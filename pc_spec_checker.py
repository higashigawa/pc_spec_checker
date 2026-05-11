#!/usr/bin/env python3
"""
PC スペックチェッカー
モダンなダークテーマのGUIでPCのスペックを表示するツール
"""

import tkinter as tk
from tkinter import ttk, font, filedialog, messagebox
import platform
import subprocess
import threading
import time
import os
import re
import csv
from datetime import datetime

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# ── カラーパレット ──────────────────────────────
BG         = "#0d0f14"
PANEL      = "#141820"
BORDER     = "#1e2433"
ACCENT     = "#00d4ff"
ACCENT2    = "#7b4fff"
TEXT_MAIN  = "#e8edf5"
TEXT_SUB   = "#6b7a99"
TEXT_VAL   = "#c0cce6"
GREEN      = "#00e87a"
YELLOW     = "#ffd166"
RED        = "#ff4d6d"
ORANGE     = "#ff8c42"


def run_command(cmd):
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            shell=(platform.system() == "Windows")
        )
        return result.stdout.strip()
    except Exception:
        return ""


def get_cpu_info():
    info = {}
    sys = platform.system()

    info["名前"] = platform.processor() or "不明"

    if sys == "Darwin":
        brand = run_command(["sysctl", "-n", "machdep.cpu.brand_string"])
        if brand:
            info["名前"] = brand
        cores_physical = run_command(["sysctl", "-n", "hw.physicalcpu"])
        cores_logical  = run_command(["sysctl", "-n", "hw.logicalcpu"])
        if cores_physical:
            info["物理コア数"] = cores_physical
        if cores_logical:
            info["論理コア数"] = cores_logical
        freq = run_command(["sysctl", "-n", "hw.cpufrequency"])
        if freq and freq.isdigit():
            info["基本クロック"] = f"{int(freq) / 1e9:.2f} GHz"

    elif sys == "Linux":
        cpuinfo = run_command(["cat", "/proc/cpuinfo"])
        for line in cpuinfo.splitlines():
            if "model name" in line:
                info["名前"] = line.split(":")[1].strip()
                break
        physical = run_command(
            ["sh", "-c", "grep '^physical id' /proc/cpuinfo | sort -u | wc -l"]
        )
        if physical:
            info["物理コア数"] = physical
        logical = run_command(
            ["sh", "-c", "grep '^processor' /proc/cpuinfo | wc -l"]
        )
        if logical:
            info["論理コア数"] = logical

    elif sys == "Windows":
        name = run_command(
            "wmic cpu get Name /value"
        )
        for line in name.splitlines():
            if "Name=" in line:
                info["名前"] = line.split("=")[1].strip()
        cores = run_command("wmic cpu get NumberOfCores /value")
        for line in cores.splitlines():
            if "NumberOfCores=" in line:
                info["物理コア数"] = line.split("=")[1].strip()
        threads = run_command("wmic cpu get NumberOfLogicalProcessors /value")
        for line in threads.splitlines():
            if "NumberOfLogicalProcessors=" in line:
                info["論理コア数"] = line.split("=")[1].strip()
        speed = run_command("wmic cpu get MaxClockSpeed /value")
        for line in speed.splitlines():
            if "MaxClockSpeed=" in line:
                mhz = line.split("=")[1].strip()
                if mhz.isdigit():
                    info["最大クロック"] = f"{int(mhz)/1000:.2f} GHz"

    if HAS_PSUTIL:
        cpu = psutil.cpu_freq()
        if cpu:
            info["現在クロック"] = f"{cpu.current:.0f} MHz"
        info["物理コア数"] = str(psutil.cpu_count(logical=False))
        info["論理コア数"] = str(psutil.cpu_count(logical=True))

    return info


def get_memory_info():
    info = {}
    sys = platform.system()

    if HAS_PSUTIL:
        mem = psutil.virtual_memory()
        info["合計"] = f"{mem.total / (1024**3):.1f} GB"
        info["使用中"] = f"{mem.used / (1024**3):.1f} GB"
        info["空き"] = f"{mem.available / (1024**3):.1f} GB"
        info["使用率"] = f"{mem.percent:.1f} %"
        swap = psutil.swap_memory()
        info["スワップ合計"] = f"{swap.total / (1024**3):.1f} GB"
        return info

    if sys == "Darwin":
        out = run_command(["sysctl", "-n", "hw.memsize"])
        if out.isdigit():
            info["合計"] = f"{int(out) / (1024**3):.1f} GB"
    elif sys == "Linux":
        out = run_command(["sh", "-c", "grep MemTotal /proc/meminfo"])
        m = re.search(r"(\d+)", out)
        if m:
            info["合計"] = f"{int(m.group(1)) / (1024**2):.1f} GB"
    elif sys == "Windows":
        out = run_command("wmic computersystem get TotalPhysicalMemory /value")
        for line in out.splitlines():
            if "TotalPhysicalMemory=" in line:
                v = line.split("=")[1].strip()
                if v.isdigit():
                    info["合計"] = f"{int(v) / (1024**3):.1f} GB"
    return info


def get_disk_info():
    disks = []
    if HAS_PSUTIL:
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "マウント":   part.mountpoint,
                    "デバイス":   part.device,
                    "ファイルシステム": part.fstype,
                    "合計":      f"{usage.total / (1024**3):.1f} GB",
                    "使用中":    f"{usage.used  / (1024**3):.1f} GB",
                    "空き":      f"{usage.free  / (1024**3):.1f} GB",
                    "使用率":    f"{usage.percent:.1f} %",
                })
            except PermissionError:
                pass
        return disks

    sys = platform.system()
    if sys in ("Darwin", "Linux"):
        out = run_command(["df", "-h"])
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 6:
                disks.append({
                    "デバイス": parts[0],
                    "合計":    parts[1],
                    "使用中":  parts[2],
                    "空き":    parts[3],
                    "使用率":  parts[4],
                    "マウント": parts[5],
                })
    elif sys == "Windows":
        out = run_command("wmic logicaldisk get Caption,Size,FreeSpace,FileSystem /value")
        disk = {}
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                disk[k.strip()] = v.strip()
            elif not line.strip() and disk:
                total = int(disk.get("Size", 0) or 0)
                free  = int(disk.get("FreeSpace", 0) or 0)
                used  = total - free
                disks.append({
                    "デバイス":   disk.get("Caption", ""),
                    "ファイルシステム": disk.get("FileSystem", ""),
                    "合計":      f"{total / (1024**3):.1f} GB" if total else "不明",
                    "使用中":    f"{used  / (1024**3):.1f} GB" if total else "不明",
                    "空き":      f"{free  / (1024**3):.1f} GB" if total else "不明",
                    "使用率":    f"{used/total*100:.1f} %" if total else "不明",
                })
                disk = {}
    return disks


