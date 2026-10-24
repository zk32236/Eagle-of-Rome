# src/tests/test_gui/test_evidence_root_negatives.py
"""W1a — `evidence_root()` 负例（N1–N7）+ 正控（P1）。

契约源：`02-sa-design/W1a/01-Helper-Contract.md`（EOR20261018-02-SA-W1A-01）§6.1/§7；
设计表：`02-Migration-and-Negatives.md` §6.2。

RED-first（G1 §3）：helper 未就位时本模块 6 个用例**全部 FAIL**
（`W1a-RED: helper absent`），不使用 `skip` / `xfail` 掩盖。helper 就位后 6/6 PASS。

断言要旨（D3 可审计）：
  * `exc.code` 精确匹配；
  * 消息含 `[EVIDENCE_PATH_DENIED]` + `target` + `allowed_roots` + `call_site`；
  * 每个 `allowed_roots` 成员都能在消息里逐项读到；
  * 越界尝试**不得**产生任何文件/目录（副作用零写）。

边界（不夸大，RR-W1a-04）：本文件只证明 **helper 会拒绝越界写**，
不证明「归档区已不可写」——W1a 只覆盖 5 个模块。
"""
import os
import sys

import pytest

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_EOR_ROOT = os.path.normpath(os.environ.get("EOR_ASSET_ROOT", "/mnt/e/OpenClaw/Projects/EOR"))
_ARCHIVE_TASK = "EOR20260821-01 GUI-BETA-R1"
_ARCHIVE_EVIDENCE = os.path.join(_EOR_ROOT, "workspace", _ARCHIVE_TASK, "03-da-evidence")
_SENTINEL = "w1a-negative-sentinel.png"

try:
    from src.tests._evidence_root import EvidencePathViolation, evidence_root

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001  (RED-first: absence must FAIL, never skip)
    EvidencePathViolation = None
    evidence_root = None
    _IMPORT_ERROR = exc


def _require_helper():
    """RED 门：helper 必须存在；缺失 → 每个用例 FAIL（不是 skip）。"""
    if _IMPORT_ERROR is not None:
        pytest.fail(
            "W1a-RED: helper absent (%s: %s)"
            % (type(_IMPORT_ERROR).__name__, _IMPORT_ERROR)
        )


def _assert_denied(exc, code, target_fragment):
    """共同断言（契约 §7 消息模板逐字契约）。"""
    msg = str(exc.value)
    assert exc.value.code == code, (exc.value.code, code)
    assert "[EVIDENCE_PATH_DENIED]" in msg
    assert "target" in msg and "allowed_roots" in msg and "call_site" in msg
    assert target_fragment in msg, msg
    assert exc.value.allowed_roots, "allowed_roots 必须非空"
    for r in exc.value.allowed_roots:  # D3：每个允许根都必须可读
        assert r in msg, (r, msg)


def _dir_state(path):
    """目录快照（mtime_ns + 前 60 个成员的 mtime_ns），用于证明零写。"""
    try:
        st = os.stat(path)
    except OSError:
        return None
    members = {}
    for name in sorted(os.listdir(path))[:60]:
        try:
            members[name] = os.stat(os.path.join(path, name)).st_mtime_ns
        except OSError:
            members[name] = None
    return (st.st_mtime_ns, members)


# ---------------------------------------------------------------- N1
def test_negative_absolute_project_path_denied(tmp_path):
    """N1：绝对路径（产品根内真实文件）→ PART_INVALID。"""
    _require_helper()
    root = evidence_root(tmp_path)
    abs_target = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml", "Main.qml")
    with pytest.raises(EvidencePathViolation) as exc:
        root.path(abs_target)
    _assert_denied(exc, "PART_INVALID", abs_target)
    # 零副作用：helper 不得在根下造出该文件的影子
    assert not os.path.exists(os.path.join(str(root.root), "Main.qml"))


