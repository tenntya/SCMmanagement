from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import os
import ctypes
from ctypes import wintypes

import pandas as pd

from . import config


logger = logging.getLogger(__name__)


_CACHE_VERSION = 2

EXCLUDED_SUPPLIER_CODES = {"NVAA294825", "NVAA351706", "NVAA280167"}
_SUPPLIER_CODE_LETTER = "B"


# ---------- 日付/列ユーティリティ ----------

def today_date() -> date:
    return date.today()


def yyyymmdd(d: date) -> str:
    return d.strftime(config.DATE_FMT_OUT)


def monday_with_prev_saturday(d: date) -> List[date]:
    # 月曜は前週土曜も対象
    if d.weekday() == 0:
        prev_sat = d - timedelta(days=2)
        return [d, prev_sat]
    return [d]


def parse_any_date(s: str) -> Optional[date]:
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    # よくある形式を順に試す
    fmts = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y%m%d",
        "%y/%m/%d",
        "%y-%m-%d",
    ]
    for f in fmts:
        try:
            return datetime.strptime(s, f).date()
        except Exception:
            continue
    # pandasの推定に最後に頼る
    try:
        dt = pd.to_datetime(s, errors="coerce").date()
        return dt
    except Exception:
        return None


def col_letter_to_index(letter: str) -> int:
    # A->0, B->1, ..., Z->25, AA->26, AB->27, AC->28, ...
    letter = letter.strip().upper()
    result = 0
    for ch in letter:
        result = result * 26 + (ord(ch) - ord('A') + 1)
    return result - 1


def index_to_col_letter(idx: int) -> str:
    idx += 1
    s = ""
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


def select_by_letters(df: pd.DataFrame, letters: List[str]) -> Tuple[pd.DataFrame, List[str]]:
    cols = []
    names = []
    for lt in letters:
        i = col_letter_to_index(lt)
        if i < len(df.columns):
            cols.append(df.columns[i])
            names.append(lt)
    return df[cols].copy(), names


# ---------- サンプル/実データ パス解決 ----------

def find_latest_by_patterns(search_dirs: List[Path], patterns: List[str]) -> Optional[Path]:
    candidates: List[Tuple[datetime, Path]] = []
    for d in search_dirs:
        for pat in patterns:
            for p in d.glob(pat):
                try:
                    stat = p.stat()
                    candidates.append((datetime.fromtimestamp(stat.st_mtime), p))
                except Exception:
                    continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def find_latest_by_filename_date(search_dirs: List[Path], patterns: List[str]) -> Optional[Path]:
    best: Tuple[Optional[date], datetime, Path] | None = None
    for d in search_dirs:
        for pat in patterns:
            for p in d.glob(pat):
                try:
                    dt_file = extract_date_from_filename(p)
                    stat = p.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime)
                    key = (dt_file, mtime, p)
                    if best is None:
                        best = key
                    else:
                        # まずファイル名の日付が大きいものを優先、同値なら更新日時
                        if (best[0] or date.min) < (dt_file or date.min) or (
                            (best[0] == dt_file) and (best[1] < mtime)
                        ):
                            best = key
                except Exception:
                    continue
    return best[2] if best else None



def _cache_path(tab: str, mode: str, ref_date: date) -> Path:
    safe_tab = tab.replace('/', '_')
    stamp = ref_date.strftime('%Y%m%d')
    return config.PROCESSED_DIR / f"{safe_tab}_{mode}_{stamp}.cache.json"


def _source_info_for(path: Path) -> Tuple[str, float, int]:
    try:
        stat = path.stat()
        return str(path), float(stat.st_mtime), int(stat.st_size)
    except Exception:
        return str(path), 0.0, 0


def _user_inputs_source_info() -> Tuple[str, float, int]:
    try:
        _ensure_user_inputs_file()
        path = config.USER_INPUTS_FILE
        stat = path.stat()
        return str(path), float(stat.st_mtime), int(stat.st_size)
    except Exception:
        return str(config.USER_INPUTS_FILE), 0.0, 0


