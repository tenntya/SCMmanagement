import argparse
import logging
import os
import threading
import time
import webbrowser
from pathlib import Path
import sys
from urllib import request as _urlreq, error as _urlerr

from flask import Flask, jsonify, render_template, request

# 直実行/モジュール実行の両対応
PKG_DIR = Path(__file__).resolve().parent
REPO_DIR = PKG_DIR.parent
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

try:
    from procurement_manager import config  # type: ignore
    from procurement_manager import data_processor as dp  # type: ignore
except Exception:  # フォールバック
    from . import config  # type: ignore
    from . import data_processor as dp  # type: ignore


def _resolve_assets_base() -> Path:
    candidates = []
    try:
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            meipass = Path(sys._MEIPASS)  # type: ignore[attr-defined]
            candidates.append(meipass / "procurement_manager")
            candidates.append(meipass)
    except Exception:
        pass
    here = Path(__file__).parent
    candidates.append(here)
    candidates.append(here.parent / "procurement_manager")
    try:
        from procurement_manager import config as _cfg  # type: ignore
        candidates.append(Path(getattr(_cfg, "ROOT_DIR", here)) / "procurement_manager")
    except Exception:
        pass

    for base in candidates:
        tpl = base / "templates" / "index.html"
        if tpl.exists():
            return base
    return here


def create_app() -> Flask:
    base_dir = _resolve_assets_base()
    app = Flask(
        __name__,
        template_folder=str(base_dir / "templates"),
        static_folder=str(base_dir / "static"),
        static_url_path="/static",
    )
    try:
        app.logger.info("assets base: %s", str(base_dir))
    except Exception:
        pass

    @app.get("/api/health")
    def api_health():
        return jsonify({"ok": True})

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.get("/api/data/<tab>")
    def api_data(tab: str):
        use_sample = request.args.get("sample", "0") != "0"
        # Special handling for reschedule to support older dp versions
        if tab == "reschedule":
            try:
                from datetime import date as _date
                today = _date.today()
                p = dp.resolve_if130_path(today, use_sample)
                if not p:
                    return jsonify({"error": "IF130データが見つかりません"})
                df = dp.read_if126(p)
                headers, letters, view_df, key_letter = dp.build_reschedule(df, today)
                rows = view_df.astype(str).fillna("").values.tolist()
                src_dt = dp.extract_date_from_filename(p) or today
                return jsonify({
                    "headers": headers,
                    "letters": letters,
                    "rows": rows,
                    "keyLetter": key_letter,
                    "sourceDates": [src_dt.strftime("%Y/%m/%d")],
                    "nameLetter": "C" if "C" in letters else (letters[0] if letters else "A"),
                })
            except Exception as e:
                app.logger.exception("reschedule endpoint error: %s", e)
                return jsonify({"error": str(e)})
        data = dp.load_tab_data(tab, use_sample=use_sample)
        # 本番指定でエラー時はサンプルへ自動フォールバック
        if (not use_sample) and isinstance(data, dict) and data.get("error"):
            try:
                data2 = dp.load_tab_data(tab, use_sample=True)
                if isinstance(data2, dict) and not data2.get("error"):
                    data2["usedSample"] = True
                    data2["note"] = "fallback to sample"
                    return jsonify(data2)
            except Exception:
                pass
        return jsonify(data)

    @app.get("/api/config")
    def api_config():
        try:
            from datetime import date as _date
            today = _date.today()
            if_path = dp.resolve_if126_path(today, use_sample=False)
            short_paths = dp.resolve_short_paths(today, use_sample=False)
            return jsonify({
                "rootDir": str(getattr(config, "ROOT_DIR", "")),
                "encoding": getattr(config, "ENCODING_SJIS", ""),
                "if126Template": getattr(config, "IF126_TEMPLATE", ""),
                "shortTemplate": getattr(config, "SHORT_TEMPLATE", ""),
                "if126Resolved": str(if_path) if if_path else None,
                "shortResolved": [str(p) for p in short_paths],
            })
        except Exception as e:
            app.logger.exception("config endpoint error: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.post("/api/save")
    def api_save():
        payload = request.get_json(silent=True) or {}
        tab = payload.get("tab")
        key = str(payload.get("key"))
        field = payload.get("field")
        value = payload.get("value", "")
        if tab not in ("houchozan", "text_items", "short", "reschedule"):
            return jsonify({"ok": False, "error": "unknown tab"}), 400
        if not key or not field:
            return jsonify({"ok": False, "error": "key/field required"}), 400
        try:
            dp.save_user_input(tab, key, field, value)
            return jsonify({"ok": True})
        except Exception as e:
            app.logger.exception("保存エラー: %s", e)
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.get("/api/houchozan/name")
    def api_hz_name_get():
        try:
            info = dp.get_houchozan_names()
            return jsonify({"ok": True, **info})
        except Exception as e:
            app.logger.exception("名称取得エラー: %s", e)
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.post("/api/houchozan/name")
    def api_hz_name_set():
        payload = request.get_json(silent=True) or {}
        name = (payload.get("name") or "").strip()
        mode = (payload.get("mode") or "set").lower()
        try:
            info = dp.set_houchozan_name(name, add_if_missing=(mode != "set"))
            return jsonify({"ok": True, **info})
        except Exception as e:
            app.logger.exception("名称設定エラー: %s", e)
            return jsonify({"ok": False, "error": str(e)}), 500

    return app


def setup_logging():
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.DEBUG if config.DEBUG else logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    try:
        logging.getLogger("main").info(
            "config: ROOT_DIR=%s, IF126_TEMPLATE=%s, SHORT_TEMPLATE=%s, ENCODING=%s",
            str(getattr(config, "ROOT_DIR", "")),
            getattr(config, "IF126_TEMPLATE", ""),
            getattr(config, "SHORT_TEMPLATE", ""),
            getattr(config, "ENCODING_SJIS", ""),
        )
    except Exception:
        pass


def _open_browser_when_ready(port: int) -> None:
    # Debugのリローダで二重起動しないように制御
    def _allow_open() -> bool:
        if getattr(config, "DEBUG", False):
            return os.environ.get("WERKZEUG_RUN_MAIN") == "true"
        return True

    if not _allow_open():
        return

    host_for_url = "127.0.0.1"
    base = f"http://{host_for_url}:{port}"
    health = base + "/api/health"

    def _worker():
        deadline = time.time() + 20.0
        while time.time() < deadline:
            try:
                with _urlreq.urlopen(health, timeout=1.5) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.4)
        try:
            webbrowser.open_new(base)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=config.PORT)
    parser.add_argument("--once", action="store_true", help="データ加工のみ実行し終了")
    parser.add_argument("--no-sample", action="store_true", help="サンプルではなく実データパスを使用")
    args = parser.parse_args()

    setup_logging()

    if args.once:
        outputs = dp.process_all_and_save(use_sample=not args.no_sample)
        logging.getLogger(__name__).info("processed files: %s", outputs)
        return

    app = create_app()
    app.logger.info("Starting server on port %s", args.port)
    # サーバのヘルス確認後に1回だけブラウザを開く
    _open_browser_when_ready(args.port)
    app.run(host=getattr(config, "HOST", "0.0.0.0"), port=args.port, debug=config.DEBUG)


if __name__ == "__main__":
    main()