def get_network_info():
    """
    各ネットワークインターフェースの情報を返す。
    戻り値: list of dict  (インターフェースごとに1つの dict)
    """
    import uuid as _uuid
    import socket as _socket

    interfaces = []

    if HAS_PSUTIL:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        AF_INET  = _socket.AF_INET
        AF_INET6 = _socket.AF_INET6
        # psutil では MAC は AF_LINK (17) または AF_PACKET (17)
        MAC_FAMILIES = {psutil.AF_LINK} if hasattr(psutil, "AF_LINK") else set()
        # fallback: family value == 17 (AF_PACKET on Linux, AF_LINK on macOS/Win)
        MAC_FAMILIES.add(17)

        for iface, addr_list in addrs.items():
            st = stats.get(iface)
            ipv4_obj = next((a for a in addr_list if a.family == AF_INET), None)
            ipv6 = next((a.address.split("%")[0] for a in addr_list if a.family == AF_INET6
                         and not a.address.startswith("fe80")), None)
            mac  = next((a.address for a in addr_list if a.family in MAC_FAMILIES), None)

            ipv4    = ipv4_obj.address if ipv4_obj else None
            netmask = ipv4_obj.netmask if ipv4_obj else None

            # ループバックは除外
            if ipv4 == "127.0.0.1" and not mac:
                continue
            # 何も情報がないインターフェースはスキップ
            if not ipv4 and not mac:
                continue

            entry = {"インターフェース": iface}
            if mac:
                entry["MACアドレス"] = mac.upper()
            if ipv4:
                entry["IPv4アドレス"] = ipv4
            if netmask:
                entry["サブネットマスク"] = netmask
            if ipv6:
                entry["IPv6アドレス"] = ipv6
            if st:
                entry["リンク速度"] = f"{st.speed} Mbps" if st.speed else "不明"
                entry["状態"] = "稼働中" if st.isup else "停止中"
            interfaces.append(entry)
        return interfaces

    # ── psutil なし: 標準ライブラリ + OS コマンドで取得 ──
    sys_name = platform.system()

    # uuid モジュールで主インターフェースの MAC だけでも取得
    raw_mac = _uuid.getnode()
    mac_str = ":".join(f"{(raw_mac >> (8*i)) & 0xff:02X}" for i in reversed(range(6)))

    if sys_name == "Darwin":
        out = run_command(["ifconfig"])
        current_iface = None
        iface_data = {}
        for line in out.splitlines():
            m = re.match(r"^(\S+):", line)
            if m:
                if current_iface and iface_data:
                    interfaces.append(iface_data)
                current_iface = m.group(1)
                iface_data = {"インターフェース": current_iface}
            elif current_iface:
                m_mac  = re.search(r"ether\s+([0-9a-f:]{17})", line)
                m_ipv4 = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", line)
                m_mask = re.search(r"netmask\s+(0x[0-9a-fA-F]+|\d+\.\d+\.\d+\.\d+)", line)
                m_ipv6 = re.search(r"inet6\s+([0-9a-f:]+)(?:%\S+)?", line)
                if m_mac:
                    iface_data["MACアドレス"] = m_mac.group(1).upper()
                if m_ipv4 and m_ipv4.group(1) != "127.0.0.1":
                    iface_data["IPv4アドレス"] = m_ipv4.group(1)
                if m_mask:
                    raw = m_mask.group(1)
                    if raw.startswith("0x"):
                        val = int(raw, 16)
                        mask = ".".join(str((val >> (8*i)) & 0xff) for i in reversed(range(4)))
                    else:
                        mask = raw
                    iface_data["サブネットマスク"] = mask
                if m_ipv6 and not m_ipv6.group(1).startswith("::1"):
                    iface_data.setdefault("IPv6アドレス", m_ipv6.group(1))
        if current_iface and iface_data:
            interfaces.append(iface_data)

    elif sys_name == "Linux":
        out = run_command(["ip", "addr"])
        current_iface = None
        iface_data = {}
        for line in out.splitlines():
            m = re.match(r"^\d+:\s+(\S+):", line)
            if m:
                if current_iface and iface_data:
                    interfaces.append(iface_data)
                current_iface = m.group(1).rstrip("@")
                iface_data = {"インターフェース": current_iface}
            elif current_iface:
                m_mac  = re.search(r"link/ether\s+([0-9a-f:]{17})", line)
                m_ipv4 = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", line)
                m_ipv6 = re.search(r"inet6\s+([0-9a-f:]+)(?:/\d+)?", line)
                if m_mac:
                    iface_data["MACアドレス"] = m_mac.group(1).upper()
                if m_ipv4 and m_ipv4.group(1) != "127.0.0.1":
                    iface_data["IPv4アドレス"] = m_ipv4.group(1)
                    prefix = int(m_ipv4.group(2))
                    bits = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
                    mask = ".".join(str((bits >> (8*i)) & 0xff) for i in reversed(range(4)))
                    iface_data["サブネットマスク"] = mask
                if m_ipv6 and not m_ipv6.group(1).startswith("::1") \
                           and not m_ipv6.group(1).startswith("fe80"):
                    iface_data.setdefault("IPv6アドレス", m_ipv6.group(1))
        if current_iface and iface_data:
            interfaces.append(iface_data)

    elif sys_name == "Windows":
        out = run_command("getmac /v /fo list")
        current = {}
        for line in out.splitlines():
            line = line.strip()
            if not line:
                if current:
                    interfaces.append(current)
                    current = {}
                continue
            if "接続名" in line or "Connection Name" in line:
                current["インターフェース"] = line.split(":", 1)[1].strip()
            elif "物理アドレス" in line or "Physical Address" in line:
                current["MACアドレス"] = line.split(":", 1)[1].strip().upper()
            elif "トランスポート名" in line or "Transport Name" in line:
                current["トランスポート"] = line.split(":", 1)[1].strip()
        if current:
            interfaces.append(current)

        # IPv4・サブネットマスクは ipconfig から補完
        ipcfg = run_command("ipconfig")
        iface_name = None
        for line in ipcfg.splitlines():
            m = re.match(r"^(\S.*):$", line)
            if m:
                iface_name = m.group(1).strip()
            m_ip   = re.search(r"IPv4.*?:\s+(\d+\.\d+\.\d+\.\d+)", line)
            m_mask = re.search(r"サブネット マスク.*?:\s+(\d+\.\d+\.\d+\.\d+)|Subnet Mask.*?:\s+(\d+\.\d+\.\d+\.\d+)", line)
            if m_ip and iface_name:
                for entry in interfaces:
                    if iface_name in entry.get("インターフェース", ""):
                        entry["IPv4アドレス"] = m_ip.group(1)
            if m_mask and iface_name:
                mask_val = m_mask.group(1) or m_mask.group(2)
                for entry in interfaces:
                    if iface_name in entry.get("インターフェース", ""):
                        entry["サブネットマスク"] = mask_val

    if not interfaces:
        interfaces.append({"インターフェース": "不明", "MACアドレス": mac_str})

    return interfaces


