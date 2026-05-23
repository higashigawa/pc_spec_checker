#!/usr/bin/env python3
"""
Wi-Fi Analyzer  —  matplotlib チャンネルグラフ版
ベル曲線でWi-Fiチャンネルの信号強度をビジュアライズ
操作: [1] 2.4GHz  [2] 5GHz  [3] 両方  [R] 再スキャン  [Q] 終了
"""

import sys, subprocess, importlib

# ── 依存パッケージの自動インストール ─────────────────────────────────────────
def _ensure(pkg, import_name=None):
    name = import_name or pkg
    try:
        importlib.import_module(name)
    except ImportError:
        print(f"[setup] {pkg} をインストール中...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
            stdout=subprocess.DEVNULL,
        )
        print(f"[setup] {pkg} のインストール完了")

_ensure("matplotlib")
_ensure("numpy")

# ── GUI バックエンド自動選択 ──────────────────────────────────────────────────
import matplotlib

def _select_backend():
    candidates = [
        ("TkAgg",  "matplotlib.backends.backend_tkagg"),
        ("Qt5Agg", "matplotlib.backends.backend_qt5agg"),
        ("QtAgg",  "matplotlib.backends.backend_qtagg"),
        ("WXAgg",  "matplotlib.backends.backend_wxagg"),
        ("Agg",    "matplotlib.backends.backend_agg"),
    ]
    for name, module in candidates:
        try:
            importlib.import_module(module)
            matplotlib.use(name)
            # Agg は非インタラクティブなのでGUIとして使えない → スキップ
            if name == "Agg":
                continue
            print(f"[backend] {name} を使用")
            return name
        except Exception:
            continue

    # GUIバックエンドが見つからなかった → PyQt5 を自動インストール
    # (EXE化時は pip が使えないため警告のみ)
    import sys as _sys
    if not getattr(_sys, "frozen", False):
        print("[setup] PyQt5 をインストールします...")
        subprocess.check_call(
            [_sys.executable, "-m", "pip", "install", "PyQt5", "--quiet"],
            stdout=subprocess.DEVNULL,
        )
        print("[setup] PyQt5 のインストール完了")
        importlib.import_module("matplotlib.backends.backend_qt5agg")
        matplotlib.use("Qt5Agg")
        return "Qt5Agg"
    else:
        # EXE実行時: TkAgg を強制指定（--hidden-import で含めたはず）
        print("[backend] EXEモード: TkAgg を強制指定")
        matplotlib.use("TkAgg")
        return "TkAgg"

_select_backend()

# ── Linux はフォントが小さく見えるためスケール係数を設定 ─────────────────────
import platform as _platform
_FS = 2.0 if _platform.system() == "Linux" else 1.0  # フォントスケール係数

# ── 日本語フォント自動検出 ────────────────────────────────────────────────────
import matplotlib.font_manager as fm

def _setup_japanese_font():
    import platform, os, glob
    candidates = []
    system = platform.system()
    if system == "Windows":
        win_fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        for pat in ["meiryo.ttc", "meiryob.ttc", "YuGothR.ttc", "YuGothM.ttc",
                    "msgothic.ttc", "msmincho.ttc"]:
            path = os.path.join(win_fonts, pat)
            if os.path.exists(path):
                candidates.append(path)
    elif system == "Darwin":
        for pat in ["/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
                    "/Library/Fonts/Arial Unicode.ttf"]:
            if os.path.exists(pat):
                candidates.append(pat)
    else:
        candidates += glob.glob("/usr/share/fonts/**/NotoSansCJK*.ttc", recursive=True)
        candidates += glob.glob("/usr/share/fonts/**/NotoSansCJK*.otf", recursive=True)
    for path in candidates:
        try:
            fm.fontManager.addfont(path)
            prop = fm.FontProperties(fname=path)
            matplotlib.rcParams["font.family"] = prop.get_name()
            return
        except Exception:
            continue

_setup_japanese_font()

# ── 通常の import ─────────────────────────────────────────────────────────────
import random
from datetime import datetime
from dataclasses import dataclass, field

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.widgets import RadioButtons
from matplotlib.animation import FuncAnimation
import numpy as np

# ── カラーパレット ────────────────────────────────────────────────────────────
COLORS = [
    "#00FF41", "#FF4444", "#4499FF", "#FFEE00", "#FF44FF",
    "#00EEFF", "#FF8800", "#BB44FF", "#FF4488", "#88FF44",
]

