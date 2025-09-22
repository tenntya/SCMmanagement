import os
import sys
import importlib
from pathlib import Path

# Ensure repo root is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def reload_config():
    import procurement_manager.config as cfg
    importlib.reload(cfg)
    return cfg


def test_env_overrides(tmp_path, monkeypatch):
    # Set environment variables
    if126_tmpl = str(tmp_path / "NHSAPOTHIF126_{yyyymmdd}.txt")
    short_tmpl = str(tmp_path / "短納期品(西神)_{yyyymmdd}.csv")
    monkeypatch.setenv("PM_IF126_TEMPLATE", if126_tmpl)
    monkeypatch.setenv("PM_SHORT_TEMPLATE", short_tmpl)

    cfg = reload_config()
    assert cfg.IF126_TEMPLATE == if126_tmpl
    assert cfg.SHORT_TEMPLATE == short_tmpl


def test_resolve_if126_path_with_env(tmp_path, monkeypatch):
    # Prepare a fake prod file for a date
    day = "20250102"
    p = tmp_path / f"NHSAPOTHIF126_{day}.txt"
    p.write_text("A\tB\n1\t2\n", encoding="utf-8")
    monkeypatch.setenv("PM_IF126_TEMPLATE", str(tmp_path / "NHSAPOTHIF126_{yyyymmdd}.txt"))

    # Reload config after setting env, then import dp
    cfg = reload_config()
    assert Path(cfg.IF126_TEMPLATE).parent == tmp_path

    import procurement_manager.data_processor as dp
    importlib.reload(dp)

    from datetime import date
    d = date(2025, 1, 2)
    path = dp.resolve_if126_path(d, use_sample=False)
    assert path == p