def get_machine_info():
    """機種名とシリアルナンバーを返す (macOS / Linux / Windows 対応)"""
    info = {}
    sys_name = platform.system()

    if sys_name == "Darwin":
        sp = run_command(["system_profiler", "SPHardwareDataType"])
        for line in sp.splitlines():
            line = line.strip()
            if "Model Name:" in line:
                info["モデル名"] = line.split(":", 1)[1].strip()
            elif "Model Identifier:" in line:
                info["モデル識別子"] = line.split(":", 1)[1].strip()
            elif "Chip:" in line:
                info["チップ"] = line.split(":", 1)[1].strip()
            elif "Serial Number" in line:
                info["シリアルNo."] = line.split(":", 1)[1].strip()
            elif "Hardware UUID" in line:
                info["ハードウェアUUID"] = line.split(":", 1)[1].strip()
        # sysctl フォールバック
        if not info.get("モデル識別子"):
            m = run_command(["sysctl", "-n", "hw.model"])
            if m:
                info["モデル識別子"] = m

    elif sys_name == "Linux":
        # 優先: /sys/class/dmi/id (root不要、多くのディストリで読める)
        import os
        dmi_map = [
            ("sys_vendor",      "メーカー"),
            ("product_name",    "機種名"),
            ("product_version", "製品バージョン"),
            ("product_serial",  "シリアルNo."),
            ("product_uuid",    "UUID"),
            ("board_name",      "ボード名"),
            ("board_vendor",    "ボードメーカー"),
        ]
        for dmi_key, label in dmi_map:
            path = f"/sys/class/dmi/id/{dmi_key}"
            try:
                with open(path, "r") as f:
                    val = f.read().strip()
                skip = {"", "To Be Filled By O.E.M.", "Default string",
                        "None", "N/A", "Not Specified", "Unknown"}
                if val not in skip:
                    info[label] = val
            except Exception:
                pass

        # 次善: dmidecode (root 権限があれば)
        if not info:
            out = run_command(["dmidecode", "-t", "system"])
            for line in out.splitlines():
                line = line.strip()
                for keyword, label in [
                    ("Manufacturer:", "メーカー"),
                    ("Product Name:", "機種名"),
                    ("Serial Number:", "シリアルNo."),
                    ("UUID:", "UUID"),
                ]:
                    if line.startswith(keyword):
                        val = line.split(":", 1)[1].strip()
                        skip = {"Not Specified", "Not Present", "", "None"}
                        if val not in skip:
                            info[label] = val

        # さらに: /proc/cpuinfo の Hardware / Revision (Raspberry Pi 等)
        if not info:
            cpuinfo = run_command(["cat", "/proc/cpuinfo"])
            for line in cpuinfo.splitlines():
                if line.startswith("Hardware"):
                    info["ハードウェア"] = line.split(":", 1)[1].strip()
                elif line.startswith("Revision"):
                    info["リビジョン"] = line.split(":", 1)[1].strip()
                elif line.startswith("Serial"):
                    info["シリアルNo."] = line.split(":", 1)[1].strip()

        if not info:
            info["備考"] = "DMI情報を取得できませんでした (仮想環境または権限不足)"

    elif sys_name == "Windows":
        # PowerShell で取得（WMIC は Windows 11 で廃止済み）
        def ps(script):
            """PowerShell ワンライナーを実行して結果を返す"""
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive",
                     "-Command", script],
                    capture_output=True, text=True, timeout=15
                )
                return r.stdout.strip()
            except Exception:
                return ""

        skip_vals = {"", "None", "N/A", "Not Available", "To Be Filled By O.E.M.",
                     "Default string", "System Product Name", "System Manufacturer",
                     "System Version", "INVALID", "00000000-0000-0000-0000-000000000000"}

        def ps_get(script, label):
            v = ps(script)
            if v and v not in skip_vals:
                info[label] = v

        # CIM (PowerShell 3+, Win8以降で確実に動作)
        ps_get(
            "(Get-CimInstance Win32_ComputerSystem).Manufacturer",
            "メーカー")
        ps_get(
            "(Get-CimInstance Win32_ComputerSystem).Model",
            "機種名")
        ps_get(
            "(Get-CimInstance Win32_ComputerSystem).SystemFamily",
            "製品ファミリー")
        ps_get(
            "(Get-CimInstance Win32_BIOS).SerialNumber",
            "シリアルNo.")
        ps_get(
            "(Get-CimInstance Win32_BIOS).SMBIOSBIOSVersion",
            "BIOSバージョン")
        ps_get(
            "(Get-CimInstance Win32_ComputerSystemProduct).UUID",
            "UUID")

        # フォールバック: WMI (古い PowerShell 向け)
        if not info:
            ps_get(
                "(Get-WmiObject Win32_ComputerSystem).Manufacturer",
                "メーカー")
            ps_get(
                "(Get-WmiObject Win32_ComputerSystem).Model",
                "機種名")
            ps_get(
                "(Get-WmiObject Win32_BIOS).SerialNumber",
                "シリアルNo.")

        # さらにフォールバック: レジストリ
        if "機種名" not in info:
            v = ps(r'(Get-ItemProperty "HKLM:\HARDWARE\DESCRIPTION\System\BIOS").SystemProductName')
            if v and v not in skip_vals:
                info["機種名"] = v
        if "メーカー" not in info:
            v = ps(r'(Get-ItemProperty "HKLM:\HARDWARE\DESCRIPTION\System\BIOS").SystemManufacturer')
            if v and v not in skip_vals:
                info["メーカー"] = v
        if "シリアルNo." not in info:
            v = ps(r'(Get-ItemProperty "HKLM:\HARDWARE\DESCRIPTION\System\BIOS").BIOSVendor')
            if v and v not in skip_vals:
                info["BIOSベンダー"] = v

        if not info:
            info["備考"] = "機種情報を取得できませんでした (管理者権限が必要な場合があります)"

    return info

def get_os_info():
    info = {
        "OS":           platform.system(),
        "バージョン":   platform.version(),
        "リリース":     platform.release(),
        "アーキテクチャ": platform.machine(),
        "ホスト名":     platform.node(),
        "Pythonバージョン": platform.python_version(),
    }
    sys = platform.system()
    if sys == "Darwin":
        ver = run_command(["sw_vers", "-productVersion"])
        name = run_command(["sw_vers", "-productName"])
        if ver:
            info["macOSバージョン"] = f"{name} {ver}"
    elif sys == "Linux":
        out = run_command(["cat", "/etc/os-release"])
        for line in out.splitlines():
            if line.startswith("PRETTY_NAME="):
                info["ディストリビューション"] = line.split("=")[1].strip().strip('"')
    return info


def _ps_run(script):
    """PowerShell コマンドを実行して stdout を返す"""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=15
        )
        return r.stdout.strip()
    except Exception:
        return ""


