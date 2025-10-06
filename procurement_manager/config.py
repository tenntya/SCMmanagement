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

def _unique_paths(paths):
    seen = set()
    result = []
    for raw in paths:
        if not raw:
            continue
        try:
            candidate = Path(raw)
        except Exception:
            continue
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _ensure_writable(path: Path) -> bool:
    test = None
    try:
        path.mkdir(parents=True, exist_ok=True)
        test = path / ".__permcheck"
        with test.open("w", encoding="utf-8") as fh:
            fh.write("")
        test.unlink()
        return True
    except Exception:
        if test and test.exists():
            try:
                test.unlink()
            except Exception:
                pass
        return False


def _first_writable(paths):
    for candidate in _unique_paths(paths):
        if _ensure_writable(candidate):
            return candidate
    raise RuntimeError("no writable directory available from candidates")




def _resolve_data_root() -> Path:
    env_dir = os.getenv("PM_DATA_DIR") or os.getenv("PM_DATA_ROOT")
    if env_dir:
        return _first_writable([env_dir])

    if getattr(sys, "frozen", False):
        dist_root = ROOT_DIR / "procurement_manager"
        if _ensure_writable(dist_root):
            return dist_root
        raise RuntimeError(f"cannot write to dist data directory: {dist_root}")

    candidates = [ROOT_DIR / "procurement_manager"]
    if os.name == "nt":
        local_app = os.getenv("LOCALAPPDATA")
        if local_app:
            candidates.append(Path(local_app) / "SCMmanagement")
        roaming = os.getenv("APPDATA")
        if roaming:
            candidates.append(Path(roaming) / "SCMmanagement")
    candidates.append(Path.home() / ".scmmanagement")
    return _first_writable(candidates)

def _resolve_log_dir(data_root: Path) -> Path:
    override = os.getenv("PM_LOG_DIR")
    candidates = [override] if override else []
    candidates.append(ROOT_DIR / "logs")
    candidates.append(data_root / "logs")
    if os.name == "nt":
        local_app = os.getenv("LOCALAPPDATA")
        if local_app:
            candidates.append(Path(local_app) / "SCMmanagement" / "logs")
    candidates.append(Path.home() / ".scmmanagement" / "logs")
    return _first_writable(candidates)

# ログ
DATA_ROOT = _resolve_data_root()
DATA_DIR = DATA_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
USER_INPUTS_FILE = DATA_DIR / "user_inputs.json"
PROCESSED_DIR = DATA_ROOT / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = _resolve_log_dir(DATA_ROOT)
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

# ファイルエンコーディング（既定: Windows Shift-JIS）
ENCODING_SJIS = "cp932"

# 日付フォーマット
DATE_FMT_OUT = "%Y%m%d"


# 本番ファイルパス（デフォルト値）。外部設定と環境変数で上書き可能。
IF126_TEMPLATE = r"K:\\PW_Tableau\\IF126_納期日程管理\\NHSAPOTHIF126_{yyyymmdd}.txt"
IF130_TEMPLATE = r"K:\\PW_Tableau\\IF130_MRP警告リスト\\NHSAPOTHIF130_{yyyymmdd}.txt"
SHORT_TEMPLATE = r"K:\\PW_MM_FileShare\\05_短納期品一覧\\西神\\短納期品(西神)_{yyyymmdd}.csv"

# サンプルファイル探索（EXE隣とその親、開発時はルートも見る）
SAMPLE_SEARCH_DIRS = [ROOT_DIR, ROOT_DIR.parent]
SAMPLE_IF126_PATTERNS = ["NHSAPOTHIF126_*.txt"]
SAMPLE_SHORT_PATTERNS = ["*.csv"]  # 日本語名のCSVも拾う

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


def _set_user_inputs_file(raw) -> None:
    global USER_INPUTS_FILE
    if raw is None:
        return
    text_value = str(raw).strip()
    if not text_value:
        return
    normalized = _drive_template_to_unc(text_value)
    candidate = Path(normalized).expanduser()
    if not candidate.is_absolute():
        candidate = DATA_DIR / candidate
    parent = candidate.parent
    if not _ensure_writable(parent):
        raise RuntimeError(f"cannot write to user inputs directory: {parent}")
    USER_INPUTS_FILE = candidate