# ── データモデル ──────────────────────────────────────────────────────────────
@dataclass
class Network:
    ssid: str
    bssid: str
    signal: int
    channel: int
    band: str
    security: str
    vendor: str
    connected: bool = False
    color: str = "#00FF41"
    _hist: list = field(default_factory=list)

    def __post_init__(self):
        self._hist = [self.signal]
        self._base_signal = self.signal  # スキャン値の基準

    def fluctuate(self):
        # 基準値から±5dBm以内に収まるよう変動
        lo = max(-95, self._base_signal - 5)
        hi = min(-20, self._base_signal + 5)
        self.signal = max(lo, min(hi, self.signal + random.randint(-2, 2)))
        self._hist.append(self.signal)
        if len(self._hist) > 60:
            self._hist.pop(0)

    def reset_base(self, new_signal: int):
        """スキャン時に基準値をリセット"""
        self._base_signal = new_signal
        self.signal = new_signal

    @property
    def freq_mhz(self) -> int:
        if self.band == "2.4GHz":
            return 2412 + (self.channel - 1) * 5
        # IEEE 802.11 標準: 5000 + ch * 5 (全帯域共通)
        return 5000 + self.channel * 5

    @property
    def bandwidth_mhz(self) -> int:
        return 40 if self.band == "5GHz" else 20


# 5GHz 全チャンネル定義 (IEEE 802.11)
CH5_BANDS = {
    "UNII-1":  [36, 40, 44, 48],
    "UNII-2A": [52, 56, 60, 64],
    "UNII-2C": [100,104,108,112,116,120,124,128,132,136,140,144],
    "UNII-3":  [149,153,157,161,165],
    "UNII-4":  [169,173,177],
}
ALL_5G_CHANNELS = [ch for chs in CH5_BANDS.values() for ch in chs]