def _normalize_sources(sources: List[Tuple[str, float, int]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for p, mtime, size in sources:
        items.append({'path': str(p), 'mtime': round(float(mtime), 6), 'size': int(size)})
    items.sort(key=lambda x: x['path'])
    return items


def _load_cached_payload(tab: str, mode: str, ref_date: date, sources: List[Tuple[str, float, int]]) -> Optional[Dict]:
    path = _cache_path(tab, mode, ref_date)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    if data.get('version') != _CACHE_VERSION:
        return None
    cached_sources = data.get('sources')
    if not isinstance(cached_sources, list):
        return None
    if _normalize_sources(sources) != cached_sources:
        return None
    payload = data.get('payload')
    return payload if isinstance(payload, dict) else None


def _save_cached_payload(tab: str, mode: str, ref_date: date, sources: List[Tuple[str, float, int]], payload: Dict) -> None:
    if not isinstance(payload, dict):
        return
    path = _cache_path(tab, mode, ref_date)
    tmp = None
    try:
        tmp = path.with_suffix('.tmp')
        data = {
            'version': _CACHE_VERSION,
            'sources': _normalize_sources(sources),
            'payload': payload,
        }
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        tmp.replace(path)
    except Exception:
        if tmp and tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass


def invalidate_tab_cache(tab: str) -> None:
    """Remove cached files for the specified tab (all modes/dates)."""
    safe_tab = (tab or '').replace('/', '_')
    pattern = f"{safe_tab}_*.cache.json"
    try:
        for cached in config.PROCESSED_DIR.glob(pattern):
            try:
                cached.unlink()
            except Exception:
                pass
    except Exception:
        pass

def _filter_excluded_suppliers(df: pd.DataFrame) -> pd.DataFrame:
    if not EXCLUDED_SUPPLIER_CODES:
        return df
    idx = col_letter_to_index(_SUPPLIER_CODE_LETTER)
    if idx >= len(df.columns):
        return df
    series = df.iloc[:, idx].astype(str).str.strip()
    mask = ~series.isin(EXCLUDED_SUPPLIER_CODES)
    if mask.all():
        return df
    filtered = df[mask].copy()
    try:
        logger.info('filter suppliers: removed %s rows', int((~mask).sum()))
    except Exception:
        pass
    return filtered


def resolve_if126_path(d: date, use_sample: bool) -> Optional[Path]:
    # Fast path: check recent dates before directory scan
    try:
        try_dates: List[date] = [d]
        if d.weekday() == 0:
            try_dates.append(d - timedelta(days=2))
        for i in range(1, 7):
            try_dates.append(d - timedelta(days=i))
        tmpl = os.getenv('PM_IF126_TEMPLATE', getattr(config, 'IF126_TEMPLATE', r'K:\PW_Tableau\IF126_納入日程管理\NHSAPOTHIF126_{yyyymmdd}.txt'))
        for dd in try_dates:
            target_path = _to_unc_if_possible(Path(str(tmpl).format(yyyymmdd=yyyymmdd(dd))))
            if target_path.exists():
                logger.info('IF126 fast path resolved: %s', target_path)
                return target_path
    except Exception:
        pass
    # サンプルモード廃止
    # 本番データ優先: 当日 → (月曜は前土曜) → ディレクトリ内の最新
    try_dates: List[date] = [d]
    if d.weekday() == 0:  # Monday
        try_dates.append(d - timedelta(days=2))

    for dd in try_dates:
        target = _to_unc_if_possible(Path(config.IF126_TEMPLATE.format(yyyymmdd=yyyymmdd(dd))))
        if target.exists():
            logger.info("IF126 path resolved: %s", target)
            return target

    # ディレクトリ内の最新を探索（複数候補）。ファイル名の日付を優先。
    dir_path = _to_unc_if_possible(Path(config.IF126_TEMPLATE)).parent
    pat = Path(config.IF126_TEMPLATE).name.replace("{yyyymmdd}", "*")
    search_dirs: List[Path] = []
    if dir_path.exists():
        search_dirs.append(dir_path)
    # 追加: 環境変数でIF126_DIRがあれば優先
    try:
        import os as _os
        if126_dir_env = _os.getenv("PM_IF126_DIR")
        if if126_dir_env:
            p_env = Path(if126_dir_env)
            if p_env.exists():
                search_dirs.append(p_env)
    except Exception:
        pass
    # 開発時の手元配置を考慮
    try:
        # 本番運用ではローカル探索は避けるが、環境変数で明示許可された場合は有効化
        from . import config as _cfg  # lazy import to avoid cycles at top
        allow_local = (os.getenv("PM_ALLOW_LOCAL_FALLBACK", "").lower() in ("1", "true", "yes"))
        if allow_local:
            search_dirs.extend([_cfg.ROOT_DIR, _cfg.ROOT_DIR.parent])
    except Exception:
        pass
    try:
        logger.debug("IF126 search dirs: %s, pattern: %s", [str(p) for p in search_dirs], pat)
    except Exception:
        pass
    latest = find_latest_by_filename_date(search_dirs, [pat]) if search_dirs else None
    if latest and latest.exists():
        logger.warning("IF126 fallback to latest file: %s", latest)
        return latest
    return None


def resolve_short_paths(d: date, use_sample: bool) -> List[Path]:
    dates = monday_with_prev_saturday(d)
    paths: List[Path] = []
    if use_sample:
        p = find_latest_by_patterns(config.SAMPLE_SEARCH_DIRS, config.SAMPLE_SHORT_PATTERNS)
        if p and p.exists():
            return [p]
        return []
    else:
        for dtv in dates:
            target = _to_unc_if_possible(Path(config.SHORT_TEMPLATE.format(yyyymmdd=yyyymmdd(dtv))))
            if target.exists():
                paths.append(target)
        if paths:
            return paths
        # 最新ファイルにフォールバック（名称ゆらぎ対応のパターンを広げ、ファイル名日付を優先）
        dir_path = _to_unc_if_possible(Path(config.SHORT_TEMPLATE)).parent
        name = Path(config.SHORT_TEMPLATE).name
        patterns_set = set()
        patterns_set.add(name.replace("{yyyymmdd}", "*"))
        patterns_set.add(name.replace("(西神)", "*").replace("{yyyymmdd}", "*"))
        patterns_set.add(name.replace("（西神）", "*").replace("{yyyymmdd}", "*"))
        patterns_set.add(name.replace("短納期品", "短納期").replace("{yyyymmdd}", "*"))
        patterns_set.add("*短納期*.csv")
        patterns_set.add("*西神*.csv")
        patterns = list(patterns_set)

        search_dirs: List[Path] = []
        if dir_path.exists():
            search_dirs.append(dir_path)
        try:
            short_dir_env = os.getenv("PM_SHORT_DIR")
            if short_dir_env:
                p_env = Path(short_dir_env)
                if p_env.exists():
                    search_dirs.append(p_env)
        except Exception:
            pass
        try:
            from . import config as _cfg  # lazy
            allow_local = (os.getenv("PM_ALLOW_LOCAL_FALLBACK", "").lower() in ("1", "true", "yes"))
            if allow_local:
                search_dirs.extend([_cfg.ROOT_DIR, _cfg.ROOT_DIR.parent])
        except Exception:
            pass
        try:
            logger.debug("SHORT search dirs: %s, patterns: %s", [str(p) for p in search_dirs], patterns)
        except Exception:
            pass
        latest = find_latest_by_filename_date(search_dirs, patterns) if search_dirs else None
        if latest and latest.exists():
            logger.warning("SHORT fallback to latest file: %s", latest)
            return [latest]
        return []


def extract_date_from_filename(p: Path) -> Optional[date]:
    try:
        import re
        m = re.search(r"(20\d{6})", p.name)
        if m:
            s = m.group(1)
            return datetime.strptime(s, "%Y%m%d").date()
    except Exception:
        pass
    return None


# ---------- データ読み込み ----------

def read_if126(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t", encoding=config.ENCODING_SJIS, dtype=str, keep_default_na=False)
    return df


def read_short(paths: List[Path]) -> pd.DataFrame:
    frames = []
    for p in paths:
        try:
            frames.append(pd.read_csv(p, encoding=config.ENCODING_SJIS, dtype=str, keep_default_na=False))
        except Exception as e:
            logger.exception("短納期CSV読込失敗: %s", p)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates()
    return df

# ---------- IF130 (再日程計画確認) ----------
def resolve_if130_path(d: date, use_sample: bool) -> Optional[Path]:
    if False and use_sample:
        patterns = getattr(config, "SAMPLE_IF130_PATTERNS", ["NHSAPOTHIF130_*.txt"])
        p = find_latest_by_patterns(getattr(config, "SAMPLE_SEARCH_DIRS", [config.ROOT_DIR, config.ROOT_DIR.parent]), patterns)
        if p and p.exists():
            logger.info("IF130 sample resolved: %s", p)
            return p
    try_dates: List[date] = [d]
    if d.weekday() == 0:
        try_dates.append(d - timedelta(days=2))
    tmpl = os.getenv("PM_IF130_TEMPLATE", getattr(config, "IF130_TEMPLATE", r"K:\\PW_Tableau\\IF130_MRP警告リスト\\NHSAPOTHIF130_{yyyymmdd}.txt"))
    for dd in try_dates:
        target = _to_unc_if_possible(Path(str(tmpl).format(yyyymmdd=yyyymmdd(dd))))
        if target.exists():
            logger.info("IF130 path resolved: %s", target)
            return target
    dir_path = _to_unc_if_possible(Path(str(tmpl))).parent
    pat = Path(str(tmpl)).name.replace("{yyyymmdd}", "*")
    search_dirs: List[Path] = []
    if dir_path.exists():
        search_dirs.append(dir_path)
    if130_dir = os.getenv("PM_IF130_DIR")
    if if130_dir:
        p_env = Path(if130_dir)
        if p_env.exists():
            search_dirs.append(p_env)
    if os.getenv("PM_ALLOW_LOCAL_FALLBACK", "").lower() in ("1","true","yes"):
        search_dirs.extend([config.ROOT_DIR, config.ROOT_DIR.parent])
    latest = find_latest_by_filename_date(search_dirs, [pat]) if search_dirs else None
    if latest and latest.exists():
        logger.warning("IF130 fallback to latest file: %s", latest)
        return latest
    return None

def build_reschedule(df_if130: pd.DataFrame, today: date) -> Tuple[List[str], List[str], pd.DataFrame, str]:
    max_idx = min(17, len(df_if130.columns))
    view_df = df_if130.iloc[:, :max_idx].copy()
    q_idx = col_letter_to_index("Q")
    if q_idx < len(view_df.columns):
        view_df = view_df[view_df.iloc[:, q_idx].astype(str).str.contains("前倒し", na=False)]
    def _classify_a(x: str) -> str:
        if not isinstance(x, str) or not x:
            return ""
        c = x[0].upper()
        if c == "H": return "TRP"
        if c == "W": return "SVF"
        return ""
    view_df = view_df.copy()
    view_df["分類"] = view_df.iloc[:, 0].astype(str).apply(_classify_a)
    key_letter = "D"
    d_idx = col_letter_to_index("D")
    inputs = load_user_inputs().get("reschedule", {})
    free = []
    for _, row in view_df.iterrows():
        key = str(row.iloc[d_idx]) if d_idx < len(row) else ""
        free.append(inputs.get(key, {}).get("自由入力", ""))
    view_df["自由入力"] = free
    headers = list(view_df.columns)
    letters = [index_to_col_letter(i) for i in range(len(headers))]
    return headers, letters, view_df.reset_index(drop=True), key_letter


# ---------- 永続化（自由入力/備考） ----------

def _ensure_user_inputs_file():
    if not config.USER_INPUTS_FILE.exists():
        config.USER_INPUTS_FILE.write_text("{}", encoding="utf-8")


def load_user_inputs() -> Dict:
    _ensure_user_inputs_file()
    try:
        data = json.loads(config.USER_INPUTS_FILE.read_text(encoding="utf-8"))
        changed = _normalize_user_inputs_inplace(data)
        if changed:
            tmp = config.USER_INPUTS_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(config.USER_INPUTS_FILE)
        return data
    except Exception as exc:
        logger.exception("failed to load user inputs: %s", exc)
        return {}




def save_user_input(tab: str, key: str, field: str, value: str) -> None:
    data = load_user_inputs()
    tabmap = data.setdefault(tab, {})
    entry = tabmap.setdefault(key, {})
    # 追加されたフィールド名を正規化
    field_norm = _normalize_field_name(tab, field)
    entry[field_norm] = value
    tmp = config.USER_INPUTS_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(config.USER_INPUTS_FILE)
    invalidate_tab_cache(tab)
    if tab == 'houchozan':
        invalidate_tab_cache('houchozan_today')





def _normalize_field_name(tab: str, field: str) -> str:
    f = (field or "").strip()
    if tab in ("houchozan", "text_items"):
        # 自由入力の表記揺れ・文字化け救済
        if f != "自由入力":
            if "自由" in f:
                return "自由入力"
        return "自由入力" if f == "" else f
    if tab == "short":
        if f != "備考":
            if f and f.startswith("備"):
                return "備考"
        return "備考" if f == "" else f
    return f


def _normalize_user_inputs_inplace(data: Dict) -> bool:
    changed = False
    if not isinstance(data, dict):
        return False
    for tab, canonical in (("houchozan", "自由入力"), ("text_items", "自由入力"), ("short", "備考")):
        tabmap = data.get(tab)
        if not isinstance(tabmap, dict):
            continue
        for key, entry in list(tabmap.items()):
            if not isinstance(entry, dict):
                continue
            # 文字化け/表記揺れキーを正規化
            if canonical not in entry:
                # 候補: 含む/先頭一致
                alt = None
                for k in list(entry.keys()):
                    if k == canonical:
                        alt = None
                        break
                    if (canonical.startswith("自由") and "自由" in k) or (canonical == "備考" and (k.startswith("備") or "備" in k)):
                        alt = k
                        break
                if alt is not None:
                    entry[canonical] = entry.pop(alt)
                    changed = True
    return changed


# ---------- 設定（名称リストなど） ----------

def _load_all() -> Dict:
    _ensure_user_inputs_file()
    try:
        return json.loads(config.USER_INPUTS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.exception("failed to load user inputs cache: %s", exc)
        return {}


def _save_all(data: Dict) -> None:
    tmp = config.USER_INPUTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(config.USER_INPUTS_FILE)


def get_houchozan_names() -> Dict[str, object]:
    data = _load_all()
    settings = data.setdefault("_settings", {})
    names = settings.setdefault("houchozan_names", [])
    current = settings.get("houchozan_current_name")
    # 型補正
    if not isinstance(names, list):
        names = []
        settings["houchozan_names"] = names
    if current is not None and not isinstance(current, str):
        current = None
        settings["houchozan_current_name"] = None
    _save_all(data)
    return {"names": names, "current": current}


def set_houchozan_name(name: str, add_if_missing: bool = True) -> Dict[str, object]:
    name = (name or "").strip()
    data = _load_all()
    settings = data.setdefault("_settings", {})
    names = settings.setdefault("houchozan_names", [])
    if add_if_missing and name and name not in names:
        names.append(name)
    if name:
        settings["houchozan_current_name"] = name
    _save_all(data)
    invalidate_tab_cache('houchozan')
    invalidate_tab_cache('houchozan_today')
    return {"names": names, "current": settings.get("houchozan_current_name")}


# ---------- タブ別データ生成 ----------

IF126_DISPLAY_LETTERS = ["B", "C", "D", "E", "I", "J", "O", "P", "R", "Y", "AC"]


def _add_delay_and_classification(df: pd.DataFrame, classification_source_letter: str, today: date) -> pd.DataFrame:
    # 遅延日数: P列（16列目）を日付解釈
    p_idx = col_letter_to_index("P")
    if p_idx < len(df.columns):
        due_series = df.iloc[:, p_idx].apply(parse_any_date)
        delay_days = due_series.apply(lambda d: max(0, (today - d).days) if isinstance(d, date) else None)
        df = df.copy()
        df["遅延日数"] = delay_days
    else:
        df = df.copy()
        df["遅延日数"] = None

    # 分類: 指定列の先頭文字で判定
    src_idx = col_letter_to_index(classification_source_letter)
    def _classify(x: str) -> str:
        if not isinstance(x, str) or not x:
            return ""
        c = x[0].upper()
        if c == "H":
            return "TRP"
        if c == "W":
            return "SVF"
        return ""

    if src_idx < len(df.columns):
        df["分類"] = df.iloc[:, src_idx].apply(_classify)
    else:
        df["分類"] = ""
    return df


def build_houchozan(df_if: pd.DataFrame, today: date) -> Tuple[List[str], List[str], pd.DataFrame, str]:
    df_if = _filter_excluded_suppliers(df_if)
    # 期限切れ: P列 < today
    p_idx = col_letter_to_index("P")
    if p_idx < len(df_if.columns):
        due_series = df_if.iloc[:, p_idx].apply(parse_any_date)
        df_if = df_if[due_series.apply(lambda d: isinstance(d, date) and d < today)]
    # 表示列
    view_df, letters = select_by_letters(df_if, IF126_DISPLAY_LETTERS)
    # 追加列
    df2 = df_if.copy()
    df2 = _add_delay_and_classification(df2, classification_source_letter="D", today=today)
    # 自由入力（I列キー）
    key_letter = "I"
    key_idx = col_letter_to_index(key_letter)
    inputs = load_user_inputs().get("houchozan", {})
    free = []
    for _, row in df2.iterrows():
        key = str(row.iloc[key_idx]) if key_idx < len(row) else ""
        free.append(inputs.get(key, {}).get("自由入力", ""))
    view_df = view_df.copy()
    view_df["遅延日数"] = df2["遅延日数"].values
    view_df["分類"] = df2["分類"].values
    view_df["自由入力"] = free
    letters = letters + [None, None, None]
    return list(view_df.columns), letters, view_df.reset_index(drop=True), key_letter


def build_houchozan_today(df_if: pd.DataFrame, today: date) -> Tuple[List[str], List[str], pd.DataFrame, str]:
    df_if = _filter_excluded_suppliers(df_if)
    # 当日納期までを対象: P列 <= today
    try:
        logger.info("[houchozan_today] input rows=%s, cols=%s", len(df_if), len(df_if.columns))
    except Exception:
        pass
    p_idx = col_letter_to_index("P")
    if p_idx < len(df_if.columns):
        colP = df_if.iloc[:, p_idx].astype(str)
        today_s = today.strftime("%Y%m%d")
        colP_digits = colP.str.replace(r"\D", "", regex=True)
        mask_digits = colP_digits.apply(lambda s: bool(s) and len(s) == 8 and s <= today_s)
        due_series = colP.apply(parse_any_date)
        mask_parsed = due_series.apply(lambda d: isinstance(d, date) and d <= today)
        before = len(df_if)
        df_if = df_if[mask_digits | mask_parsed]
        try:
            logger.info("[houchozan_today] after P<=today filter: %s -> %s", before, len(df_if))
        except Exception:
            pass
    # 27列目に「検収」を含むものを除外（0始まり index=26）
    try:
        idx27 = 26
        if idx27 < len(df_if.columns):
            before2 = len(df_if)
            df_if = df_if[~df_if.iloc[:, idx27].astype(str).str.contains("検収", na=False)]
            try:
                logger.info("[houchozan_today] after exclude 検収 at col27: %s -> %s", before2, len(df_if))
            except Exception:
                pass
    except Exception:
        pass
    # 表示・自由入力付与などは発注残のビルドを再利用（ただし期限判定の基準は当日を含めるため +1日）
    headers, letters, view_df, key_letter = build_houchozan(df_if, today + timedelta(days=1))
    # ただし遅延日数は「今日」基準で再計算して上書きする
    base_cols = list(df_if.columns)
    df2 = _add_delay_and_classification(df_if.copy(), classification_source_letter="D", today=today)
    added_cols = [c for c in df2.columns if c not in base_cols]
    # 遅延日数らしき列名を推定（日本語の「日」や「遅」または 'delay' を含む）
    delay_candidates = [c for c in added_cols if any(k in str(c) for k in ("日", "遅", "delay", "Delay"))]
    delay_col = delay_candidates[0] if delay_candidates else (added_cols[0] if added_cols else None)
    if delay_col and delay_col in view_df.columns:
        try:
            view_df[delay_col] = list(df2[delay_col].values)
        except Exception:
            pass
    return headers, letters, view_df.reset_index(drop=True), key_letter


def build_text_items(df_if: pd.DataFrame, today: date) -> Tuple[List[str], List[str], pd.DataFrame, str]:
    df_if = _filter_excluded_suppliers(df_if)
    # D列が空白のみ
    d_idx = col_letter_to_index("D")
    if d_idx < len(df_if.columns):
        df_if = df_if[df_if.iloc[:, d_idx].astype(str).str.strip() == ""]
    # 表示列
    view_df, letters = select_by_letters(df_if, IF126_DISPLAY_LETTERS)
    # 追加列（分類はF列）
    df2 = df_if.copy()
    df2 = _add_delay_and_classification(df2, classification_source_letter="F", today=today)
    # 自由入力（I列キー）
    key_letter = "I"
    key_idx = col_letter_to_index(key_letter)
    inputs = load_user_inputs().get("text_items", {})
    free = []
    for _, row in df2.iterrows():
        key = str(row.iloc[key_idx]) if key_idx < len(row) else ""
        free.append(inputs.get(key, {}).get("自由入力", ""))
    view_df = view_df.copy()
    view_df["遅延日数"] = df2["遅延日数"].values
    view_df["分類"] = df2["分類"].values
    view_df["自由入力"] = free
    letters = letters + [None, None, None]
    return list(view_df.columns), letters, view_df.reset_index(drop=True), key_letter


def build_short(df_short: pd.DataFrame, today: date) -> Tuple[List[str], List[str], pd.DataFrame, str]:
    # A〜M列（13列）
    letters = [index_to_col_letter(i) for i in range(13)]
    if df_short.empty:
        view_df = pd.DataFrame(columns=[])  # 空
        headers = []
        letters_ret: List[Optional[str]] = []
    else:
        max_idx = min(13, len(df_short.columns))
        headers = list(df_short.columns[:max_idx])
        view_df = df_short.iloc[:, :max_idx].copy()
        letters = [index_to_col_letter(i) for i in range(max_idx)]
    # 備考（自由入力、A列キー）
    key_letter = "A"
    key_idx = 0
    inputs = load_user_inputs().get("short", {})
    notes = []
    for _, row in view_df.iterrows():
        key = str(row.iloc[key_idx]) if key_idx < len(row) else ""
        notes.append(inputs.get(key, {}).get("備考", ""))
    view_df = view_df.copy()
    view_df["備考"] = notes
    letters_ret = letters + [None]
    return list(view_df.columns), letters_ret, view_df.reset_index(drop=True), key_letter


def load_tab_data(tab: str, use_sample: bool = True, ref_date: Optional[date] = None) -> Dict:
    ref_date = ref_date or today_date()
    mode = "sample" if use_sample else "prod"
    sources_info: List[Tuple[str, float, int]] = []

    try:
        if tab in ("houchozan", "text_items"):
            p = resolve_if126_path(ref_date, use_sample)
            if not p:
                raise FileNotFoundError("IF126データが見つかりません")
            sources_info = [_source_info_for(p)]
            sources_info.append(_user_inputs_source_info())
            cached = _load_cached_payload(tab, mode, ref_date, sources_info)
            if cached:
                return cached
            df = read_if126(p)
            src_dt = extract_date_from_filename(p) or ref_date
            if tab == "houchozan":
                headers, letters, view_df, key_letter = build_houchozan(df, ref_date)
            else:
                headers, letters, view_df, key_letter = build_text_items(df, ref_date)
        elif tab == "short":
            ps = resolve_short_paths(ref_date, use_sample)
            if not ps:
                raise FileNotFoundError("短納期CSVが見つかりません")
            sources_info = [_source_info_for(pp) for pp in ps]
            sources_info.append(_user_inputs_source_info())
            cached = _load_cached_payload(tab, mode, ref_date, sources_info)
            if cached:
                return cached
            df = read_short(ps)
            headers, letters, view_df, key_letter = build_short(df, ref_date)
            src_dates = []
            for pp in ps:
                dt = extract_date_from_filename(pp)
                if dt:
                    src_dates.append(dt)
            if not src_dates:
                src_dates = monday_with_prev_saturday(ref_date)
        else:
            return {"error": "unknown tab"}

        rows = view_df.astype(str).fillna("").values.tolist()
        result = {
            "headers": headers,
            "letters": letters,
            "rows": rows,
            "keyLetter": key_letter,
        }
        if tab in ("houchozan", "text_items"):
            result["sourceDates"] = [src_dt.strftime("%Y/%m/%d")]
            result["nameLetter"] = "C"
        elif tab == "short":
            uniq = sorted({d.strftime("%Y/%m/%d") for d in src_dates})
            result["sourceDates"] = uniq
            result["nameLetter"] = "C" if "C" in letters else ("B" if "B" in letters else letters[0] if letters else "A")

        _save_cached_payload(tab, mode, ref_date, sources_info, result)
        return result
    except Exception as e:
        logger.exception("データ読込エラー: %s", e)
        return {"error": str(e)}


def process_all_and_save(use_sample: bool = False, ref_date: Optional[date] = None) -> Dict[str, Path]:
    # 日次バッチ用：加工済みJSONを保存
    ref_date = ref_date or today_date()
    outputs: Dict[str, Path] = {}
    for tab in ("houchozan", "text_items", "short"):
        data = load_tab_data(tab, use_sample=use_sample, ref_date=ref_date)
        out = config.PROCESSED_DIR / f"{tab}_{yyyymmdd(ref_date)}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        outputs[tab] = out
    return outputs


# ---------- Robust CSV reading (fallback encodings) ----------
def _read_csv_with_fallback(path: Path, sep: Optional[str] = None) -> pd.DataFrame:
    enc_order = []
    seen = set()
    for e in [getattr(config, "ENCODING_SJIS", None), "cp932", "utf-8-sig", "utf-8"]:
        if e and e not in seen:
            enc_order.append(e)
            seen.add(e)
    last_err: Optional[Exception] = None
    for enc in enc_order:
        try:
            kwargs = {"dtype": str, "keep_default_na": False}
            if sep is not None:
                kwargs["sep"] = sep
            df = pd.read_csv(path, encoding=enc, **kwargs)
            logger.info("read %s with encoding=%s", path, enc)
            return df
        except Exception as e:
            last_err = e
            continue
    logger.exception("failed to read %s with encodings %s", path, enc_order)
    if last_err:
        raise last_err
    raise RuntimeError(f"failed to read: {path}")


# Override readers to use fallback
def read_if126(path: Path) -> pd.DataFrame:  # type: ignore[override]
    return _read_csv_with_fallback(path, sep="\t")


def read_short(paths: List[Path]) -> pd.DataFrame:  # type: ignore[override]
    frames = []
    for p in paths:
        try:
            frames.append(_read_csv_with_fallback(p))
        except Exception:
            logger.exception("短納期CSV読込失敗: %s", p)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates()
    return df
# ---------- Windows UNC 補助 ----------
def _to_unc_if_possible(path: Path) -> Path:
    try:
        if os.name != "nt":
            return path
        s = str(path)
        if len(s) < 2 or s[1] != ":":
            return path  # not a drive-letter path
        WNetGetUniversalNameW = ctypes.windll.mpr.WNetGetUniversalNameW  # type: ignore[attr-defined]
        WNetGetUniversalNameW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPVOID, ctypes.POINTER(wintypes.DWORD)]
        WNetGetUniversalNameW.restype = wintypes.DWORD
        UNIVERSAL_NAME_INFO_LEVEL = 1
        buf_size = 65536
        buf = ctypes.create_unicode_buffer(buf_size)
        size = wintypes.DWORD(ctypes.sizeof(buf))
        rc = WNetGetUniversalNameW(s, UNIVERSAL_NAME_INFO_LEVEL, ctypes.byref(buf), ctypes.byref(size))
        if rc == 0:
            unc = buf.value
            if unc:
                return Path(unc)
    except Exception:
        pass
    return path

# --- override: clean build_reschedule with correct Japanese headers ---
def build_reschedule(df_if130: pd.DataFrame, today: date) -> Tuple[List[str], List[str], pd.DataFrame, str]:  # type: ignore[override]
    max_idx = min(17, len(df_if130.columns))
    view_df = df_if130.iloc[:, :max_idx].copy()
    q_idx = col_letter_to_index("Q")
    if q_idx < len(view_df.columns):
        view_df = view_df[view_df.iloc[:, q_idx].astype(str).str.contains("前倒し", na=False)]
    def _classify_a(x: str) -> str:
        if not isinstance(x, str) or not x:
            return ""
        c = x[0].upper()
        if c == "H": return "TRP"
        if c == "W": return "SVF"
        return ""
    view_df = view_df.copy()
    # R列=分類, S列=自由入力
    view_df["分類"] = view_df.iloc[:, 0].astype(str).apply(_classify_a)
    key_letter = "D"
    d_idx = col_letter_to_index("D")
    inputs = load_user_inputs().get("reschedule", {})
    free = []
    for _, row in view_df.iterrows():
        key = str(row.iloc[d_idx]) if d_idx < len(row) else ""
        free.append(inputs.get(key, {}).get("自由入力", ""))
    view_df["自由入力"] = free
    headers = list(view_df.columns)
    letters = [index_to_col_letter(i) for i in range(len(headers))]
    return headers, letters, view_df.reset_index(drop=True), key_letter
