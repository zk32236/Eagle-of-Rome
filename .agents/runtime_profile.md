# EOR Codex Runtime Profile

Updated: 2026-06-28

## Status

This is the active Codex/PyCharm runtime baseline for Eagle of Rome.

Since 2026-06-28, the project uses a unified code + documentation Git repository baseline. New agents should treat the C-drive project root as the only official collaboration baseline.

## Active PyCharm Project

| Item | Value |
| --- | --- |
| Project root | `C:\Users\Kerl\PycharmProjects\Eagle of Rome` |
| Official docs root | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs` |
| Official PM docs | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理` |
| PyCharm config | `.idea` exists under project root. |
| Main run configuration | `Python.main` from `.idea\workspace.xml` |
| Main script | `$PROJECT_DIR$/main.py` |
| Main working directory | `$PROJECT_DIR$` |
| Main environment | `PYTHONUNBUFFERED=1` |
| Test runner | pytest (`py.test` in PyCharm config) |
| Source roots | project root and `$PROJECT_DIR$/src` |

## Interpreter Baseline

User-confirmed interpreter:

```text
C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe
```

Verified:

| Check | Result |
| --- | --- |
| Python version | `Python 3.10.6` |
| pytest availability | `pytest 9.0.2` available |
| Equivalent pytest command | Verified with `src\tests\test_core\test_contract_ext.py`: `5 passed` |

Project-local virtualenv also exists:

```text
C:\Users\Kerl\PycharmProjects\Eagle of Rome\Scripts\python.exe
```

But this interpreter currently does **not** have pytest installed. Codex should not use it for test validation unless it is explicitly repaired or PyCharm is confirmed to use it for a specific run.

The project-local virtualenv files (`Lib/`, `Scripts/`, `pyvenv.cfg`) are intentionally ignored by Git and should not be committed.

## Unified Repository Baseline

Effective date: 2026-06-28

| Item | Value |
| --- | --- |
| Unified project root | `C:\Users\Kerl\PycharmProjects\Eagle of Rome` |
| Official documentation root | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs` |
| Formal task / acceptance archive | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\03 开发任务书` |
| PM task archive | `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\02_项目任务书` |
| GitHub remote | `https://github.com/zk32236/Eagle-of-Rome.git` |
| Current pushed branch | `debug-phase3-stderr-removal` |

Key integration commits:

```text
ae9b163 repo hygiene before docs integration
963f288 Add project documentation baseline under docs
637d36b Address ZP-01 repository audit findings
```

`E:\Eagle of Rome` is retained only as a legacy document workspace and historical source. Do not archive new task briefs, acceptance reports, audit reports, or code handoffs there unless the user explicitly requests a historical copy.

## Codex Standard Environment

Use these environment variables for command-line parity and readable output:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
```

`PYTHONUTF8=1` avoids Windows console encoding failures with Chinese text and symbols.

`PYTHONDONTWRITEBYTECODE=1` reduces extra `__pycache__` churn during Codex validation.

## Main Program Command

Equivalent to PyCharm `Python.main`:

```powershell
cd "C:\Users\Kerl\PycharmProjects\Eagle of Rome"
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" "C:\Users\Kerl\PycharmProjects\Eagle of Rome\main.py"
```

Note: `main.py` starts the interactive Debug CLI. Codex should run it only when an interactive smoke check is needed.

## Test Commands

Full test suite, equivalent to PyCharm `pytest in tests`:

```powershell
cd "C:\Users\Kerl\PycharmProjects\Eagle of Rome"
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests" -q
```

Common focused test targets from PyCharm configuration:

```powershell
# API tests
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_api" -q

# Systems tests
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_systems" -q

# Contract extension regression
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_core\test_contract_ext.py" -q
```

## Verified Smoke Test

Command run by Codex:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
& "C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe" -m pytest -p no:cacheprovider "C:\Users\Kerl\PycharmProjects\Eagle of Rome\src\tests\test_core\test_contract_ext.py" -q
```

Result:

```text
5 passed in 0.05s
```

## DeepSeek/Codex Handoff Rule

For future DeepSeek output, Codex should treat this directory as the active codebase:

```text
C:\Users\Kerl\PycharmProjects\Eagle of Rome
```

Do not treat the historical document archive at `E:\Eagle of Rome` as the active source root unless a task explicitly references it.

Do not treat the historical document archive at `E:\Eagle of Rome` as the active documentation root. Formal collaboration documents should be created under:

```text
C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理
```

Recommended handoff directory:

```text
C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents
```

Suggested files:

```text
01_deepseek_output.md
02_codex_review.md
03_test_result.md
04_next_deepseek_task.md
05_acceptance_status.md
runtime_profile.md
```