def get_gpu_info():
    """GPU情報を返す。戻り値は list of dict (GPU ごとに 1 dict)"""
    gpus = []
    sys_name = platform.system()

    if sys_name == "Darwin":
        # system_profiler で確実に取得
        out = run_command(["system_profiler", "SPDisplaysDataType"])
        current = {}
        for line in out.splitlines():
            line = line.strip()
            if "Chipset Model:" in line:
                if current:
                    gpus.append(current)
                current = {"GPU名": line.split(":", 1)[1].strip()}
            elif current:
                for keyword, label in [
                    ("VRAM",         "VRAM"),
                    ("Vendor:",      "ベンダー"),
                    ("Device ID:",   "デバイスID"),
                    ("Metal:",       "Metal対応"),
                    ("Resolution:",  "解像度"),
                    ("Displays:",    "接続ディスプレイ数"),
                ]:
                    if keyword in line:
                        current[label] = line.split(":", 1)[1].strip()
        if current:
            gpus.append(current)

    elif sys_name == "Linux":
        # ① lspci (pciutils)
        for lspci_cmd in [["lspci", "-vmm"], ["lspci", "-v"], ["lspci"]]:
            lspci_out = run_command(lspci_cmd)
            if lspci_out:
                break

        if lspci_out:
            current = {}
            in_gpu = False
            for line in lspci_out.splitlines():
                # -vmm 形式: "Class:	VGA..." などフラットに来る
                if re.match(r"^Class:\s+(VGA|3D|Display)", line):
                    if current:
                        gpus.append(current)
                    current = {}
                    in_gpu = True
                elif in_gpu and line.startswith("Device:"):
                    current["GPU名"] = line.split(":", 1)[1].strip()
                elif in_gpu and line.startswith("SVendor:"):
                    current["ベンダー"] = line.split(":", 1)[1].strip()
                elif in_gpu and line.startswith("Driver:"):
                    current["カーネルドライバ"] = line.split(":", 1)[1].strip()
                elif not line.strip() and in_gpu:
                    in_gpu = False

            # 通常 lspci 形式のフォールバック
            if not current and not gpus:
                for line in lspci_out.splitlines():
                    if any(k in line for k in ("VGA", "3D controller", "Display controller")):
                        parts = line.split(":", 2)
                        name = parts[2].strip() if len(parts) >= 3 else line
                        current = {"GPU名": name}
                    elif current and line.startswith("	"):
                        if "Kernel driver" in line:
                            current["カーネルドライバ"] = line.split(":", 1)[1].strip()
            if current:
                gpus.append(current)

        # ② /sys/class/drm フォールバック (lspci なし環境)
        if not gpus:
            drm_path = "/sys/class/drm"
            try:
                cards = [d for d in os.listdir(drm_path)
                         if re.match(r"^card\d+$", d)]
                for card in sorted(cards):
                    vendor_file = os.path.join(drm_path, card, "device", "vendor")
                    device_file = os.path.join(drm_path, card, "device", "device")
                    try:
                        vendor = open(vendor_file).read().strip()
                        device = open(device_file).read().strip()
                        gpus.append({"GPU名": f"{card} (vendor={vendor} device={device})"})
                    except Exception:
                        gpus.append({"GPU名": card})
            except Exception:
                pass

        # ③ nvidia-smi (NVIDIA GPU 専用)
        nsmi = run_command(["nvidia-smi",
                            "--query-gpu=name,memory.total,driver_version",
                            "--format=csv,noheader,nounits"])
        if nsmi:
            for line in nsmi.splitlines():
                parts = [p.strip() for p in line.split(",")]
                entry = {"GPU名": parts[0]} if parts else {}
                if len(parts) >= 2:
                    try:
                        entry["VRAM"] = f"{int(parts[1])/1024:.1f} GB"
                    except ValueError:
                        entry["VRAM"] = parts[1]
                if len(parts) >= 3:
                    entry["ドライババージョン"] = parts[2]
                if entry:
                    # 既存エントリと統合
                    matched = False
                    for g in gpus:
                        if parts[0].lower() in g.get("GPU名", "").lower():
                            g.update(entry)
                            matched = True
                            break
                    if not matched:
                        gpus.append(entry)

        if not gpus:
            gpus.append({"備考": "GPU情報を取得できませんでした (pciutils/lspci をインストールしてください)"})

    elif sys_name == "Windows":
        # PowerShell CIM で取得（WMIC 廃止対応）
        # 各プロパティを個別行で出力してパース
        ps_script = (
            "Get-CimInstance Win32_VideoController | ForEach-Object {"
            "  $ram = 0;"
            "  if ($_.AdapterRAM -and $_.AdapterRAM -gt 0) {"
            "    $ram = [math]::Round($_.AdapterRAM / 1073741824, 1)"
            "  };"
            "  $rx = if ($_.CurrentHorizontalResolution) { $_.CurrentHorizontalResolution } else { 0 };"
            "  $ry = if ($_.CurrentVerticalResolution)   { $_.CurrentVerticalResolution   } else { 0 };"
            "  $hz = if ($_.CurrentRefreshRate)          { $_.CurrentRefreshRate          } else { 0 };"
            "  Write-Output ('---GPU---');"
            "  Write-Output ('NAME:'     + $_.Name);"
            "  Write-Output ('VRAM:'     + $ram);"
            "  Write-Output ('DRIVER:'   + $_.DriverVersion);"
            "  Write-Output ('PROC:'     + $_.VideoProcessor);"
            "  Write-Output ('RESX:'     + $rx);"
            "  Write-Output ('RESY:'     + $ry);"
            "  Write-Output ('HZ:'       + $hz);"
            "  Write-Output ('STATUS:'   + $_.Status)"
            "}"
        )
        out = _ps_run(ps_script)
        current = {}
        for line in out.splitlines():
            line = line.strip()
            if line == "---GPU---":
                if current.get("GPU名"):
                    gpus.append(current)
                current = {}
            elif ":" in line:
                key, val = line.split(":", 1)
                val = val.strip()
                if key == "NAME" and val:
                    current["GPU名"] = val
                elif key == "VRAM":
                    try:
                        f = float(val)
                        current["VRAM"] = f"{f:.1f} GB" if f > 0 else "共有メモリ (統合GPU)"
                    except ValueError:
                        pass
                elif key == "DRIVER" and val:
                    current["ドライババージョン"] = val
                elif key == "PROC" and val:
                    current["ビデオプロセッサ"] = val
                elif key == "RESX" and val not in ("", "0"):
                    current.setdefault("_rx", val)
                elif key == "RESY" and val not in ("", "0"):
                    current.setdefault("_ry", val)
                elif key == "HZ" and val not in ("", "0"):
                    current.setdefault("_hz", val)
                elif key == "STATUS" and val:
                    current["ステータス"] = val
        if current.get("GPU名"):
            gpus.append(current)

        # 解像度を結合
        for g in gpus:
            rx = g.pop("_rx", None)
            ry = g.pop("_ry", None)
            hz = g.pop("_hz", None)
            if rx and ry:
                g["現在の解像度"] = f"{rx} x {ry}"
            if hz:
                g["リフレッシュレート"] = f"{hz} Hz"

        # フォールバック: Get-WmiObject (古い PowerShell 向け)
        if not gpus:
            fb_script = (
                "Get-WmiObject Win32_VideoController | ForEach-Object {"
                "  Write-Output ('---GPU---');"
                "  Write-Output ('NAME:'   + $_.Name);"
                "  Write-Output ('DRIVER:' + $_.DriverVersion)"
                "}"
            )
            out2 = _ps_run(fb_script)
            current = {}
            for line in out2.splitlines():
                line = line.strip()
                if line == "---GPU---":
                    if current.get("GPU名"):
                        gpus.append(current)
                    current = {}
                elif line.startswith("NAME:") and line[5:].strip():
                    current["GPU名"] = line[5:].strip()
                elif line.startswith("DRIVER:") and line[7:].strip():
                    current["ドライババージョン"] = line[7:].strip()
            if current.get("GPU名"):
                gpus.append(current)

        if not gpus:
            gpus.append({"備考": "GPU情報を取得できませんでした"})

    return gpus


