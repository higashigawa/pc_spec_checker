#!/usr/bin/env python3
"""
PC スペックチェッカー
モダンなダークテーマのGUIでPCのスペックを表示するツール
"""

import tkinter as tk
from tkinter import ttk, font
import platform
import subprocess
import threading
import time
import os
import re

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


def get_gpu_info():
    info = {}
    sys = platform.system()
    if sys == "Darwin":
        out = run_command(
            ["system_profiler", "SPDisplaysDataType", "-detailLevel", "mini"]
        )
        gpu_name = None
        for line in out.splitlines():
            line = line.strip()
            if "Chipset Model:" in line:
                gpu_name = line.split(":", 1)[1].strip()
            elif "VRAM" in line and gpu_name:
                vram = line.split(":", 1)[1].strip()
                info[gpu_name] = vram
                gpu_name = None
        if gpu_name:
            info[gpu_name] = "VRAM不明"
    elif sys == "Linux":
        out = run_command(["lspci"])
        for line in out.splitlines():
            if "VGA" in line or "3D" in line or "Display" in line:
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    info[parts[2].strip()] = ""
    elif sys == "Windows":
        out = run_command("wmic path win32_VideoController get Name,AdapterRAM /value")
        gpu = {}
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                gpu[k.strip()] = v.strip()
            elif not line.strip() and gpu:
                name = gpu.get("Name", "")
                ram  = gpu.get("AdapterRAM", "0")
                if name:
                    vram = f"{int(ram)/(1024**3):.1f} GB" if ram.isdigit() and int(ram) > 0 else "不明"
                    info[name] = vram
                gpu = {}
    return info


# ── ウィジェット構築 ─────────────────────────────

class PCSpecApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PC スペックチェッカー")
        self.configure(bg=BG)
        self.geometry("900x700")
        self.minsize(700, 500)
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
        self.after(0, lambda: self._render_kv(self.tabs["機種情報"], machine_data, "機種情報"))

        self._update_status("OS情報を取得中...")
        os_data  = get_os_info()
        self.after(0, lambda: self._render_kv(self.tabs["OS"], os_data))

        self._update_status("CPU情報を取得中...")
        cpu_data = get_cpu_info()
        self.after(0, lambda: self._render_cpu(self.tabs["CPU"], cpu_data))

        self._update_status("メモリ情報を取得中...")
        mem_data = get_memory_info()
        self.after(0, lambda: self._render_memory(self.tabs["メモリ"], mem_data))

        self._update_status("ストレージ情報を取得中...")
        disk_data = get_disk_info()
        self.after(0, lambda: self._render_disks(self.tabs["ストレージ"], disk_data))

        self._update_status("GPU情報を取得中...")
        gpu_data = get_gpu_info()
        self.after(0, lambda: self._render_kv(self.tabs["GPU"], gpu_data, "GPU"))

        self._update_status("ネットワーク情報を取得中...")
        net_data = get_network_info()
        self.after(0, lambda: self._render_network(self.tabs["ネットワーク"], net_data))

        self._update_status("完了")

    def _update_status(self, msg):
        self.after(0, lambda: self.status_lbl.config(text=msg))

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