def _apply_overrides() -> None:
    global IF126_TEMPLATE, SHORT_TEMPLATE, ENCODING_SJIS, HOST, PORT, LOG_DIR, LOG_FILE, SAMPLE_SEARCH_DIRS, IF130_TEMPLATE, USER_INPUTS_FILE

    # 1) 環境変数で上書き (環境変数が最優先)
    env_if126 = os.getenv("PM_IF126_TEMPLATE")
    env_if130 = os.getenv("PM_IF130_TEMPLATE")
    env_short = os.getenv("PM_SHORT_TEMPLATE")
    env_encoding = os.getenv("PM_ENCODING")
    env_host = os.getenv("PM_HOST")
    env_port = os.getenv("PM_PORT")
    env_sample_dirs = os.getenv("PM_SAMPLE_DIRS")
    env_user_inputs = os.getenv("PM_USER_INPUTS_FILE")

    if env_if126:
        IF126_TEMPLATE = env_if126
    if env_if130:
        IF130_TEMPLATE = env_if130
    if env_short:
        SHORT_TEMPLATE = env_short
    if env_encoding:
        ENCODING_SJIS = env_encoding
    if env_host:
        HOST = env_host
    if env_port:
        try:
            PORT = int(env_port)
        except Exception:
            pass
    if env_sample_dirs:
        SAMPLE_SEARCH_DIRS = [Path(s.strip()) for s in env_sample_dirs.split(";") if s.strip()]
    if env_user_inputs:
        _set_user_inputs_file(env_user_inputs)

    # 2) INI ファイルで上書き (環境変数が未設定の項目のみ)
    if SETTINGS_INI.exists():
        cp = configparser.ConfigParser()
        try:
            cp.read(SETTINGS_INI, encoding="utf-8-sig")
        except Exception:
            cp.read(SETTINGS_INI)
        if cp.has_section("paths"):
            if not env_if126:
                IF126_TEMPLATE = cp.get("paths", "IF126_TEMPLATE", fallback=IF126_TEMPLATE)
            if not env_if130:
                IF130_TEMPLATE = cp.get("paths", "IF130_TEMPLATE", fallback=IF130_TEMPLATE)
            if not env_short:
                SHORT_TEMPLATE = cp.get("paths", "SHORT_TEMPLATE", fallback=SHORT_TEMPLATE)
            if not env_sample_dirs:
                sample_dirs = cp.get("paths", "SAMPLE_DIRS", fallback=None)
                if sample_dirs:
                    SAMPLE_SEARCH_DIRS = [Path(s.strip()) for s in sample_dirs.split(";") if s.strip()]
            if not env_user_inputs:
                user_inputs_path = cp.get("paths", "USER_INPUTS_FILE", fallback=None)
                if user_inputs_path:
                    _set_user_inputs_file(user_inputs_path)
        if cp.has_section("encoding") and not env_encoding:
            ENCODING_SJIS = cp.get("encoding", "file", fallback=ENCODING_SJIS)
        if cp.has_section("server"):
            if not env_host:
                HOST = cp.get("server", "HOST", fallback=HOST)
            if not env_port:
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

    # 3) JSON ファイルで上書き (環境変数が未設定の項目のみ)
    if SETTINGS_JSON.exists():
        try:
            d = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        except Exception:
            d = {}
        paths = d.get("paths", {}) if isinstance(d.get("paths"), dict) else d
        if not env_if126:
            IF126_TEMPLATE = str(paths.get("IF126_TEMPLATE", IF126_TEMPLATE))
        if not env_if130:
            IF130_TEMPLATE = str(paths.get("IF130_TEMPLATE", IF130_TEMPLATE))
        if not env_short:
            SHORT_TEMPLATE = str(paths.get("SHORT_TEMPLATE", SHORT_TEMPLATE))
        if not env_user_inputs:
            user_inputs_path = paths.get("USER_INPUTS_FILE")
            if user_inputs_path:
                _set_user_inputs_file(user_inputs_path)
        enc = d.get("encoding", {})
        if isinstance(enc, dict) and not env_encoding:
            ENCODING_SJIS = str(enc.get("file", ENCODING_SJIS))
        server = d.get("server", {})
        if isinstance(server, dict):
            if not env_host:
                HOST = str(server.get("HOST", HOST))
            if not env_port:
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
_set_user_inputs_file(USER_INPUTS_FILE)

# --- Disable sample mode globally (prefer UNC/prod only)
SAMPLE_SEARCH_DIRS = []
SAMPLE_IF126_PATTERNS = []
SAMPLE_SHORT_PATTERNS = []
