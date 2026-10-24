# src/tests/_evidence_root.py
"""W1a — 测试证据写根 helper（默认 tmp 派生根；越界 fail-closed）。

契约源：`EOR20261018-02-SA-W1A-01`（`02-sa-design/W1a/01-Helper-Contract.md`）。
本模块只决定「测试证据可以写到哪里」，不代写任何证据文件。

不变量（01 §1）：I1 默认根 = `<pytest tmp base>/.eor-evidence/**`；I2 归一化目标必须严格包含于
根内（commonpath，非 startswith）；I3 组件命中受保护集（03-da-evidence / 04-sa-verify /
99 完工目录 / .git）→ 拒；I4 符号链接解析后逃出根 → 拒；I5 持久化需 registry + enabled +
合法 task-id + 显式 opt-in env；I6 无隐式兜底（拿不到 tmp 基 / 不可写 / registry 未启用 → 报错，
绝不回落固定目录）。

模式（01 §4）：T0 TMP `evidence_root(tmp_path)`（W1a 唯一启用）；T1 PERSIST
`evidence_root(None, namespace=task_id)`（代码就位，registry 全 `enabled=False`）；
T2 FORMAL **无 API**（deny-by-absence：正式 03-da-evidence / 04-sa-verify 证据不走本 helper）。

依赖：仅标准库；**不 import pytest**（tmp 基由调用方传入）；不改任何 ini/toml/conftest。
"""
import errno
import json
import os
import re
import secrets
import stat
import traceback
from datetime import datetime, timezone

__all__ = ["EvidencePathViolation", "EvidenceRoot", "evidence_root"]

