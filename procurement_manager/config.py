from pathlib import Path
import sys
import os
import json
import configparser

# Basic settings
DEBUG = True
HOST = "0.0.0.0"
PORT = 5000

# Root directory (repo in dev, EXE dir in packaged)
if getattr(sys, "frozen", False):
    DEBUG = False
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    ROOT_DIR = Path(__file__).resolve().parent.parent

# Logs
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

# Encoding
ENCODING_SJIS = "cp932"

# Default production file templates (overridable)
IF126_TEMPLATE = r"K:\\PW_Tableau\\IF126_納入日程管理\\NHSAPOTHIF126_{yyyymmdd}.txt"
IF130_TEMPLATE = r"K:\\PW_Tableau\\IF130_MRP警告リスト\\NHSAPOTHIF130_{yyyymmdd}.txt"
SHORT_TEMPLATE = r"K:\\PW_MM_FileShare\\05_短納期品一覧\\西神\\短納期品(西神)_{yyyymmdd}.csv"

# Sample search settings (for dev/sample mode)
SAMPLE_SEARCH_DIRS = [ROOT_DIR, ROOT_DIR.parent]
SAMPLE_IF126_PATTERNS = ["NHSAPOTHIF126_*.txt"]
SAMPLE_IF130_PATTERNS = ["NHSAPOTHIF130_*.txt"]
SAMPLE_SHORT_PATTERNS = ["*.csv"]

# Data locations
DATA_DIR = ROOT_DIR / "procurement_manager" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
USER_INPUTS_FILE = DATA_DIR / "user_inputs.json"
PROCESSED_DIR = DATA_DIR / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Date format
DATE_FMT_OUT = "%Y%m%d"

# External settings
SETTINGS_INI = ROOT_DIR / "pm_settings.ini"
SETTINGS_JSON = ROOT_DIR / "pm_settings.json"


def _drive_template_to_unc(tmpl: str) -> str:
    try:
        if os.name != "nt" or not isinstance(tmpl, str) or len(tmpl) < 3:
            return tmpl
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
    global IF126_TEMPLATE, IF130_TEMPLATE, SHORT_TEMPLATE, ENCODING_SJIS, HOST, PORT, LOG_DIR, LOG_FILE, SAMPLE_SEARCH_DIRS

    # 1) Environment variables
    IF126_TEMPLATE = os.getenv("PM_IF126_TEMPLATE", IF126_TEMPLATE)
    IF130_TEMPLATE = os.getenv("PM_IF130_TEMPLATE", IF130_TEMPLATE)
    SHORT_TEMPLATE = os.getenv("PM_SHORT_TEMPLATE", SHORT_TEMPLATE)
    enc_env = os.getenv("PM_ENCODING")
    if enc_env:
        ENCODING_SJIS = enc_env
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

    # 2) INI file
    if SETTINGS_INI.exists():
        cp = configparser.ConfigParser()
        try:
            cp.read(SETTINGS_INI, encoding="utf-8")
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
        # Apply UNC conversion
        IF126_TEMPLATE = _drive_template_to_unc(IF126_TEMPLATE)
        IF130_TEMPLATE = _drive_template_to_unc(IF130_TEMPLATE)
        SHORT_TEMPLATE = _drive_template_to_unc(SHORT_TEMPLATE)
        return

    # 3) JSON file
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

    # Final UNC conversion
    IF126_TEMPLATE = _drive_template_to_unc(IF126_TEMPLATE)
    IF130_TEMPLATE = _drive_template_to_unc(IF130_TEMPLATE)
    SHORT_TEMPLATE = _drive_template_to_unc(SHORT_TEMPLATE)


_apply_overrides()
