# Repository Guidelines

## Project Structure & Module Organization
- `procurement_manager/`: Core app
  - `main.py` (Flask server), `data_processor.py` (ETL/filters), `config.py` (paths, dates, logging)
  - `templates/index.html`, `static/css/style.css`, `static/js/app.js`
  - `data/user_inputs.json`, `data/processed/`
- Root: `requirements.txt`, `build.bat`, `run_daily.bat`, `AGENTS.md`
- Add tests under `tests/` and sample fixtures under `data/samples/`.

## Build, Test, and Development Commands
- Create venv: `python -m venv .venv && .\.venv\Scripts\activate`
- Install deps: `pip install -r requirements.txt`
- Run locally: `python procurement_manager\main.py` (serves UI on `http://127.0.0.1:<port>` from `config.py`)
- Package (EXE): `./build.bat` or `pyinstaller -F procurement_manager\main.py`
- Schedule/daily run: `./run_daily.bat` (for Windows Task Scheduler)
- Tests: `pytest -q` (place tests in `tests/`).

## Coding Style & Naming Conventions
- Python: PEP 8, 4-space indents, UTF-8 source files.
- Names: snake_case (functions/vars), PascalCase (classes), UPPER_CASE (constants).
- Paths: use `pathlib.Path`; keep file locations in `config.py` (avoid hard-coded drive letters in code).
- Data: read inputs as Shift-JIS; write JSON UTF-8; prefer explicit column names over indices.

## Testing Guidelines
- Framework: `pytest`; name files `test_*.py`.
- Cover: date logic (Monday uses prior Saturday), filters per tab, JSON persistence keys (I列 for 発注残/テキスト, A列 for 短納期).
- Use small TSV/CSV fixtures in `data/samples/` to keep tests fast.

## Commit & Pull Request Guidelines
- Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `build:`.
- PRs include: clear description, linked issues, verification steps, and screenshots for UI changes.
- Pre-submit: run the app locally and ensure no errors in logs.

## Security & Configuration Tips
- Keep network paths, ports, and log levels in `config.py` or env vars; never commit secrets.
- Handle missing files/encoding errors gracefully; log with rotation.
