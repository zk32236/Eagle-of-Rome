# src/tests/test_gui/test_evidence_immutability.py
"""P1-PC-WPE-HARNESS-01 — 冻结截图证据 SHA 保全守卫（确定性，零重生成）。

- 纯文件读 + hashlib.sha256：零 Qt / 零离屏渲染 / 零网络 / 零时间戳 → 任何环境确定性。
- 只 open(path, "rb") 读，绝不写任何证据文件；不调用 _capture/grabWindow/_make_store。
- manifest：03-da-evidence/P1-HARNESS-01/evidence-manifest.sha256，
  格式 `sha256  <relpath>`（relpath 相对 EVIDENCE_ROOT，每行一文件）。
- 覆盖集（26 文件，S0b 实名清单，磁盘 ls 实测一致）：
  WP-E-R3-A2 12（before 6 + after 6）+ WP-E-R4 8（before 4 + after 4）
  + WP-E-R5 4（before 2 + after 2）+ screenshots/g7r-post-click-mortality 2
  （PNG 有日期后缀 2026-08-24、runtime 无日期后缀，P2-4）。
- 显式 regen 模式：env P1_HARNESS_REGEN_MANIFEST=1 → 非收集函数 _regen_manifest()
  确定性重算 26 文件并写 manifest（唯一写路径，opt-in）；默认（无 env）纯读零写。
- 负向测试通道：P1_HARNESS_MANIFEST=<副本路径>（篡改副本注入，不触碰真实 manifest）。
"""
import hashlib
import os

EVIDENCE_ROOT = (
    "/mnt/e/OpenClaw/Projects/EOR/workspace/EOR20260821-01 GUI-BETA-R1"
    "/03-da-evidence"
)
DEFAULT_MANIFEST = os.path.join(EVIDENCE_ROOT, "P1-HARNESS-01", "evidence-manifest.sha256")
MANIFEST = os.environ.get("P1_HARNESS_MANIFEST") or DEFAULT_MANIFEST

# 冻结覆盖集（26 文件；relpath 相对 EVIDENCE_ROOT）
_FROZEN_SET = [
    # WP-E-R3-A2 before/（eb157fb）
    "WP-E-R3-A2/before/revenue-before-eb157fb.png",
    "WP-E-R3-A2/before/revenue-before-eb157fb-runtime.json",
    "WP-E-R3-A2/before/forum-before-eb157fb.png",
    "WP-E-R3-A2/before/forum-before-eb157fb-runtime.json",
    "WP-E-R3-A2/before/combat-before-eb157fb.png",
    "WP-E-R3-A2/before/combat-before-eb157fb-runtime.json",
    # WP-E-R3-A2 after/
    "WP-E-R3-A2/after/revenue-after.png",
    "WP-E-R3-A2/after/revenue-after-runtime.json",
    "WP-E-R3-A2/after/forum-after.png",
    "WP-E-R3-A2/after/forum-after-runtime.json",
    "WP-E-R3-A2/after/combat-after.png",
    "WP-E-R3-A2/after/combat-after-runtime.json",
    # WP-E-R4 before/（1bcb54a）
    "WP-E-R4/before/revenue-before-1bcb54a.png",
    "WP-E-R4/before/revenue-before-1bcb54a-runtime.json",
    "WP-E-R4/before/forum-before-1bcb54a.png",
    "WP-E-R4/before/forum-before-1bcb54a-runtime.json",
    # WP-E-R4 after/
    "WP-E-R4/after/revenue-after.png",
    "WP-E-R4/after/revenue-after-runtime.json",
    "WP-E-R4/after/forum-after.png",
    "WP-E-R4/after/forum-after-runtime.json",
    # WP-E-R5 before/（r5pre）
    "WP-E-R5/before/revenue-before-r5pre.png",
    "WP-E-R5/before/revenue-before-r5pre-runtime.json",
    # WP-E-R5 after/
    "WP-E-R5/after/revenue-after.png",
    "WP-E-R5/after/revenue-after-runtime.json",
    # G7R EC-14（PNG 有日期后缀 / runtime 无日期后缀，P2-4 磁盘实名）
    "screenshots/g7r-post-click-mortality-2026-08-24.png",
    "screenshots/g7r-post-click-mortality-runtime.json",
]


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest(path):
    """解析 manifest：每行 `sha256  <relpath>` → [(relpath, sha256), ...]。"""
    entries = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            digest, relpath = line.split("  ", 1)
            entries.append((relpath, digest))
    return entries


def _regen_manifest():
    """显式 opt-in（P1_HARNESS_REGEN_MANIFEST=1）：确定性重算 26 文件 → 写 manifest。

    - 纯读 EVIDENCE_ROOT 下冻结文件（零重生成），写目标 = MANIFEST（默认真实路径，
      负向/scratch 场景经 P1_HARNESS_MANIFEST 指到副本路径）。
    - os.makedirs 目录兜底（P1-HARNESS-01/ 目录不存在时创建）。
    """
    lines = []
    for relpath in _FROZEN_SET:
        full = os.path.join(EVIDENCE_ROOT, relpath)
        if not os.path.exists(full):
            raise AssertionError(f"missing frozen evidence: {relpath}")
        lines.append(f"{_sha256(full)}  {relpath}")
    out_dir = os.path.dirname(MANIFEST)
    os.makedirs(out_dir, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return len(lines)


def test_frozen_evidence_immutable():
    """冻结证据 SHA 守卫（fail-fast 哨兵）：manifest 内任一文件缺失/漂移 → FAIL。"""
    if os.environ.get("P1_HARNESS_REGEN_MANIFEST") == "1":
        count = _regen_manifest()
        assert count == len(_FROZEN_SET), f"regen wrote {count} != {len(_FROZEN_SET)}"
    entries = _load_manifest(MANIFEST)
    assert entries, f"manifest empty: {MANIFEST}"
    for relpath, expected in entries:
        full = os.path.join(EVIDENCE_ROOT, relpath)
        assert os.path.exists(full), f"missing frozen evidence: {relpath}"
        actual = _sha256(full)
        assert actual == expected, (
            f"FROZEN EVIDENCE MUTATED: {relpath} {actual} != {expected}"
        )
