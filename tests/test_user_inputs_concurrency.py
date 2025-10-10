import importlib
import json
import threading
import time
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import procurement_manager.config as config


def test_concurrent_free_input_updates_preserve_existing(tmp_path, monkeypatch):
    data_file = tmp_path / 'user_inputs.json'
    processed_dir = tmp_path / 'processed'
    monkeypatch.setattr(config, 'USER_INPUTS_FILE', data_file, raising=False)
    monkeypatch.setattr(config, 'PROCESSED_DIR', processed_dir, raising=False)

    dp = importlib.import_module('procurement_manager.data_processor')
    dp = importlib.reload(dp)

    field_key = dp._normalize_field_name('houchozan', '自由入力')
    data_file.write_text(
        json.dumps({'houchozan': {'existing': {field_key: 'keep'}}}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    def make_sleepy(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            time.sleep(0.05)
            return result
        return wrapper

    for name in ('_read_user_inputs_unlocked', 'load_user_inputs'):
        if hasattr(dp, name):
            original = getattr(dp, name)
            monkeypatch.setattr(dp, name, make_sleepy(original))

    threads = []
    for key, value in (('A', 'foo'), ('B', 'bar')):
        t = threading.Thread(target=dp.save_user_input, args=('houchozan', key, '自由入力', value))
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    result = dp.load_user_inputs()
    tabmap = result.get('houchozan', {})

    assert tabmap['existing'][field_key] == 'keep'
    assert tabmap['A'][field_key] == 'foo'
    assert tabmap['B'][field_key] == 'bar'
