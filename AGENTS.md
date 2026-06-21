# Eagle of Rome Agent Instructions

## Project Paths

- `E:\Eagle of Rome` is for project documents, architecture documents, MVP plans, and historical archives only.
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome` is the active codebase, PyCharm project root, test root, and Codex/DeepSeek handoff root.
- Do not add code, runtime caches, test artifacts, or handoff files under `E:\Eagle of Rome`.
- Apply code changes only under `C:\Users\Kerl\PycharmProjects\Eagle of Rome` unless the user explicitly asks to edit documents.

## Startup Context

At the start of each Codex session for this project, read:

```text
C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents\runtime_profile.md
```

Use it as the runtime baseline for Python, pytest, PyCharm parity, and DeepSeek/Codex handoff rules.

## Runtime

- Python interpreter: `C:\Users\Kerl\AppData\Local\Programs\Python\Python310\python.exe`
- Working directory for code runs: `C:\Users\Kerl\PycharmProjects\Eagle of Rome`
- Test runner: pytest
- Prefer setting these environment variables before Python runs:

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONUNBUFFERED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
```

## DeepSeek/Codex Workflow

- DeepSeek may generate large code changes or patch proposals.
- Codex should read/apply/validate them locally in the active codebase.
- Store handoff reports and review files under:

```text
C:\Users\Kerl\PycharmProjects\Eagle of Rome\.agents
```
- Use `$eor-deepseek-codex-loop` whenever handling DeepSeek code changes, patches, implementation reports, test logs, or next-round fixes.
- If any participant deviates from the required DeepSeek -> Codex review/debug -> DeepSeek feedback loop, Codex must warn before proceeding.

Required loop:

```text
DeepSeek outputs code changes
User places changes in the code project
Codex reads local changes
Codex reviews, runs tests, and diagnoses failures
Codex writes acceptance/debug report and next DeepSeek task
User sends report to DeepSeek
DeepSeek outputs the next change set
Repeat until accepted
```

Warning format:

```text
Workflow warning:
Expected:
Observed:
Correction:
```

## Project Roles

- The user/project manager sends bounded development tasks to the module programmer.
- DeepSeek is the module programmer responsible for producing code changes, patches, implementation reports, and test claims.
- Codex is the system architect and acceptance reviewer. Codex must cooperate with the project manager, review DeepSeek output against EOR development standards, run local debugging/tests, and produce feedback for DeepSeek.
- Codex should repeat the review/debug/feedback loop until the task meets acceptance criteria or is explicitly blocked by missing input.

## DeepSeek Review Protocol

When reviewing DeepSeek output, Codex must:

- Identify the output type: task report, patch summary, handoff, test log, architecture proposal, or status review.
- Read the task brief when available.
- Compare DeepSeek claims against the actual local code and documents.
- Separate functional acceptance from architecture acceptance.
- Check changed files, implementation summary, test command/results, risks, unresolved items, and document/function-index updates when interfaces changed.
- Reject or request rework if DeepSeek bypasses API boundaries, adds business rules to UI command layer, directly mutates private fields without justification, breaks multiplayer information isolation, or claims completion without tests.

Review decisions should use:

```text
PASS
CONDITIONAL_PASS
RETURN_FOR_REWORK
DEFER
```

Review feedback should include:

```text
Decision:
Reasons:
Files reviewed:
Test status:
Architecture risks:
Required DeepSeek changes:
```

## DeepSeek Task Publication Mechanism

Task publication responsibility is split between PM and SA:

- The project manager Agent (PM) owns task intent and priority management: why the task matters, priority, acceptance goal, and delivery expectations.
- The system architect Agent (SA/Codex) owns technical task finalization and publication to DeepSeek.
- PM should first produce a PM-level task intent.
- SA should refine that intent into a technical DeepSeek task brief based on architecture boundary review, allowed scope, forbidden changes, tests, and deliverables.
- SA should send the finalized technical task brief directly to DeepSeek.
- After DeepSeek outputs code, SA must perform code review, architecture review, local debugging, and pytest validation before PM-level acceptance.

Do not treat a PM-level task intent as ready for DeepSeek implementation until SA has finalized the technical task brief.