# ---------------------------------------------------------------- N2
def test_negative_archived_task_evidence_denied(tmp_path, monkeypatch):
    """N2：① 组件 `03-da-evidence` → PROTECTED_PATH；② 持久化指向真归档区 → PERSIST_ROOT_NOT_REGISTERED。"""
    _require_helper()
    root = evidence_root(tmp_path)
    before = _dir_state(_ARCHIVE_EVIDENCE)

    with pytest.raises(EvidencePathViolation) as exc:
        root.ensure_dir("03-da-evidence", _ARCHIVE_TASK, _SENTINEL)
    _assert_denied(exc, "PROTECTED_PATH", "03-da-evidence")

    monkeypatch.setenv("EOR_TEST_EVIDENCE_PERSIST", "1")
    monkeypatch.setenv("EOR_TEST_EVIDENCE_ROOT", _ARCHIVE_EVIDENCE)
    with pytest.raises(EvidencePathViolation) as exc2:
        evidence_root(None, namespace="EOR20261018-02")
    _assert_denied(exc2, "PERSIST_ROOT_NOT_REGISTERED", _ARCHIVE_TASK)

    # 零写：哨兵不存在，归档目录状态（mtime）与用例前一致
    assert not os.path.exists(os.path.join(_ARCHIVE_EVIDENCE, _SENTINEL))
    assert _dir_state(_ARCHIVE_EVIDENCE) == before


# ---------------------------------------------------------------- N3
def test_negative_symlink_escape_denied(tmp_path):
    """N3：根内 symlink 指向归档区 → SYMLINK_ESCAPE（解析后落点必须在消息里）。"""
    _require_helper()
    root = evidence_root(tmp_path)
    link = os.path.join(str(root.root), "link")
    try:
        os.symlink(_ARCHIVE_EVIDENCE, link)
    except (OSError, NotImplementedError) as exc:  # ENV：无 symlink 能力
        pytest.skip(
            "ENV: symlink unsupported (%s): SYMLINK_ESCAPE AC 未证（G5 记 EVIDENCE_INCOMPLETE）"
            % exc
        )
    try:
        with pytest.raises(EvidencePathViolation) as exc:
            root.path("link", _SENTINEL)
        _assert_denied(exc, "SYMLINK_ESCAPE", _SENTINEL)
        assert _ARCHIVE_TASK in str(exc.value), str(exc.value)  # 解析后落点
        assert not os.path.exists(os.path.join(_ARCHIVE_EVIDENCE, _SENTINEL))
    finally:
        os.unlink(link)


# ---------------------------------------------------------------- N4
def test_negative_namespace_injection_denied(tmp_path):
    """N4：namespace 注入（`../evil` / `a/b` 两腿）→ NAMESPACE_INVALID，根外不建目录。"""
    _require_helper()
    for bad in ("../evil", "a/b"):
        with pytest.raises(EvidencePathViolation) as exc:
            evidence_root(tmp_path, namespace=bad)
        _assert_denied(exc, "NAMESPACE_INVALID", bad)
    assert not os.path.exists(os.path.join(str(tmp_path), "evil"))
    assert not os.path.exists(os.path.join(os.path.dirname(str(tmp_path)), "evil"))
    assert not os.path.exists(os.path.join(str(tmp_path), "a"))


# ---------------------------------------------------------------- N5
def test_negative_persist_not_enabled_in_w1a(tmp_path, monkeypatch):
    """N5：PERSIST=1 + registry 合法根 + 合法 task-id → PERSIST_NOT_ENABLED_W1A（W1a 全 registry=False）。"""
    _require_helper()
    monkeypatch.setenv("EOR_TEST_EVIDENCE_PERSIST", "1")
    monkeypatch.setenv("EOR_TEST_EVIDENCE_ROOT", os.path.join(PROJECT_ROOT, "tests", "_artifacts"))
    with pytest.raises(EvidencePathViolation) as exc:
        evidence_root(None, namespace="EOR20261018-02")
    _assert_denied(exc, "PERSIST_NOT_ENABLED_W1A", "REPO_ARTIFACTS")
    assert not os.path.exists(
        os.path.join(PROJECT_ROOT, "tests", "_artifacts", "EOR20261018-02")
    )


