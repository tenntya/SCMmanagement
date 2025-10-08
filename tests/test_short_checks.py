import json
from datetime import date

import pandas as pd

from procurement_manager import data_processor as dp


def _setup_user_inputs(tmp_path, monkeypatch, payload):
    ui_file = tmp_path / "user_inputs.json"
    ui_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    processed_dir = tmp_path / "cache"
    processed_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dp.config, "USER_INPUTS_FILE", ui_file)
    monkeypatch.setattr(dp.config, "PROCESSED_DIR", processed_dir)
    return ui_file


def test_build_short_includes_checked_keys(tmp_path, monkeypatch):
    payload = {
        "short": {
            "K1": {"自由入力": "メモ1", "__checked__": True},
            "K2": {"自由入力": "メモ2", "__checked__": False},
        }
    }
    _setup_user_inputs(tmp_path, monkeypatch, payload)
    df = pd.DataFrame([
        ["K1", "item-1"],
        ["K2", "item-2"],
    ], columns=["A", "B"])

    headers, letters, view_df, key_letter, checked = dp.build_short(df, date.today())

    assert key_letter == "A"
    assert '自由' in headers[-1]
    assert list(view_df[headers[-1]]) == ["メモ1", "メモ2"]
    assert checked == ["K1"]
    assert len(headers) == len(letters)


def test_save_user_input_checkbox_toggle(tmp_path, monkeypatch):
    ui_file = _setup_user_inputs(tmp_path, monkeypatch, {"short": {}})

    dp.save_user_input("short", "ROW1", "__checked__", True)
    data = json.loads(ui_file.read_text(encoding="utf-8"))
    assert data["short"]["ROW1"]["__checked__"] is True

    dp.save_user_input("short", "ROW1", "__checked__", False)
    data = json.loads(ui_file.read_text(encoding="utf-8"))
    assert "ROW1" not in data.get("short", {})
