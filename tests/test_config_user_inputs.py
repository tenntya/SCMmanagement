import importlib
from pathlib import Path
import sys
import json

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import procurement_manager.config as config


def _reload_config():
    return importlib.reload(config)


def test_user_inputs_file_env_override(tmp_path, monkeypatch):
    override = tmp_path / "alt" / "inputs.json"
    monkeypatch.setenv("PM_USER_INPUTS_FILE", str(override))
    try:
        cfg = _reload_config()
        assert cfg.USER_INPUTS_FILE == override
        assert override.parent.exists()
    finally:
        monkeypatch.delenv("PM_USER_INPUTS_FILE", raising=False)
        _reload_config()

def test_user_inputs_file_read(tmp_path, monkeypatch):
    data_file = tmp_path / "inputs.json"
    sample = {"houchozan": {"123": {"自由入力": "メモ"}}}
    data_file.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("PM_USER_INPUTS_FILE", str(data_file))
    cfg = _reload_config()
    # reload data_processor to pick up new config path
    dp = importlib.import_module("procurement_manager.data_processor")
    dp = importlib.reload(dp)
    loaded = dp.load_user_inputs()
    assert loaded["houchozan"]["123"]["自由入力"] == "メモ"
    monkeypatch.delenv("PM_USER_INPUTS_FILE", raising=False)
    _reload_config()
