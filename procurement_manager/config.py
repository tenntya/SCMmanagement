from pathlib import Path
import sys
import os
import json
import configparser


# 基本設定
DEBUG = True
HOST = "0.0.0.0"  # 他PCからのアクセスを許可
PORT = 5000

# ルートディレクトリ判定（通常: リポジトリ直下 / EXE: 実行ファイルの隣）
if getattr(sys, "frozen", False):
    DEBUG = False
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    ROOT_DIR = Path(__file__).resolve().parent.parent

# ログ
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

# ファイルエンコーディング（既定: Windows Shift-JIS）
ENCODING_SJIS = "cp932"

# 本番ファイルパス（デフォルト値）。外部設定と環境変数で上書き可能。
IF126_TEMPLATE = r"K:\\PW_Tableau\\IF126_納期日程管理\NHSAPOTHIF126_{yyyymmdd}.txt"
SHORT_TEMPLATE = r"K:\\PW_MM_FileShare\\05_短納期品一覧\\西神\\短納期品(西神)_{yyyymmdd}.csv"

# サンプルファイル探索（EXE隣とその親、開発時はルートも見る）
SAMPLE_SEARCH_DIRS = [ROOT_DIR, ROOT_DIR.parent]
SAMPLE_IF126_PATTERNS = ["NHSAPOTHIF126_*.txt"]
SAMPLE_SHORT_PATTERNS = ["*.csv"]  # 日本語名のCSVも拾う

# データ保存
DATA_DIR = ROOT_DIR / "procurement_manager" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
USER_INPUTS_FILE = DATA_DIR / "user_inputs.json"
PROCESSED_DIR = DATA_DIR / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# 日付フォーマット
DATE_FMT_OUT = "%Y%m%d"


# 外部設定の読込（pm_settings.ini または pm_settings.json、環境変数）
SETTINGS_INI = ROOT_DIR / "pm_settings.ini"
SETTINGS_JSON = ROOT_DIR / "pm_settings.json"


def _drive_template_to_unc(tmpl: str) -> str:
    try:
        if os.name != "nt" or not isinstance(tmpl, str) or len(tmpl) < 3:
            return tmpl
        # like 'X:\\...'
        if tmpl[1:3] != ":\\":
            return tmpl
        drive = tmpl[0].upper()
        try:
            import winreg  # type: ignore
        except Exception:
            return tmpl
        key_path = f"Network\\{drive}"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
                remote, _ = winreg.QueryValueEx(k, "RemotePath")
        except Exception:
            return tmpl
        if not remote:
            return tmpl
        remote = str(remote).rstrip("\\/")
        rest = tmpl[2:].lstrip("\\/")
        unc = remote + ("\\" + rest if rest else "")
        return unc
    except Exception:
        return tmpl


def _apply_overrides() -> None:
    global IF126_TEMPLATE, SHORT_TEMPLATE, ENCODING_SJIS, HOST, PORT, LOG_DIR, LOG_FILE, SAMPLE_SEARCH_DIRS, IF130_TEMPLATE

    # 1) 環境変数で上書き
    IF126_TEMPLATE = os.getenv("PM_IF126_TEMPLATE", IF126_TEMPLATE)
    IF130_TEMPLATE = os.getenv("PM_IF130_TEMPLATE", globals().get("IF130_TEMPLATE", r"K:\\PW_Tableau\\IF130_MRP隴ｦ蜻翫Μ繧ｹ繝・\\NHSAPOTHIF130_{yyyymmdd}.txt"))
    SHORT_TEMPLATE = os.getenv("PM_SHORT_TEMPLATE", SHORT_TEMPLATE)
    ENCODING_SJIS = os.getenv("PM_ENCODING", ENCODING_SJIS)
    host_env = os.getenv("PM_HOST")
    port_env = os.getenv("PM_PORT")
    if host_env:
        HOST = host_env
    if port_env:
        try:
            PORT = int(port_env)
        except Exception:
            pass
    sample_dirs_env = os.getenv("PM_SAMPLE_DIRS")
    if sample_dirs_env:
        SAMPLE_SEARCH_DIRS = [Path(s.strip()) for s in sample_dirs_env.split(";") if s.strip()]

    # 2) INI ファイルで上書き
    if SETTINGS_INI.exists():
        cp = configparser.ConfigParser()
        try:
            cp.read(SETTINGS_INI, encoding="utf-8-sig")
        except Exception:
            cp.read(SETTINGS_INI)
        if cp.has_section("paths"):
            IF126_TEMPLATE = cp.get("paths", "IF126_TEMPLATE", fallback=IF126_TEMPLATE)
            IF130_TEMPLATE = cp.get("paths", "IF130_TEMPLATE", fallback=IF130_TEMPLATE)
            SHORT_TEMPLATE = cp.get("paths", "SHORT_TEMPLATE", fallback=SHORT_TEMPLATE)
            sample_dirs = cp.get("paths", "SAMPLE_DIRS", fallback=None)
            if sample_dirs:
                SAMPLE_SEARCH_DIRS = [Path(s.strip()) for s in sample_dirs.split(";") if s.strip()]
        if cp.has_section("encoding"):
            ENCODING_SJIS = cp.get("encoding", "file", fallback=ENCODING_SJIS)
        if cp.has_section("server"):
            HOST = cp.get("server", "HOST", fallback=HOST)
            try:
                PORT = cp.getint("server", "PORT", fallback=PORT)
            except Exception:
                pass
        if cp.has_section("logs"):
            logdir = cp.get("logs", "LOG_DIR", fallback=None)
            if logdir:
                LOG_DIR = Path(logdir)
                LOG_DIR.mkdir(parents=True, exist_ok=True)
                LOG_FILE = LOG_DIR / "app.log"
        # Convert drive-letter templates to UNC if mapping exists
        IF126_TEMPLATE = _drive_template_to_unc(IF126_TEMPLATE)
        IF130_TEMPLATE = _drive_template_to_unc(IF130_TEMPLATE)
        SHORT_TEMPLATE = _drive_template_to_unc(SHORT_TEMPLATE)
        return

    # 3) JSON ファイルで上書き（任意）
    if SETTINGS_JSON.exists():
        try:
            d = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        except Exception:
            d = {}
        paths = d.get("paths", {}) if isinstance(d.get("paths"), dict) else d
        IF126_TEMPLATE = str(paths.get("IF126_TEMPLATE", IF126_TEMPLATE))
        IF130_TEMPLATE = str(paths.get("IF130_TEMPLATE", IF130_TEMPLATE))
        SHORT_TEMPLATE = str(paths.get("SHORT_TEMPLATE", SHORT_TEMPLATE))
        enc = d.get("encoding", {})
        if isinstance(enc, dict):
            ENCODING_SJIS = str(enc.get("file", ENCODING_SJIS))
        server = d.get("server", {})
        if isinstance(server, dict):
            HOST = str(server.get("HOST", HOST))
            try:
                PORT = int(server.get("PORT", PORT))
            except Exception:
                pass
        logs = d.get("logs", {})
        if isinstance(logs, dict) and logs.get("LOG_DIR"):
            LOG_DIR = Path(str(logs["LOG_DIR"]))
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            LOG_FILE = LOG_DIR / "app.log"
    # Convert drive-letter templates to UNC if mapping exists (final)
    IF126_TEMPLATE = _drive_template_to_unc(IF126_TEMPLATE)
    IF130_TEMPLATE = _drive_template_to_unc(IF130_TEMPLATE)
    SHORT_TEMPLATE = _drive_template_to_unc(SHORT_TEMPLATE)


_apply_overrides()
