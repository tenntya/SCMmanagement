import sys
import importlib
from pathlib import Path

# Ensure repo root is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_utf8sig_fallback_for_short(tmp_path, monkeypatch):
    # Create UTF-8 with BOM (utf-8-sig) CSV
    csv = "列A,列B\nあ,い\n"
    f = tmp_path / "短納期_utf8.csv"
    f.write_text(csv, encoding="utf-8-sig")

    import procurement_manager.data_processor as dp
    importlib.reload(dp)

    df = dp.read_short([f])
    assert not df.empty
    assert list(df.columns)[:2] == ["列A", "列B"]
    assert df.iloc[0, 0] == "あ"
    assert df.iloc[0, 1] == "い"