_MODULE_PATH = os.path.normcase(os.path.realpath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
_EOR_ROOT = os.path.normpath(os.environ.get("EOR_ASSET_ROOT") or "/mnt/e/OpenClaw/Projects/EOR")

_T0_ROOT_NAME = ".eor-evidence"
_PROTECTED_COMPONENTS = ("03-da-evidence", "04-sa-verify", "99 完工目录", ".git")
_PROTECTED_COMPONENTS_CF = frozenset(c.casefold() for c in _PROTECTED_COMPONENTS)
_RESERVED_NAMES = frozenset({"con", "prn", "aux", "nul"} | {"com%d" % i for i in range(1, 10)}
                            | {"lpt%d" % i for i in range(1, 10)})
_NS_T0_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_NS_T1_RE = re.compile(r"^EOR\d{8}-\d{2}$")
_ENV_PERSIST = "EOR_TEST_EVIDENCE_PERSIST"
_ENV_ROOT = "EOR_TEST_EVIDENCE_ROOT"

# 代码常量（不是配置文件）；`enabled=False` ⇒ W1a 一律拒写（01 §5）
_REGISTERED_PERSIST_ROOTS = (
    {"id": "REPO_ARTIFACTS", "path": os.path.join(_REPO_ROOT, "tests", "_artifacts"), "enabled": False},
    {"id": "ASSET_ARTIFACTS", "path": os.path.join(_EOR_ROOT, "workspace", "_test-artifacts"),
     "enabled": False},
)

# A4/P3：卷根与 OS 全局临时根 —— 仅等值判定（子目录不拒，否则 tmp_path 自身会被误杀）
_EQUALITY_ROOTS = (os.path.abspath(os.sep), "/tmp", "/var/tmp",
                   os.environ.get("TEMP") or "", os.environ.get("TMP") or "")


def _nc(path):
    return os.path.normcase(os.path.normpath(path))


def _within(path_nc, prefix_nc):
    """commonpath 包含判定（不用 startswith：'/a/Group-evil' 不是 '/a/Group' 的子路径）。"""
    if path_nc == prefix_nc:
        return True
    try:
        return os.path.commonpath([path_nc, prefix_nc]) == prefix_nc
    except ValueError:
        return False


def _call_site():
    """helper 外的第一帧（报告指向真实 caller，而不是本模块内部）。"""
    for frame in reversed(traceback.extract_stack()):
        try:
            filename_nc = os.path.normcase(os.path.realpath(frame.filename))
        except OSError:  # pragma: no cover
            filename_nc = os.path.normcase(frame.filename)
        if filename_nc != _MODULE_PATH:
            return "%s:%d in %s" % (frame.filename, frame.lineno, frame.name)
    return "<unknown>"  # pragma: no cover


class EvidencePathViolation(RuntimeError):
    """越界/非法证据写路径（fail-closed）。`str(exc)` 即 01 §7 消息模板。"""

    def __init__(self, code, target, allowed_roots, detail, call_site=None):
        self.code, self.target, self.detail = code, target, detail
        self.allowed_roots = tuple(str(r) for r in allowed_roots)
        self.call_site = call_site or _call_site()
        super().__init__(self._render())

    def _render(self):
        return ("[EVIDENCE_PATH_DENIED] code=%s\n"
                "  target        : %s\n"
                "  allowed_roots : [%s]\n"
                "  detail        : %s\n"
                "  call_site     : %s" % (self.code, self.target, ", ".join(self.allowed_roots),
                                          self.detail, self.call_site))

    def __str__(self):
        return self._render()


def _deny(code, target, allowed_roots, detail):
    raise EvidencePathViolation(code, target, allowed_roots, detail)


def _oserr(target, exc, allowed_roots):
    _deny("PERMISSION_DENIED", target, allowed_roots,
          "%s: %s" % (errno.errorcode.get(exc.errno, "E?"), exc.strerror or exc))


def _registry_paths():
    return tuple(entry["path"] for entry in _REGISTERED_PERSIST_ROOTS)


def _registry_enabled(path_nc):
    return any(entry["enabled"] and _within(path_nc, _nc(os.path.realpath(entry["path"])))
               for entry in _REGISTERED_PERSIST_ROOTS)


def _check_global_denies(target, allowed_roots):
    """A4：P4 src/.git（前缀，无例外）、P1 EOR workspace、P2 repo（各带 registry 例外）、P3 等值。"""
    p4 = (_nc(os.path.join(_REPO_ROOT, "src")), _nc(os.path.join(_REPO_ROOT, ".git")))
    ws, ws_exc = _nc(os.path.join(_EOR_ROOT, "workspace")), _nc(
        os.path.join(_EOR_ROOT, "workspace", "_test-artifacts"))
    repo, repo_exc = _nc(_REPO_ROOT), _nc(os.path.join(_REPO_ROOT, "tests", "_artifacts"))
    for cand in (_nc(target), _nc(os.path.realpath(target))):
        for pref in p4:
            if _within(cand, pref):
                _deny("PROTECTED_PATH", target, allowed_roots, "protected prefix '%s'" % pref)
        if _within(cand, ws) and not (_within(cand, ws_exc) and _registry_enabled(cand)):
            _deny("PROTECTED_PATH", target, allowed_roots,
                  "protected prefix '%s' (EOR workspace / archive area)" % ws)
        if _within(cand, repo) and not (_within(cand, repo_exc) and _registry_enabled(cand)):
            _deny("PROTECTED_PATH", target, allowed_roots,
                  "protected prefix '%s' (product repo)" % repo)
        for eq in _EQUALITY_ROOTS:
            if eq and cand == _nc(eq):
                _deny("PROTECTED_PATH", target, allowed_roots,
                      "refusing to write at a volume/temp root itself: '%s'" % eq)


def _check_protected_components(target, allowed_roots):
    """A5：逐层组件扫描（casefold）。"""
    for base in (os.path.abspath(target), os.path.realpath(target)):
        for name in base.replace("\\", "/").split("/"):
            if name and name.casefold() in _PROTECTED_COMPONENTS_CF:
                _deny("PROTECTED_PATH", target, allowed_roots, "protected component '%s'" % name)


def _check_symlinks(target, root_real, allowed_roots):
    """A6：target 自身是链接 → 拒；已存在祖先为链接且解析后逃出根 → 拒。"""
    if os.path.islink(target):
        _deny("SYMLINK_ESCAPE", target, allowed_roots,
              "target is a symlink -> %s" % os.path.realpath(target))
    root_abs, probe = _nc(os.path.abspath(root_real)), os.path.dirname(os.path.abspath(target))
    while True:
        if os.path.islink(probe):
            landed = os.path.realpath(probe)
            if not _within(_nc(landed), _nc(root_real)):
                _deny("SYMLINK_ESCAPE", target, allowed_roots,
                      "ancestor '%s' resolves to '%s' (outside root)" % (probe, landed))
        if _nc(probe) == root_abs:
            break
        parent = os.path.dirname(probe)
        if parent == probe:  # pragma: no cover
            break
        probe = parent


def _check_containment(target, root_real, allowed_roots):
    """A7：commonpath 包含判定（realpath 归一后）。"""
    target_nc, root_nc = _nc(os.path.realpath(target)), _nc(os.path.realpath(root_real))
    try:
        common = _nc(os.path.commonpath([target_nc, root_nc]))
    except ValueError:  # pragma: no cover  (不同卷)
        _deny("TARGET_OUTSIDE_ROOT", target, allowed_roots, "target and root are on different roots")
    if common != root_nc:
        _deny("TARGET_OUTSIDE_ROOT", target, allowed_roots,
              "normalized target is not inside root '%s'" % root_real)


def _draft(root, part):
    try:
        return os.path.normpath(os.path.join(root, part))
    except (TypeError, ValueError):  # pragma: no cover
        return str(part)


def _check_part(part, root, allowed_roots):
    """单段校验（每段都做；绝对段/f 分隔符在拼接前拦下）。"""
    if not isinstance(part, str):
        _deny("PART_INVALID", root, allowed_roots, "part must be str, got %s" % type(part).__name__)
    reason = None
    if not part:
        reason = "empty part"
    elif "\x00" in part:
        reason = "part contains NUL: %r" % part
    elif os.path.isabs(part):
        reason = "part is an absolute path: %r" % part
    elif os.sep in part or (os.altsep and os.altsep in part) or "/" in part or "\\" in part:
        reason = "part contains a path separator: %r" % part
    elif part in (".", ".."):
        reason = "part is a traversal token: %r" % part
    elif len(part) > 255:
        reason = "part longer than 255 characters"
    elif part.rstrip() != part or part.endswith("."):
        reason = "part ends with a space or a dot: %r" % part
    elif part.split(".")[0].casefold() in _RESERVED_NAMES:
        reason = "part is a Windows reserved device name: %r" % part
    if reason:
        _deny("PART_INVALID", _draft(root, part), allowed_roots, reason)


class EvidenceRoot:
    """本次测试的证据写根（T0/T1）。`path()`/`ensure_dir()` 每次调用都重跑 A5–A7。"""

    def __init__(self, mode, root, base, run_id, namespace, allowed_roots):
        self.mode, self.root, self.base = mode, str(root), str(base)
        self.run_id, self.namespace = run_id, namespace
        self.allowed_roots = tuple(str(r) for r in allowed_roots)

    def path(self, *parts):
        """校验并返回绝对路径字符串；**不建目录、不写盘**。"""
        for part in parts:
            _check_part(part, self.root, self.allowed_roots)
        target = self.root if not parts else os.path.normpath(os.path.join(self.root, *parts))
        _check_symlinks(target, self.root, self.allowed_roots)
        _check_global_denies(target, self.allowed_roots)
        _check_protected_components(target, self.allowed_roots)
        _check_containment(target, self.root, self.allowed_roots)
        return target

    def ensure_dir(self, *parts):
        """校验 + `os.makedirs(exist_ok=True)`；返回与 `path()` 相同的结果。"""
        target = self.path(*parts)
        try:
            os.makedirs(target, exist_ok=True)
        except OSError as exc:
            _oserr(target, exc, self.allowed_roots)
        return target

    def describe(self):
        """provenance（写入 `<root>/_evidence_root.json`）。"""
        return {
            "schema": "eor-evidence-root/v1", "mode": self.mode, "root": self.root,
            "base": self.base, "namespace": self.namespace, "run_id": self.run_id,
            "allowed_roots": list(self.allowed_roots),
            "protected_components": list(_PROTECTED_COMPONENTS),
            "generated_by": "src/tests/_evidence_root.py",
            "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    def _write_provenance(self):
        """provenance 写入（TD-01 V1-a：先校验、后打开；符号链接一律拒）。

        旧实现直接 `open(target, "w")`：既有 `_evidence_root.json` 若是指向根外的符号链接，
        会被跟随并截断根外文件。此处按 A5–A7 同一套校验先跑一遍，再加 lstat（不跟随）与
        `O_NOFOLLOW`（竞态兜底）打开，写后复检真实落点仍在根内。
        """
        target = os.path.join(self.root, "_evidence_root.json")
        _check_symlinks(target, self.root, self.allowed_roots)
        _check_global_denies(target, self.allowed_roots)
        _check_protected_components(target, self.allowed_roots)
        _check_containment(target, self.root, self.allowed_roots)
        try:
            st = os.lstat(target)  # 不跟随：链接本身的状态
        except FileNotFoundError:
            st = None
        except OSError as exc:
            _oserr(target, exc, self.allowed_roots)
        if st is not None:
            if stat.S_ISLNK(st.st_mode):
                _deny("SYMLINK_ESCAPE", target, self.allowed_roots,
                      "provenance target is a symlink -> %s (root: %s)"
                      % (os.path.realpath(target), self.root))
            if not stat.S_ISREG(st.st_mode):
                _deny("PERMISSION_DENIED", target, self.allowed_roots,
                      "provenance target exists and is not a regular file (root: %s)" % self.root)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(target, flags, 0o600)
        except OSError as exc:
            if exc.errno in (errno.ELOOP, errno.EMLINK):
                _deny("SYMLINK_ESCAPE", target, self.allowed_roots,
                      "provenance target became a symlink at open -> %s (root: %s)"
                      % (os.path.realpath(target), self.root))
            _oserr(target, exc, self.allowed_roots)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.describe(), fh, ensure_ascii=False, indent=2, sort_keys=True)
                fh.write("\n")
        except OSError as exc:
            _oserr(target, exc, self.allowed_roots)
        _check_containment(target, self.root, self.allowed_roots)  # 写后复检


def _check_namespace_t0(namespace, allowed_roots, base_real):
    if not isinstance(namespace, str) or not _NS_T0_RE.match(namespace):
        _deny("NAMESPACE_INVALID", os.path.join(base_real, _T0_ROOT_NAME, str(namespace)),
              allowed_roots, "namespace %r does not match %s" % (namespace, _NS_T0_RE.pattern))


def _create_root(mode, root_raw, base, run_id, namespace, allowed_roots, require_inside_base):
    """建根（TD-01 V1-b：**先校验、后创建**；创建后再复检；失败零副作用）。"""
    _check_preexisting_chain(root_raw, base, allowed_roots, require_inside_base)
    missing = _missing_chain(root_raw)
    try:
        os.makedirs(root_raw, exist_ok=(mode == "TMP"))
    except FileExistsError:
        _rollback(missing)
        _deny("RUN_CONFLICT", root_raw, allowed_roots, "run-id directory already exists")
    except OSError as exc:
        _rollback(missing)
        _oserr(root_raw, exc, allowed_roots)
    root_real = os.path.realpath(root_raw)
    roots = tuple(dict.fromkeys((root_real, base) + tuple(allowed_roots)))
    try:
        if os.path.islink(root_raw):
            _deny("SYMLINK_ESCAPE", root_raw, roots,
                  "root became a symlink after creation -> %s" % root_real)
        _check_global_denies(root_real, roots)
        _check_protected_components(root_real, roots)
        if require_inside_base:  # T0：根必须仍在 tmp 基内
            _check_containment(root_real, base, roots)
        root = EvidenceRoot(mode, root_real, base, run_id, namespace, roots)
        root._write_provenance()
    except EvidencePathViolation:
        _rollback(missing)  # 失败零副作用：只删本次新建的空目录（深→浅）
        raise
    return root


def _missing_chain(target):
    """从 target 起尚未存在的祖先链（深→浅），用于失败回滚。"""
    missing, cur = [], os.path.abspath(target)
    while not os.path.lexists(cur):
        missing.append(cur)
        parent = os.path.dirname(cur)
        if parent == cur:  # pragma: no cover
            break
        cur = parent
    return missing


def _rollback(missing):
    """只删「本次新建且仍为空」的目录；既有目录/文件绝不动。"""
    for path in missing:  # 深→浅
        try:
            os.rmdir(path)
        except OSError:  # pragma: no cover
            pass


def _check_preexisting_chain(target, base_real, allowed_roots, require_inside_base):
    """TD-01 V1-b：创建**之前**的校验（完全无副作用）。

    覆盖：目标本身是链接；已存在祖先为链接且解析后逃出 base；已存在祖先不是目录。
    旧实现的 `makedirs` 先于 containment 判定，可能在根外造出目录后才拒绝。
    """
    target_abs = os.path.normpath(os.path.abspath(target))
    if require_inside_base and not _within(_nc(target_abs), _nc(base_real)):
        _deny("TARGET_OUTSIDE_ROOT", target, allowed_roots,
              "draft root is outside base '%s' before creation" % base_real)
    if os.path.islink(target_abs):
        _deny("SYMLINK_ESCAPE", target, allowed_roots,
              "draft root is a symlink -> %s (root: %s)" % (os.path.realpath(target_abs), base_real))
    probe = target_abs
    while not os.path.lexists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:  # pragma: no cover
            break
        probe = parent
    if not os.path.isdir(probe) and not os.path.islink(probe):
        _deny("PERMISSION_DENIED", target, allowed_roots,
              "existing ancestor '%s' is not a directory" % probe)
    cur = probe
    while True:
        if os.path.islink(cur):
            landed = os.path.realpath(cur)
            if require_inside_base and not _within(_nc(landed), _nc(base_real)):
                _deny("SYMLINK_ESCAPE", target, allowed_roots,
                      "pre-existing component '%s' resolves to '%s' (outside root '%s')"
                      % (cur, landed, base_real))
        if _nc(cur) == _nc(base_real):
            break
        parent = os.path.dirname(cur)
        if parent == cur:  # pragma: no cover
            break
        cur = parent


def _tmp_root(base, namespace):
    base_abs = os.path.abspath(os.fspath(base))
    if not os.path.isdir(base_abs):
        _deny("BASE_MISSING", base_abs, (base_abs,),
              "base is not an existing directory; pass pytest tmp_path / tmp_path_factory")
    base_real = os.path.realpath(base_abs)
    if not os.path.isdir(base_real):
        _deny("BASE_MISSING", base_real, (base_abs,),
              "base realpath is not a directory; pass pytest tmp_path / tmp_path_factory")
    if namespace is None:
        root_raw = os.path.join(base_real, _T0_ROOT_NAME)
    else:
        _check_namespace_t0(namespace, (base_real,), base_real)
        root_raw = os.path.join(base_real, _T0_ROOT_NAME, namespace)
    # 建目录前先 deny 检查（fail-closed：绝不为被拒路径创造目录）
    _check_global_denies(root_raw, (base_real,))
    _check_protected_components(root_raw, (base_real,))
    return _create_root("TMP", root_raw, base_real, None, namespace, (base_real,), True)


def _persist_root(namespace):
    registry = _registry_paths()
    if not isinstance(namespace, str) or not _NS_T1_RE.match(namespace):
        _deny("NAMESPACE_INVALID", str(namespace), registry,
              "T1 namespace must be a task id matching %s" % _NS_T1_RE.pattern)
    env_root = os.environ.get(_ENV_ROOT) or _REGISTERED_PERSIST_ROOTS[0]["path"]
    base_real = os.path.realpath(env_root)
    draft = os.path.join(base_real, namespace)
    if os.environ.get(_ENV_PERSIST) != "1":
        _deny("PERSIST_DISABLED", draft, registry,
              "env %s must be '1' (explicit opt-in)" % _ENV_PERSIST)
    entry, env_root_nc = None, _nc(base_real)
    for candidate in _REGISTERED_PERSIST_ROOTS:
        if _within(env_root_nc, _nc(os.path.realpath(candidate["path"]))):
            entry = candidate
            break
    if entry is None:
        _deny("PERSIST_ROOT_NOT_REGISTERED", draft, registry,
              "env %s=%r is not under any registered persist root; registry=%s"
              % (_ENV_ROOT, env_root, ", ".join(registry)))
    if not entry["enabled"]:
        _deny("PERSIST_NOT_ENABLED_W1A", draft, registry,
              "registry '%s' enabled=False — W1a 只做默认根 (tmp); persistent roots arrive in W2"
              % entry["id"])
    run_id = "%s-%s" % (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                        secrets.token_hex(3))
    root_raw = os.path.join(base_real, namespace, run_id)
    _check_global_denies(root_raw, registry)
    _check_protected_components(root_raw, registry)
    return _create_root("PERSIST", root_raw, base_real, run_id, namespace, registry, False)


def evidence_root(base=None, *, namespace=None):
    """返回本次测试的证据写根。

    base 给定 → T0：root = `<base>/.eor-evidence[/<namespace>]`
    base 缺省 → T1：必须给 task-id namespace 且满足 I5（W1a 下 registry 全 False ⇒ 拒）
    两者都缺省 → TypeError（fail-closed，不做任何猜测）
    """
    if base is None and namespace is None:
        raise TypeError("evidence_root() requires a tmp base (T0) or a task-id namespace (T1); "
                        "refusing to guess a default evidence root")
    if base is not None:
        return _tmp_root(base, namespace)
    return _persist_root(namespace)