# ---------------------------------------------------------------- N6（TD-01 V1-a）
def test_negative_preexisting_provenance_symlink_denied(tmp_path):
    """N6（TD-01 V1-a）：既有 `_evidence_root.json` 是指向根外的符号链接
    → `SYMLINK_ESCAPE`，且**不得跟随写入**（根外目标内容与 mtime 均不变）。

    这是「既有文件」场景，不是并发竞态：修复前 `open(target, "w")` 会截断根外目标。
    """
    _require_helper()
    root_dir = os.path.join(str(tmp_path), ".eor-evidence")
    os.makedirs(root_dir, exist_ok=True)
    outside_dir = os.path.join(str(tmp_path), "outside-root")
    os.makedirs(outside_dir, exist_ok=True)
    sentinel = os.path.join(outside_dir, "sentinel.json")
    body = '{"sentinel": "must-not-be-overwritten"}\n'
    with open(sentinel, "w", encoding="utf-8") as fh:
        fh.write(body)
    before_mtime = os.stat(sentinel).st_mtime_ns

    link = os.path.join(root_dir, "_evidence_root.json")
    os.symlink(sentinel, link)  # ENV 不支持 symlink → FAIL（TD-01 禁新 skip）

    with pytest.raises(EvidencePathViolation) as exc:
        evidence_root(tmp_path)
    _assert_denied(exc, "SYMLINK_ESCAPE", "_evidence_root.json")
    msg = str(exc.value)
    # 消息必须同时给出 root 与真实 caller（TD-01 断言要求：target/root/call_site）
    assert str(tmp_path) in msg or os.path.realpath(str(tmp_path)) in msg, msg
    assert "test_evidence_root_negatives.py" in msg, msg
    assert os.path.islink(link), "既有链接不得被删除/替换"

    with open(sentinel, "r", encoding="utf-8") as fh:
        assert fh.read() == body, "根外目标被改写（V1-a 未修）"
    assert os.stat(sentinel).st_mtime_ns == before_mtime, "根外目标 mtime 变化（V1-a 未修）"


# ---------------------------------------------------------------- N7（TD-01 V1-b）
def test_negative_root_parent_escape_rejected_before_creation(tmp_path):
    """N7（TD-01 V1-b）：`<base>/.eor-evidence` 预置为指向根外的符号链接。

    腿 A：对端 namespace 目录尚不存在（旧实现 `makedirs` 先建、后判 containment）
    腿 B：对端已存在同名目录（必须原样保留，不得改动内容）
    两腿都必须 `SYMLINK_ESCAPE` 且**零根外副作用**。
    """
    _require_helper()
    for leg in ("link-to-empty", "link-to-existing-ns"):
        base = os.path.join(str(tmp_path), "base-%s" % leg)
        os.makedirs(base, exist_ok=True)
        outside = os.path.join(str(tmp_path), "outside-%s" % leg)
        os.makedirs(outside, exist_ok=True)
        marker = None
        if leg == "link-to-existing-ns":
            ns_dir = os.path.join(outside, "run1")
            os.makedirs(ns_dir, exist_ok=True)
            marker = os.path.join(ns_dir, "marker.txt")
            with open(marker, "w", encoding="utf-8") as fh:
                fh.write("keep\n")
        os.symlink(outside, os.path.join(base, ".eor-evidence"))

        before = sorted(os.listdir(outside))
        with pytest.raises(EvidencePathViolation) as exc:
            evidence_root(base, namespace="run1")
        _assert_denied(exc, "SYMLINK_ESCAPE", "run1")

        after = sorted(os.listdir(outside))
        assert after == before, "根外目录被创建/改动（V1-b 未修）: %s -> %s" % (before, after)
        assert not os.path.exists(os.path.join(outside, "run1")) or marker is not None
        if marker is not None:
            with open(marker, "r", encoding="utf-8") as fh:
                assert fh.read() == "keep\n"


# ---------------------------------------------------------------- P1（正控）
def test_positive_tmp_root_allows_nested_write(tmp_path):
    """P1：正控 —— 根内嵌套目录 + 1 字节写入必须成功（证明不是「一律拒绝」）。"""
    _require_helper()
    root = evidence_root(tmp_path)
    out_dir = root.ensure_dir("Group-A-1")
    assert str(root.root) in out_dir, (root.root, out_dir)
    target = root.path("Group-A-1", "positive-control.txt")
    with open(target, "w", encoding="utf-8") as fh:
        fh.write("x")
    assert os.path.isfile(target) and os.path.getsize(target) == 1
    assert os.path.realpath(target).startswith(os.path.realpath(str(tmp_path)))