# ── ウィジェット構築 ─────────────────────────────

class PCSpecApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PC スペックチェッカー")
        self.configure(bg=BG)
        self.geometry("900x700")
        self.minsize(700, 500)
        self._spec_data = {}  # CSV出力用データ格納
        self._setup_fonts()
        self._build_ui()
        self._load_data_async()

    def _setup_fonts(self):
        self.font_title  = ("Helvetica Neue", 22, "bold")
        self.font_head   = ("Helvetica Neue", 11, "bold")
        self.font_label  = ("Helvetica Neue", 10)
        self.font_val    = ("Menlo", 10) if platform.system() == "Darwin" else ("Consolas", 10)
        self.font_small  = ("Helvetica Neue", 9)

    def _build_ui(self):
        # ── ヘッダー
        header = tk.Frame(self, bg=PANEL, height=64)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        tk.Label(
            header, text="⬡  PC SPEC CHECKER",
            bg=PANEL, fg=ACCENT,
            font=self.font_title
        ).pack(side="left", padx=24, pady=14)

        self.xlsx_btn = tk.Button(
            header, text="📊 Excel出力",
            bg="#1d6f42", fg=TEXT_MAIN,
            font=self.font_small,
            relief="flat", padx=12, pady=4,
            cursor="hand2",
            command=self._export_xlsx,
            state="disabled"
        )
        self.xlsx_btn.pack(side="right", padx=(0, 4), pady=14)

        self.csv_btn = tk.Button(
            header, text="📥 CSV出力",
            bg=ACCENT2, fg=TEXT_MAIN,
            font=self.font_small,
            relief="flat", padx=12, pady=4,
            cursor="hand2",
            command=self._export_csv,
            state="disabled"
        )
        self.csv_btn.pack(side="right", padx=(0, 8), pady=14)

        self.status_lbl = tk.Label(
            header, text="読み込み中...",
            bg=PANEL, fg=TEXT_SUB,
            font=self.font_small
        )
        self.status_lbl.pack(side="right", padx=24)

        # ── ノートブック
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("TNotebook",
            background=BG, borderwidth=0, tabmargins=[0, 0, 0, 0])
        style.configure("TNotebook.Tab",
            background=PANEL, foreground=TEXT_SUB,
            padding=[18, 8], font=self.font_label, borderwidth=0)
        style.map("TNotebook.Tab",
            background=[("selected", BG)],
            foreground=[("selected", ACCENT)])
        style.configure("TFrame", background=BG)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=0, pady=0)

        tab_names = ["機種情報", "OS", "CPU", "メモリ", "ストレージ", "GPU", "ネットワーク"]
        self.tabs = {}
        for name in tab_names:
            frame = ttk.Frame(self.nb)
            self.nb.add(frame, text=f"  {name}  ")
            self.tabs[name] = frame

        # ── フッター
        footer = tk.Frame(self, bg=PANEL, height=28)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        if not HAS_PSUTIL:
            tk.Label(
                footer,
                text="ヒント: pip install psutil を実行するとより詳細な情報が表示されます",
                bg=PANEL, fg=YELLOW, font=self.font_small
            ).pack(side="left", padx=16, pady=4)

    # ── データ読み込み ─────────────────────────
    def _load_data_async(self):
        threading.Thread(target=self._collect_all, daemon=True).start()

    def _collect_all(self):
        self._update_status("機種情報を取得中...")
        machine_data = get_machine_info()
        self._spec_data["機種情報"] = machine_data
        self.after(0, lambda: self._render_kv(self.tabs["機種情報"], machine_data, "機種情報"))

        self._update_status("OS情報を取得中...")
        os_data = get_os_info()
        self._spec_data["OS"] = os_data
        self.after(0, lambda: self._render_kv(self.tabs["OS"], os_data))

        self._update_status("CPU情報を取得中...")
        cpu_data = get_cpu_info()
        self._spec_data["CPU"] = cpu_data
        self.after(0, lambda: self._render_cpu(self.tabs["CPU"], cpu_data))

        self._update_status("メモリ情報を取得中...")
        mem_data = get_memory_info()
        self._spec_data["メモリ"] = mem_data
        self.after(0, lambda: self._render_memory(self.tabs["メモリ"], mem_data))

        self._update_status("ストレージ情報を取得中...")
        disk_data = get_disk_info()
        self._spec_data["ストレージ"] = disk_data
        self.after(0, lambda: self._render_disks(self.tabs["ストレージ"], disk_data))

        self._update_status("GPU情報を取得中...")
        gpu_data = get_gpu_info()
        self._spec_data["GPU"] = gpu_data
        self.after(0, lambda: self._render_gpu(self.tabs["GPU"], gpu_data))

        self._update_status("ネットワーク情報を取得中...")
        net_data = get_network_info()
        self._spec_data["ネットワーク"] = net_data
        self.after(0, lambda: self._render_network(self.tabs["ネットワーク"], net_data))

        self._update_status("完了")
        self.after(0, lambda: self.csv_btn.config(state="normal"))
        self.after(0, lambda: self.xlsx_btn.config(state="normal"))

    def _update_status(self, msg):
        self.after(0, lambda: self.status_lbl.config(text=msg))

    def _get_default_stem(self):
        """ファイル名のベース部分（拡張子なし）を生成"""
        hostname  = platform.node() or "unknown"
        serial    = self._spec_data.get("機種情報", {}).get("シリアルNo.", "") or ""
        safe_host = re.sub(r'[\\/:*?"<>|]', "_", hostname)
        safe_ser  = re.sub(r'[\\/:*?"<>|]', "_", serial)
        parts = ["pc_spec", safe_host]
        if safe_ser:
            parts.append(safe_ser)
        parts.append(datetime.now().strftime("%Y%m%d_%H%M%S"))
        return "_".join(parts)

    def _export_xlsx(self):
        """全スペック情報を見やすい書式付き Excel ファイルに出力する"""
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
        except ImportError:
            if messagebox.askyesno(
                "openpyxl が見つかりません",
                "Excel出力には openpyxl が必要です。\n今すぐインストールしますか?\n\n  pip install openpyxl"
            ):
                import subprocess as _sp, sys as _sys
                try:
                    _sp.run([_sys.executable, "-m", "pip", "install", "openpyxl"], check=True)
                    messagebox.showinfo("完了", "インストール完了。もう一度「Excel出力」を押してください。")
                except Exception as e:
                    messagebox.showerror("エラー", "インストール失敗:\n" + str(e))
            return

        stem = self._get_default_stem()
        path = filedialog.asksaveasfilename(
            title="Excelの保存先を選択",
            defaultextension=".xlsx",
            initialfile=stem + ".xlsx",
            filetypes=[("Excelファイル", "*.xlsx"), ("すべてのファイル", "*.*")]
        )
        if not path:
            return

        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter

            wb = openpyxl.Workbook()
            wb.remove(wb.active)

            hostname = platform.node() or "unknown"
            serial   = self._spec_data.get("機種情報", {}).get("シリアルNo.", "") or ""
            now_str  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # ═══════════════════════════════════════════
            # カラーパレット（ライト / ビジネス向け）
            # ═══════════════════════════════════════════
            C = {
                "hdr_bg"   : "17375E",   # 濃紺  ヘッダー背景
                "hdr_fg"   : "FFFFFF",   # 白    ヘッダー文字
                "acc_bg"   : "2E75B6",   # 中青  アクセント見出し背景
                "acc_fg"   : "FFFFFF",
                "sub_bg"   : "D6E4F0",   # 薄青  サブ見出し背景
                "sub_fg"   : "17375E",
                "odd_bg"   : "FFFFFF",   # 白    奇数行
                "even_bg"  : "EBF3FB",   # 極薄青 偶数行
                "key_fg"   : "404040",   # 濃グレー キー
                "val_fg"   : "17375E",   # 濃紺   値
                "title_bg" : "17375E",   # タイトル帯
                "title_fg" : "FFFFFF",
                "info_bg"  : "D6E4F0",   # PC情報帯
                "info_fg"  : "17375E",
                "bdr"      : "B8CCE4",   # 罫線
                "bdr_acc"  : "2E75B6",   # アクセント罫線
                "sum_cat"  : "1F497D",   # サマリーカテゴリ列
            }

            # ── スタイルヘルパー ───────────────────────
            def F(color=None, bold=False, size=10, italic=False):
                return Font(name="Yu Gothic UI" if platform.system()=="Windows" else "Helvetica Neue",
                            color=color or C["key_fg"], bold=bold, size=size, italic=italic)

            def Fill(hex_c):
                return PatternFill("solid", fgColor=hex_c)

            def Al(h="left", v="center", wrap=False, indent=0):
                return Alignment(horizontal=h, vertical=v, wrap_text=wrap, indent=indent)

            def Bdr(color=None, style="thin"):
                s = Side(style=style, color=color or C["bdr"])
                return Border(left=s, right=s, top=s, bottom=s)

            def BdrAccBottom(top_color=None):
                t  = Side(style="thin",   color=top_color or C["bdr"])
                ac = Side(style="medium", color=C["bdr_acc"])
                return Border(left=t, right=t, top=t, bottom=ac)

            def set_col_widths(ws, widths):
                for i, w in enumerate(widths, 1):
                    ws.column_dimensions[get_column_letter(i)].width = w

            def freeze(ws, cell="A5"):
                ws.freeze_panes = cell

            def make_sheet(title, tab_color="17375E"):
                ws = wb.create_sheet(title=title)
                ws.sheet_view.showGridLines = False
                ws.sheet_properties.tabColor = tab_color
                return ws

            # ── 共通ブロック描画 ──────────────────────

            def draw_title_bar(ws, row, text, ncols=3):
                ws.merge_cells(f"A{row}:{get_column_letter(ncols)}{row}")
                c = ws.cell(row=row, column=1, value=text)
                c.fill = Fill(C["title_bg"]); c.font = F(C["title_fg"], bold=True, size=14)
                c.alignment = Al(h="center"); c.border = Bdr(C["title_bg"])
                ws.row_dimensions[row].height = 38
                return row + 1

            def draw_info_bar(ws, row, ncols=3):
                ws.merge_cells(f"A{row}:{get_column_letter(ncols)}{row}")
                serial_part = f"  │  シリアルNo: {serial}" if serial else ""
                c = ws.cell(row=row, column=1,
                            value=f"  PC名: {hostname}{serial_part}  │  出力日時: {now_str}")
                c.fill = Fill(C["info_bg"]); c.font = F(C["info_fg"], bold=False, size=9)
                c.alignment = Al(); c.border = BdrAccBottom()
                ws.row_dimensions[row].height = 20
                return row + 1

            def draw_col_header(ws, row, labels, ncols=None):
                n = ncols or len(labels)
                for ci, lbl in enumerate(labels, 1):
                    c = ws.cell(row=row, column=ci, value=lbl)
                    c.fill = Fill(C["hdr_bg"]); c.font = F(C["hdr_fg"], bold=True, size=10)
                    c.alignment = Al(h="center"); c.border = Bdr(C["hdr_bg"])
                ws.row_dimensions[row].height = 22
                return row + 1

            def draw_section_header(ws, row, text, ncols=3):
                ws.merge_cells(f"A{row}:{get_column_letter(ncols)}{row}")
                c = ws.cell(row=row, column=1, value=f"  ◆  {text}")
                c.fill = Fill(C["acc_bg"]); c.font = F(C["acc_fg"], bold=True, size=11)
                c.alignment = Al(); c.border = BdrAccBottom()
                ws.row_dimensions[row].height = 24
                return row + 1

            def draw_sub_header(ws, row, text, ncols=3):
                ws.merge_cells(f"A{row}:{get_column_letter(ncols)}{row}")
                c = ws.cell(row=row, column=1, value=f"    ▸  {text}")
                c.fill = Fill(C["sub_bg"]); c.font = F(C["sub_fg"], bold=True, size=10)
                c.alignment = Al(); c.border = Bdr(C["bdr_acc"], style="thin")
                ws.row_dimensions[row].height = 20
                return row + 1

            def draw_kv(ws, row, key, value, idx=0, ncols=3):
                bg = C["odd_bg"] if idx % 2 == 0 else C["even_bg"]
                kc = ws.cell(row=row, column=1, value=key)
                kc.fill = Fill(bg); kc.font = F(C["key_fg"], size=10)
                kc.alignment = Al(indent=1); kc.border = Bdr()

                ws.merge_cells(f"B{row}:{get_column_letter(ncols)}{row}")
                vc = ws.cell(row=row, column=2, value=str(value) if value else "—")
                vc.fill = Fill(bg); vc.font = F(C["val_fg"], bold=True, size=10)
                vc.alignment = Al(wrap=True); vc.border = Bdr()
                ws.row_dimensions[row].height = 18
                return row + 1

            def draw_empty(ws, row, ncols=3):
                ws.merge_cells(f"A{row}:{get_column_letter(ncols)}{row}")
                c = ws.cell(row=row, column=1, value="")
                c.fill = Fill("FFFFFF"); c.border = Bdr("FFFFFF")
                ws.row_dimensions[row].height = 6
                return row + 1

            cat_icons = {
                "機種情報": "🖥 機種情報", "OS": "💻 OS",
                "CPU": "⚡ CPU",      "メモリ": "🧠 メモリ",
                "ストレージ": "💾 ストレージ", "GPU": "🎮 GPU",
                "ネットワーク": "🌐 ネットワーク",
            }
            tab_colors = {
                "機種情報": "17375E", "OS": "375623", "CPU": "7B3F00",
                "メモリ": "4A235A", "ストレージ": "78290F",
                "GPU": "1C3A5E", "ネットワーク": "1A472A",
            }

            # ═══════════════════════════════════════════
            # ① サマリーシート
            # ═══════════════════════════════════════════
            ws_s = make_sheet("📋 サマリー", "17375E")
            set_col_widths(ws_s, [20, 28, 42])

            row = draw_title_bar(ws_s, 1, "🖥  PC SPEC CHECKER  ─  スペック一覧")
            row = draw_info_bar(ws_s, row)
            row = draw_empty(ws_s, row)
            row = draw_col_header(ws_s, row, ["カテゴリ", "項目", "値"])
            freeze(ws_s, f"A{row}")

            idx = 0
            prev_cat = None
            for cat, data in self._spec_data.items():
                rows_to_write = []
                if isinstance(data, dict):
                    for k, v in data.items():
                        rows_to_write.append((cat, k, str(v) if v else "—"))
                elif isinstance(data, list):
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        sub = (item.get("マウント") or item.get("GPU名")
                               or item.get("インターフェース") or item.get("備考") or "")
                        lbl = f"{cat}  ({sub})" if sub else cat
                        for k, v in item.items():
                            rows_to_write.append((lbl, k, str(v) if v else "—"))

                for cat_lbl, k, v in rows_to_write:
                    bg = C["odd_bg"] if idx % 2 == 0 else C["even_bg"]
                    # カテゴリ列
                    cc = ws_s.cell(row=row, column=1, value=cat_lbl if cat_lbl != prev_cat else "")
                    cc.fill = Fill(bg); cc.font = F(C["sum_cat"], bold=(cat_lbl != prev_cat), size=9)
                    cc.alignment = Al(indent=1); cc.border = Bdr()
                    prev_cat = cat_lbl
                    # キー列
                    kc = ws_s.cell(row=row, column=2, value=k)
                    kc.fill = Fill(bg); kc.font = F(C["key_fg"], size=10)
                    kc.alignment = Al(indent=1); kc.border = Bdr()
                    # 値列
                    vc = ws_s.cell(row=row, column=3, value=v)
                    vc.fill = Fill(bg); vc.font = F(C["val_fg"], bold=True, size=10)
                    vc.alignment = Al(wrap=True); vc.border = Bdr()
                    ws_s.row_dimensions[row].height = 18
                    row += 1; idx += 1

            # ═══════════════════════════════════════════
            # ② カテゴリ別シート
            # ═══════════════════════════════════════════
            for cat, data in self._spec_data.items():
                icon  = cat_icons.get(cat, cat)
                tcolor = tab_colors.get(cat, "17375E")
                ws = make_sheet(icon, tcolor)
                set_col_widths(ws, [30, 45, 0])  # C列は非表示（merge先）

                r = draw_title_bar(ws, 1, icon)
                r = draw_info_bar(ws, r)
                r = draw_empty(ws, r)

                if isinstance(data, dict):
                    r = draw_section_header(ws, r, cat)
                    r = draw_col_header(ws, r, ["項目", "値"])
                    for i, (k, v) in enumerate(data.items()):
                        r = draw_kv(ws, r, k, v, i)
                    freeze(ws, f"A{r - len(data)}")

                elif isinstance(data, list):
                    r = draw_col_header(ws, r, ["項目", "値"])
                    freeze(ws, f"A{r}")
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        sub = (item.get("マウント") or item.get("GPU名")
                               or item.get("インターフェース") or item.get("備考") or "")
                        r = draw_sub_header(ws, r, sub or cat)
                        for i, (k, v) in enumerate(item.items()):
                            r = draw_kv(ws, r, k, v, i)
                        r = draw_empty(ws, r)

            wb.save(path)
            messagebox.showinfo("Excel出力完了", "スペック情報を保存しました。\n\n" + path)

        except Exception as e:
            messagebox.showerror("エラー", "Excel出力に失敗しました。\n\n" + str(e))

    def _export_csv(self):
        """全スペック情報を CSV ファイルに出力する"""
        hostname = platform.node() or "unknown"
        default_name = self._get_default_stem() + ".csv"
        path = filedialog.asksaveasfilename(
            title="CSVの保存先を選択",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSVファイル", "*.csv"), ("すべてのファイル", "*.*")]
        )
        if not path:
            return  # キャンセル

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["PC名", hostname])
                writer.writerow(["出力日時", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                writer.writerow([])
                writer.writerow(["カテゴリ", "項目", "値"])
                writer.writerow([])

                for category, data in self._spec_data.items():
                    if isinstance(data, dict):
                        # OS, CPU, メモリ, 機種情報
                        for key, val in data.items():
                            writer.writerow([category, key, val])
                        writer.writerow([])

                    elif isinstance(data, list):
                        for i, item in enumerate(data):
                            if not isinstance(item, dict):
                                continue
                            # ストレージ: マウント名、GPU: GPU名、ネットワーク: インターフェース名を小見出しに
                            subtitle = (
                                item.get("マウント")
                                or item.get("GPU名")
                                or item.get("インターフェース")
                                or item.get("備考")
                                or f"#{i+1}"
                            )
                            for key, val in item.items():
                                writer.writerow([f"{category} ({subtitle})", key, val])
                            writer.writerow([])

            messagebox.showinfo(
                "CSV出力完了",
                "スペック情報を保存しました。\n\n" + path
            )
        except Exception as e:
            messagebox.showerror("エラー", "CSV出力に失敗しました。\n\n" + str(e))

    # ── レンダリング ────────────────────────────
    def _scrollable(self, parent):
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        style = ttk.Style()
        style.configure("Vertical.TScrollbar",
            background=BORDER, troughcolor=PANEL,
            arrowcolor=TEXT_SUB, relief="flat", borderwidth=0)
        frame = tk.Frame(canvas, bg=BG)
        frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win_id = canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(win_id, width=e.width))
        canvas.pack(side="left",  fill="both", expand=True)
        sb.pack   (side="right", fill="y")
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        return frame

    def _section_label(self, parent, text):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="x", padx=24, pady=(20, 6))
        tk.Label(f, text=text.upper(), bg=BG,
                 fg=ACCENT, font=self.font_head).pack(side="left")
        tk.Frame(f, bg=BORDER, height=1).pack(
            side="left", fill="x", expand=True, padx=(10, 0))

    def _kv_row(self, parent, label, value, alt=False):
        bg = "#111520" if alt else BG
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", padx=24, pady=1)

        lbl = tk.Label(row, text=label, bg=bg,
                       fg=TEXT_SUB, font=self.font_label, width=22, anchor="w")
        lbl.pack(side="left", padx=(0, 8), pady=5)

        val = tk.Label(row, text=value or "—", bg=bg,
                       fg=TEXT_VAL, font=self.font_val, anchor="w")
        val.pack(side="left", pady=5)

    def _render_kv(self, tab, data: dict, section="情報"):
        frame = self._scrollable(tab)
        if not data:
            self._section_label(frame, section)
            tk.Label(frame, text="情報を取得できませんでした",
                     bg=BG, fg=TEXT_SUB, font=self.font_label).pack(padx=32, pady=10)
            return
        self._section_label(frame, section if section != "情報" else list(data.keys())[0] if len(data) == 1 else "情報")
        for i, (k, v) in enumerate(data.items()):
            self._kv_row(frame, k, v, alt=(i % 2 == 1))

    def _render_cpu(self, tab, data: dict):
        frame = self._scrollable(tab)
        self._section_label(frame, "プロセッサー")
        for i, (k, v) in enumerate(data.items()):
            self._kv_row(frame, k, v, alt=(i % 2 == 1))

        if HAS_PSUTIL:
            self._section_label(frame, "リアルタイム使用率")
            bar_frame = tk.Frame(frame, bg=BG)
            bar_frame.pack(fill="x", padx=24, pady=8)
            self._draw_cpu_bars(bar_frame)

    def _draw_cpu_bars(self, parent):
        try:
            percents = psutil.cpu_percent(percpu=True, interval=0.5)
        except Exception:
            return
        cols = min(4, len(percents))
        for i, pct in enumerate(percents):
            col = i % cols
            row = i // cols
            cell = tk.Frame(parent, bg=BG)
            cell.grid(row=row, column=col, padx=8, pady=4, sticky="ew")
            parent.columnconfigure(col, weight=1)

            lbl = tk.Label(cell, text=f"Core {i}",
                           bg=BG, fg=TEXT_SUB, font=self.font_small)
            lbl.pack(anchor="w")

            bar_bg = tk.Frame(cell, bg=BORDER, height=6)
            bar_bg.pack(fill="x")
            bar_bg.update_idletasks()
            w = bar_bg.winfo_width() or 120
            fill_w = max(4, int(w * pct / 100))
            color = GREEN if pct < 60 else YELLOW if pct < 85 else RED
            bar_fill = tk.Frame(bar_bg, bg=color, height=6, width=fill_w)
            bar_fill.place(x=0, y=0)

            tk.Label(cell, text=f"{pct:.0f}%",
                     bg=BG, fg=TEXT_VAL, font=self.font_small).pack(anchor="e")

    def _render_memory(self, tab, data: dict):
        frame = self._scrollable(tab)
        self._section_label(frame, "物理メモリ")
        for i, (k, v) in enumerate(data.items()):
            self._kv_row(frame, k, v, alt=(i % 2 == 1))

        if HAS_PSUTIL:
            mem = psutil.virtual_memory()
            self._section_label(frame, "使用状況")
            self._draw_usage_bar(frame, "RAM", mem.percent, GREEN if mem.percent < 70 else YELLOW if mem.percent < 90 else RED)

            swap = psutil.swap_memory()
            if swap.total > 0:
                self._draw_usage_bar(frame, "SWAP", swap.percent, ACCENT2)

    def _draw_usage_bar(self, parent, label, pct, color):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="x", padx=24, pady=6)
        tk.Label(f, text=label, bg=BG,
                 fg=TEXT_SUB, font=self.font_label, width=10, anchor="w").pack(side="left")
        bar_bg = tk.Frame(f, bg=BORDER, height=16)
        bar_bg.pack(side="left", fill="x", expand=True, padx=(8, 8))
        bar_bg.update_idletasks()
        bar_bg.pack_propagate(False)
        # Use canvas for reliable pixel width
        bar_canvas = tk.Canvas(bar_bg, bg=BORDER, height=16, highlightthickness=0, bd=0)
        bar_canvas.pack(fill="both", expand=True)
        bar_canvas.update_idletasks()
        w = bar_canvas.winfo_width() or 300
        fill_w = max(4, int(w * pct / 100))
        bar_canvas.create_rectangle(0, 0, fill_w, 16, fill=color, outline="")
        tk.Label(f, text=f"{pct:.1f}%", bg=BG,
                 fg=TEXT_VAL, font=self.font_val, width=6).pack(side="right")

    def _render_disks(self, tab, disks: list):
        frame = self._scrollable(tab)
        if not disks:
            self._section_label(frame, "ストレージ")
            tk.Label(frame, text="情報を取得できませんでした",
                     bg=BG, fg=TEXT_SUB, font=self.font_label).pack(padx=32, pady=10)
            return

        for disk in disks:
            mount = disk.get("マウント") or disk.get("デバイス", "ドライブ")
            self._section_label(frame, f"ドライブ: {mount}")
            for i, (k, v) in enumerate(disk.items()):
                self._kv_row(frame, k, v, alt=(i % 2 == 1))

            pct_str = disk.get("使用率", "0 %").replace("%", "").strip()
            try:
                pct = float(pct_str)
                color = GREEN if pct < 70 else YELLOW if pct < 90 else RED
                self._draw_usage_bar(frame, "使用率", pct, color)
            except ValueError:
                pass


    def _render_gpu(self, tab, gpus: list):
        frame = self._scrollable(tab)
        if not gpus:
            self._section_label(frame, "GPU")
            tk.Label(frame, text="情報を取得できませんでした",
                     bg=BG, fg=TEXT_SUB, font=self.font_label).pack(padx=32, pady=10)
            return
        for gpu in gpus:
            name = gpu.get("GPU名") or gpu.get("備考", "GPU")
            self._section_label(frame, name)
            items = [(k, v) for k, v in gpu.items() if k != "GPU名"]
            for i, (k, v) in enumerate(items):
                self._kv_row(frame, k, v, alt=(i % 2 == 1))

    def _render_network(self, tab, interfaces: list):
        frame = self._scrollable(tab)
        if not interfaces:
            self._section_label(frame, "ネットワーク")
            tk.Label(frame, text="情報を取得できませんでした",
                     bg=BG, fg=TEXT_SUB, font=self.font_label).pack(padx=32, pady=10)
            return

        for iface_data in interfaces:
            name = iface_data.get("インターフェース", "不明")
            self._section_label(frame, f"インターフェース: {name}")
            items = [(k, v) for k, v in iface_data.items() if k != "インターフェース"]
            for i, (k, v) in enumerate(items):
                # MACアドレスは強調表示
                if k == "MACアドレス":
                    row_bg = "#0d1a22"
                    lbl_fg = ACCENT
                    val_fg = ACCENT
                    row = tk.Frame(frame, bg=row_bg)
                    row.pack(fill="x", padx=24, pady=1)
                    tk.Label(row, text=k, bg=row_bg, fg=lbl_fg,
                             font=self.font_label, width=22, anchor="w").pack(
                        side="left", padx=(0, 8), pady=5)
                    tk.Label(row, text=v or "—", bg=row_bg, fg=val_fg,
                             font=self.font_val, anchor="w").pack(side="left", pady=5)
                else:
                    self._kv_row(frame, k, v, alt=(i % 2 == 1))


def main():
    app = PCSpecApp()
    app.mainloop()


if __name__ == "__main__":
    main()
