# Eagle of Rome

Eagle of Rome is a Python strategy game project based on the Republic of Rome theme. The current codebase contains the MVP 0.7 gameplay baseline, the architecture closeout work for MVP 0.9, and the first playable PySide6/QML GUI prototype.

## Repository Layout

- `main.py`: CLI entry point.
- `gui_main.py`: PySide6/QML GUI entry point.
- `src/`: game source code, APIs, core systems, UI commands, and tests.
- `data/`: game configuration, cards, scenarios, and i18n files.
- `docs/`: project documentation baseline, architecture docs, task briefs, audit reports, and planning assets.
- `gui_delivery/`: GUI delivery screenshots and related materials.
- `AGENTS.md`: agent collaboration and codebase rules.

## Environment

Recommended Python version: Python 3.10.

Install dependencies from the repository root:

```powershell
python -m pip install -r requirements.txt
```

The GUI-specific dependency pin file is also kept as `requirements-gui.txt`.

## Run

CLI:

```powershell
python main.py
```

GUI:

```powershell
python gui_main.py
```

## Test

Run the full test suite:

```powershell
python -m pytest -p no:cacheprovider src/tests -q
```

The current integrated baseline was verified with `734 passed`.

## Git Hygiene

The repository tracks source code, data, tests, GUI assets, and formal project documentation. Local virtual environment folders and files such as `Lib/`, `Scripts/`, `pyvenv.cfg`, caches, logs, and IDE metadata are ignored and should not be committed.
