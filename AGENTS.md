# Eagle of Rome Agent Instructions

## Project Paths

- `C:\Users\Kerl\PycharmProjects\Eagle of Rome` is the only official project root, Git repository root, code root, documentation root, PyCharm project root, test root, and Codex/DeepSeek handoff root.
- `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs` is the official documentation root for architecture documents, MVP plans, task briefs, acceptance reports, audit reports, and historical documentation baselines.
- `E:\Eagle of Rome` is now only a legacy document workspace and historical source. Do not use it as the official collaboration baseline after 2026-06-28.
- Apply code changes only under `C:\Users\Kerl\PycharmProjects\Eagle of Rome`.
- Store formal task briefs and acceptance reports under `C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理\...` unless a task explicitly says otherwise.
- Do not add code, runtime caches, test artifacts, or handoff files under `E:\Eagle of Rome`.

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

Store formal project-management records, task briefs, SA/CGT/KIMI acceptance reports, and audit reports under:

```text
C:\Users\Kerl\PycharmProjects\Eagle of Rome\docs\MVP 0.9 项目管理
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

## SA Test Reuse Policy

When CGT-01 or another implementation Agent has already run full regression tests, Codex/SA does not rerun the full suite by default. SA should instead verify that the implementation matches the approved task/design, inspect the changed files or diff, and confirm that the Agent's acceptance report satisfies the task's required test scope.

SA may rely on the Agent's full-test result only when the report includes the exact command, environment assumptions, pass/fail count, and no unresolved failure. In the SA response, state that the full regression was accepted from the Agent report and was not rerun by SA.

SA should still run targeted tests, smoke checks, or the full suite when evidence is missing or stale, the reported result conflicts with the local diff, the change touches test infrastructure, dependency/bootstrap code, persistence, global state, or other high-risk shared paths, or the user explicitly requests an independent rerun.
## DeepSeek Task Publication Mechanism

Task publication responsibility is split between PM and SA:

- The project manager Agent (PM) owns task intent and priority management: why the task matters, priority, acceptance goal, and delivery expectations.
- The system architect Agent (SA/Codex) owns technical task finalization and publication to DeepSeek.
- PM should first produce a PM-level task intent.
- SA should refine that intent into a technical DeepSeek task brief based on architecture boundary review, allowed scope, forbidden changes, tests, and deliverables.
- SA should send the finalized technical task brief directly to DeepSeek.
- After DeepSeek outputs code, SA must perform code review, architecture review, local debugging, and pytest validation before PM-level acceptance.

Do not treat a PM-level task intent as ready for DeepSeek implementation until SA has finalized the technical task brief.