def get_connected_ssids() -> set:
    """OS APIで現在接続中のSSIDを取得する"""
    import platform, subprocess, re
    connected = set()
    system = platform.system()
    try:
        if system == "Windows":
            # netsh wlan show interfaces で接続中SSIDを取得
            out = subprocess.check_output(
                ["netsh", "wlan", "show", "interfaces"],
                encoding="utf-8", errors="ignore",
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            for line in out.splitlines():
                m = re.search(r"^\s*SSID\s*:\s*(.+)$", line)
                if m and "BSSID" not in line:
                    connected.add(m.group(1).strip())
        elif system == "Darwin":
            # macOS: airport コマンド
            out = subprocess.check_output(
                ["/System/Library/PrivateFrameworks/Apple80211.framework"
                 "/Versions/Current/Resources/airport", "-I"],
                encoding="utf-8", errors="ignore",
            )
            for line in out.splitlines():
                m = re.search(r"^\s*SSID\s*:\s*(.+)$", line)
                if m:
                    connected.add(m.group(1).strip())
        else:
            # Linux: nmcli または iwgetid
            try:
                out = subprocess.check_output(
                    ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"],
                    encoding="utf-8", errors="ignore",
                )
                for line in out.splitlines():
                    if line.startswith("yes:"):
                        connected.add(line[4:].strip())
            except FileNotFoundError:
                out = subprocess.check_output(
                    ["iwgetid", "-r"],
                    encoding="utf-8", errors="ignore",
                )
                ssid = out.strip()
                if ssid:
                    connected.add(ssid)
    except Exception:
        pass  # 取得失敗時は空セット (✓なし)
    return connected


def _pct_to_dbm(pct: int) -> int:
    """Windowsの信号強度(%)をdBmに変換"""
    pct = max(0, min(100, pct))
    return int(-100 + pct * 0.7)   # 0%=-100dBm, 100%=-30dBm


def scan_networks() -> list:
    """OSコマンドで周辺Wi-Fiをスキャンして Network リストを返す"""
    import platform, subprocess, re
    system = platform.system()
    nets = []
    color_map: dict = {}  # bssid -> color (同一SSIDでも区別)

    def assign_color(bssid: str) -> str:
        if bssid not in color_map:
            color_map[bssid] = COLORS[len(color_map) % len(COLORS)]
        return color_map[bssid]

    try:
        if system == "Windows":
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            out = subprocess.check_output(
                ["netsh", "wlan", "show", "networks", "mode=bssid"],
                encoding="cp932", errors="ignore",
                creationflags=flags,
            )
            # ブロックごとに分割して解析
            blocks = re.split(r"\nSSID\s+\d+\s*:", out)
            for block in blocks[1:]:
                lines = block.splitlines()
                ssid = lines[0].strip() if lines else "Unknown"
                security, band, channel, signal, bssid = "WPA2", "2.4GHz", 6, -70, "00:00:00:00:00:00"
                for line in lines:
                    line = line.strip()
                    m = re.match(r"認証\s*:\s*(.+)", line)
                    if m: security = m.group(1).strip()
                    m = re.match(r"Authentication\s*:\s*(.+)", line, re.I)
                    if m: security = m.group(1).strip()
                    m = re.match(r"(?:ラジオの種類|Radio type)\s*:\s*(.+)", line, re.I)
                    if m:
                        rt = m.group(1).strip()
                        if "5" in rt or "ac" in rt.lower() or "ax" in rt.lower():
                            band = "5GHz"
                        else:
                            band = "2.4GHz"
                    m = re.match(r"(?:チャネル|Channel)\s*:\s*(\d+)", line, re.I)
                    if m: channel = int(m.group(1))
                    m = re.match(r"(?:信号|Signal)\s*:\s*(\d+)%", line, re.I)
                    if m: signal = _pct_to_dbm(int(m.group(1)))
                    m = re.match(r"BSSID\s+\d+\s*:\s*([\w:]+)", line, re.I)
                    if m: bssid = m.group(1).strip()
                if not ssid:
                    continue
                nets.append(Network(
                    ssid=ssid, bssid=bssid, signal=signal,
                    channel=channel, band=band,
                    security=security, vendor="",
                    color=assign_color(bssid),
                ))

        elif system == "Darwin":
            out = subprocess.check_output(
                ["/System/Library/PrivateFrameworks/Apple80211.framework"
                 "/Versions/Current/Resources/airport", "-s"],
                encoding="utf-8", errors="ignore",
            )
            for line in out.splitlines()[1:]:
                parts = line.split()
                if len(parts) < 7:
                    continue
                ssid = parts[0]
                bssid = parts[1]
                try: signal = int(parts[2])
                except: signal = -80
                try: channel = int(parts[3].split(",")[0])
                except: channel = 6
                band = "5GHz" if channel > 14 else "2.4GHz"
                security = parts[6] if len(parts) > 6 else "WPA2"
                nets.append(Network(
                    ssid=ssid, bssid=bssid, signal=signal,
                    channel=channel, band=band,
                    security=security, vendor="",
                    color=assign_color(bssid),
                ))

        else:
            # Linux: nmcli
            # -t 出力はBSSIDの":" が "\:" にエスケープされるため正しく処理する
            out = subprocess.check_output(
                ["nmcli", "-t", "-f",
                 "SSID,BSSID,SIGNAL,CHAN,FREQ,SECURITY",
                 "dev", "wifi", "list"],
                encoding="utf-8", errors="ignore",
            )
            for line in out.splitlines():
                if not line.strip():
                    continue
                # "\:" を一時プレースホルダ文字列に置換してから ":" で分割
                MARK = "<<COLON>>"
                tmp = line.replace("\:", MARK)
                parts = tmp.split(":")
                if len(parts) < 6:
                    continue
                # プレースホルダを ":" に戻す
                parts = [p.replace(MARK, ":") for p in parts]
                ssid     = parts[0].strip()
                bssid    = parts[1].strip()
                sig_str  = parts[2].strip()
                ch_str   = parts[3].strip()
                freq_str = parts[4].strip()
                sec      = ":".join(parts[5:]).strip()
                try: signal = _pct_to_dbm(int(sig_str))
                except: signal = -80
                try: channel = int(ch_str)
                except: channel = 6
                band = "5GHz" if channel > 14 else "2.4GHz"
                nets.append(Network(
                    ssid=ssid or "(hidden)", bssid=bssid, signal=signal,
                    channel=channel, band=band,
                    security=sec or "WPA2", vendor="",
                    color=assign_color(bssid),
                ))

    except Exception as e:
        print(f"[scan] スキャン失敗: {e}")

    # スキャン結果が空なら最低限のダミーを返す
    if not nets:
        print("[scan] ネットワークが見つかりませんでした（デモデータを使用）")
        nets = _demo_networks()
    return nets


def _demo_networks() -> list:
    """スキャン失敗時のフォールバック用デモデータ"""
    return [
        Network("Demo_2.4G", "AA:BB:01", -65, 6,  "2.4GHz", "WPA2", "", color=COLORS[0]),
        Network("Demo_5G",   "AA:BB:02", -70, 36, "5GHz",   "WPA2", "", color=COLORS[1]),
    ]


def make_networks() -> list:
    """起動時スキャン"""
    return scan_networks()


def bell_curve(cx, sig, bw, x):
    sigma = bw / 2.5
    return -100.0 + (sig + 100.0) * np.exp(-0.5 * ((x - cx) / sigma) ** 2)


# ── グラフ描画ヘルパー ────────────────────────────────────────────────────────
def draw_band_axes(ax_main, nets, band_label,
                   BG, PANEL, GRID, TICK, LABEL):
    """1つの帯域分のメイングラフを描画する共通関数"""
    is_5g = all(n.band == "5GHz" for n in nets)

    # ── メイングラフ ────────────────────────────────────────────────────
    freqs = [n.freq_mhz for n in nets]
    fmin, fmax = min(freqs) - 80, max(freqs) + 80

    ax_main.set_facecolor(PANEL)
    ax_main.set_xlim(fmin, fmax); ax_main.set_ylim(-100, -20)
    for dbm in range(-90, -20, 10):
        ax_main.axhline(dbm, color=GRID, lw=0.6, zorder=0)
    ax_main.set_yticks(range(-90, -20, 10))
    ax_main.set_yticklabels([str(v) for v in range(-90, -20, 10)],
                            color=TICK, fontsize=int(9.0 * _FS))
    ax_main.set_ylabel("シグナル強度 [dBm]", color=LABEL, fontsize=int(9.0 * _FS), labelpad=6)

    ch_ticks, ch_labels = [], []
    if is_5g:
        for ch in ALL_5G_CHANNELS:
            f = 5000 + ch * 5
            if fmin <= f <= fmax:
                ch_ticks.append(f); ch_labels.append(str(ch))
    else:
        for ch in range(1, 14):
            f = 2412 + (ch - 1) * 5
            if fmin <= f <= fmax:
                ch_ticks.append(f); ch_labels.append(str(ch))
    ax_main.set_xticks(ch_ticks)
    ax_main.set_xticklabels(ch_labels, color=LABEL, fontsize=int(8.0 * _FS),
                             rotation=45, ha="right")
    ax_main.set_xlabel("Wifi チャンネル", color=LABEL, fontsize=int(9.0 * _FS), labelpad=4)
    for sp in ax_main.spines.values(): sp.set_color("#333333")
    ax_main.tick_params(axis="both", length=0)

    x = np.linspace(fmin, fmax, 4000)
    used: dict = {}
    for n in sorted(nets, key=lambda n: n.signal):
        y = bell_curve(n.freq_mhz, n.signal, n.bandwidth_mhz, x)
        ax_main.fill_between(x, y, -100, color=n.color,
                             alpha=0.22 if n.connected else 0.16, zorder=2)
        ax_main.plot(x, y, color=n.color,
                     lw=2.2 if n.connected else 1.6, alpha=0.95, zorder=3)
        lx, ly = n.freq_mhz, n.signal + 2.0
        key = (round(lx / 15), round(ly / 4))
        while used.get(key):
            ly -= 5; key = (round(lx / 15), round(ly / 4))
        used[key] = True
        ax_main.text(lx, ly, f"{n.ssid}{' ✓' if n.connected else ''}",
                     color=n.color, fontsize=int(8.5 * _FS), ha="center", va="bottom",
                     fontweight="bold" if n.connected else "normal", zorder=4)

    # UNII サブバンド区切り線 (5GHz のみ)
    if is_5g:
        unii_boundaries = [5250, 5470, 5725, 5850]  # 各UNII帯の境界MHz
        unii_labels     = ["UNII-1","UNII-2A","UNII-2C","UNII-3","UNII-4"]
        prev_f = fmin
        for i, boundary in enumerate(unii_boundaries + [fmax]):
            mid = (prev_f + min(boundary, fmax)) / 2
            if fmin < mid < fmax:
                ax_main.text(mid, -21.5, unii_labels[i],
                             color="#555555", fontsize=int(7.5 * _FS),
                             ha="center", va="top", style="italic")
            if fmin < boundary < fmax:
                ax_main.axvline(boundary, color="#444444", lw=0.8,
                                linestyle="--", zorder=1)
            prev_f = boundary

    ax_main.set_title(
        f"Wifi Analyzer   {band_label}   {len(nets)} ネットワーク"
        f"   {datetime.now().strftime('%H:%M:%S')}",
        color="#CCCCCC", fontsize=int(10.0 * _FS), pad=6, loc="left",
    )

    seen: set = set(); handles = []
    for n in sorted(nets, key=lambda n: n.signal, reverse=True):
        uid = n.ssid + n.bssid
        if uid not in seen:
            seen.add(uid)
            handles.append(mpatches.Patch(color=n.color,
                                          label=f"{n.ssid}   {n.signal} dBm"))
    ax_main.legend(handles=handles,
                   bbox_to_anchor=(1.0, 0.93),
                   loc="upper right",
                   borderaxespad=0,
                   fontsize=int(7.5 * _FS),
                   facecolor="#222222", edgecolor="#444444",
                   labelcolor="white", framealpha=0.88, ncol=3)


# ── メインアプリ ──────────────────────────────────────────────────────────────
class WifiAnalyzer:
    BG    = "#111111"
    PANEL = "#1A1A1A"
    GRID  = "#2A2A2A"
    TICK  = "#666666"
    LABEL = "#AAAAAA"

    BAND_LABELS = ["2.4 GHz", "5 GHz", "両方"]
    BAND_KEYS   = ["2.4GHz",  "5GHz",  "両方"]

    def __init__(self):
        self.all_nets   = make_networks()
        # 起動時に接続状態を反映
        connected_ssids = get_connected_ssids()
        for n in self.all_nets:
            n.connected = n.ssid in connected_ssids
        self.band_index = 1   # デフォルト: 5GHz
        self._tick      = 0

        plt.style.use("dark_background")
        self.fig = plt.figure(figsize=(15, 9), facecolor=self.BG)
        try:
            self.fig.canvas.manager.set_window_title("Wi-Fi Analyzer")
        except Exception:
            pass

        self._build_layout()
        self.fig.canvas.mpl_connect("key_press_event", self._on_key)
        self.ani = FuncAnimation(
            self.fig, self._update, interval=1000, cache_frame_data=False
        )

    # ── レイアウト構築 ────────────────────────────────────────────────────────
    def _build_layout(self):
        """バンドモードに応じて axes を動的に再構成する"""
        self.fig.clear()
        key = self.BAND_KEYS[self.band_index]

        # 外側: 左(ラジオ) + 右(グラフエリア)
        outer = gridspec.GridSpec(
            1, 2, figure=self.fig,
            width_ratios=[1, 13],
            left=0.01, right=0.99, top=0.97, bottom=0.06,
            wspace=0.02,
        )

        # ── 左: RadioButtons ──────────────────────────────────────────
        self.ax_radio = self.fig.add_subplot(outer[0, 0])
        self.ax_radio.set_facecolor(self.PANEL)
        for sp in self.ax_radio.spines.values():
            sp.set_color("#333333")
        self.ax_radio.tick_params(
            left=False, bottom=False, labelleft=False, labelbottom=False)
        self.ax_radio.text(0.5, 0.97, "バンド", transform=self.ax_radio.transAxes,
                           ha="center", va="top", color=self.LABEL, fontsize=int(9.0 * _FS))

        self.radio = RadioButtons(
            self.ax_radio,
            labels=self.BAND_LABELS,
            active=self.band_index,
            activecolor="#00EEFF",
        )
        for lbl in self.radio.labels:
            lbl.set_color(self.LABEL); lbl.set_fontsize(int(9 * _FS))
        self.radio.on_clicked(self._on_band_click)

        # ── 右: グラフエリア ──────────────────────────────────────────
        right = outer[0, 1]

        if key == "両方":
            # 1行 × 2列: 左=2.4GHz、右=5GHz
            inner = gridspec.GridSpecFromSubplotSpec(
                1, 2,
                subplot_spec=right,
                wspace=0.06,
            )
            self.ax_main24 = self.fig.add_subplot(inner[0, 0])
            self.ax_main5  = self.fig.add_subplot(inner[0, 1])
        else:
            # 1列のみ
            inner = gridspec.GridSpecFromSubplotSpec(
                1, 1,
                subplot_spec=right,
            )
            self.ax_main = self.fig.add_subplot(inner[0, 0])

    # ── フィルタ ──────────────────────────────────────────────────────────────
    def _nets(self, band=None):
        b = band or self.BAND_KEYS[self.band_index]
        if b == "両方":
            return self.all_nets
        return [n for n in self.all_nets if n.band == b]

    # ── アニメーション更新 ────────────────────────────────────────────────────
    def _update(self, frame):
        self._tick += 1
        # 5秒ごとに再スキャン
        if self._tick % 5 == 0:
            self._scan()
            self._redraw()

    def _scan(self):
        """Wi-Fiをスキャンしてネットワークリストを更新"""
        nets = scan_networks()
        connected_ssids = get_connected_ssids()
        # 既存ネットワークの情報を引き継ぐ (color・履歴)
        old_map = {n.bssid: n for n in self.all_nets}
        for n in nets:
            if n.bssid in old_map:
                old_n = old_map[n.bssid]
                n.color = old_n.color        # 色を維持
                n._hist = old_n._hist        # 履歴を引き継ぎ
            n.reset_base(n.signal)           # 基準値をスキャン結果にリセット
            n._hist.append(n.signal)
            if len(n._hist) > 60:
                n._hist.pop(0)
            n.connected = n.ssid in connected_ssids
        self.all_nets = nets

    def _redraw(self):
        key = self.BAND_KEYS[self.band_index]
        if key == "両方":
            for ax in [self.ax_main24, self.ax_main5]:
                ax.cla()
            nets24 = self._nets("2.4GHz")
            nets5  = self._nets("5GHz")
            draw_band_axes(self.ax_main24, nets24, "2.4 GHz",
                           self.BG, self.PANEL, self.GRID, self.TICK, self.LABEL)
            draw_band_axes(self.ax_main5,  nets5,  "5 GHz",
                           self.BG, self.PANEL, self.GRID, self.TICK, self.LABEL)
        else:
            self.ax_main.cla()
            draw_band_axes(self.ax_main, self._nets(),
                           self.BAND_LABELS[self.band_index],
                           self.BG, self.PANEL, self.GRID, self.TICK, self.LABEL)


    # ── バンド切り替え ────────────────────────────────────────────────────────
    def _on_band_click(self, label):
        self.band_index = self.BAND_LABELS.index(label)
        self._build_layout()
        self._redraw()
        self.fig.canvas.draw_idle()

    # ── キー操作 ─────────────────────────────────────────────────────────────
    def _on_key(self, event):
        if event.key in ("q", "escape", "ctrl+c"):
            plt.close("all")
        elif event.key == "r":
            for n in self.all_nets:
                n.fluctuate()
            self._redraw()
            self.fig.canvas.draw_idle()
        elif event.key in ("1", "2", "3"):
            idx = int(event.key) - 1
            self.band_index = idx
            self._build_layout()
            self._redraw()
            self.radio.set_active(idx)
            self.fig.canvas.draw_idle()

    def run(self):
        # 描画完了後に最大化 (plt.show より前に window が存在する必要あり)
        def _maximize(event):
            try:
                mgr = self.fig.canvas.manager
                try:
                    mgr.window.showMaximized()       # Qt
                except AttributeError:
                    try:
                        mgr.window.state("zoomed")   # Tk (Windows)
                    except AttributeError:
                        try:
                            mgr.frame.Maximize(True) # WX
                        except AttributeError:
                            pass
            except Exception:
                pass
            # 一度だけ実行すれば十分なので切断
            self.fig.canvas.mpl_disconnect(self._maximize_cid)

        self._maximize_cid = self.fig.canvas.mpl_connect("draw_event", _maximize)
        plt.show()


# ── エントリポイント ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Wi-Fi Analyzer を起動中...")
    print("  バンド切替: [1] 2.4GHz  [2] 5GHz  [3] 両方")
    print("  [R] 再スキャン   [Q] 終了")
    WifiAnalyzer().run()
