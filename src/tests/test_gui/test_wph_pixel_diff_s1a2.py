# src/tests/test_gui/test_wph_pixel_diff_s1a2.py
"""WP-H / S1 Attempt-2 — before/after 像素比对（OD-H-02）。

读 `03-da-evidence/S1/baseline-captures/{before,after}-*.png`（G7 截图链产物），
逐像素比对并产 `pixel-diff-report.md`。

运行（safe-bin 全路径；workdir = 产品仓）：
  WPH_CAPTURE_DIR="<...>/03-da-evidence/S1/baseline-captures" \
    /home/openclaw/.openclaw/safe-bin/oc-pytest-run -m pytest \
    src/tests/test_gui/test_wph_pixel_diff_s1a2.py -q

无证据图（干净回归环境）→ skip（不阻断全量回归）。
"""

import hashlib
import os

import pytest
from PySide6.QtGui import QImage

DEFAULT_CAP = (
    "/mnt/e/OpenClaw/Projects/EOR/workspace/EOR20260821-01 GUI-BETA-R1"
    "/WP-H-QML-Hygie/03-da-evidence/S1/baseline-captures"
)
CAP = os.environ.get("WPH_CAPTURE_DIR", DEFAULT_CAP)

PAIRS = (
    ("W09", "Forum 覆盖层", "before-forum-overlay.png", "after-forum-overlay.png"),
    ("W10/W11", "Mortality 事件行", "before-mortality-rows.png", "after-mortality-rows.png"),
    ("W12", "Population 控件", "before-population-control.png", "after-population-control.png"),
)

TOLERANCE = 0.005  # OD-H-02：差异 0 / ≤ 极小容差（含采集时钟区域时标）


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _rgba(img):
    img = img.convertToFormat(QImage.Format_RGBA8888)
    return img.width(), img.height(), img.bytesPerLine(), bytes(img.constBits())


def _pair_diff(a_path, b_path):
    ia, ib = QImage(a_path), QImage(b_path)
    assert not ia.isNull(), a_path
    assert not ib.isNull(), b_path
    wa, ha, bpla, rawa = _rgba(ia)
    wb, hb, bplb, rawb = _rgba(ib)
    assert (wa, ha) == (wb, hb), ((wa, ha), (wb, hb))
    w, h = wa, ha
    diff_px = 0
    max_delta = 0
    sum_delta = 0
    xmin = ymin = 10 ** 9
    xmax = ymax = -1
    for y in range(h):
        ra = rawa[y * bpla:y * bpla + w * 4]
        rb = rawb[y * bplb:y * bplb + w * 4]
        if ra == rb:
            continue
        for x in range(w):
            o = x * 4
            pa, pb = ra[o:o + 4], rb[o:o + 4]
            if pa != pb:
                diff_px += 1
                d = max(abs(pa[i] - pb[i]) for i in range(4))
                if d > max_delta:
                    max_delta = d
                sum_delta += d
                if x < xmin:
                    xmin = x
                if x > xmax:
                    xmax = x
                if y < ymin:
                    ymin = y
                if y > ymax:
                    ymax = y
    bbox = None if diff_px == 0 else (xmin, ymin, xmax, ymax)
    return {
        "w": w, "h": h, "diff_px": diff_px, "total_px": w * h,
        "ratio": diff_px / float(w * h), "max_delta": max_delta,
        "mean_delta_on_diff": (sum_delta / diff_px) if diff_px else 0.0,
        "bbox": bbox,
    }


def test_pixel_diff_report():
    if not os.path.isdir(CAP):
        pytest.skip(f"capture dir absent: {CAP}")
    missing = [n for _, _, b, a in PAIRS for n in (b, a) if not os.path.isfile(os.path.join(CAP, n))]
    if missing:
        pytest.skip(f"before/after images absent: {missing}")

    rows = []
    for key, label, before, after in PAIRS:
        r = _pair_diff(os.path.join(CAP, before), os.path.join(CAP, after))
        rows.append((key, label, before, after, r))

    lines = [
        "# Pixel Diff Report — WP-H / S1 Attempt-2（OD-H-02）",
        "",
        "> before = launch SHA `8bb067a` 未修态捕获；after = 修正后工作树捕获（同 1440×900 / 同 fixture / 同字体）。",
        f"> 判定阈值：差异占比 ≤ {TOLERANCE*100:.2f}%（OD-H-02：差异 0 / ≤ 极小容差）。",
        "",
        "| 位点 | 对象 | 尺寸 | 差异像素 | 差异占比 | 最大通道差 | 平均通道差(差异像素) | 差异包围盒 | 判定 |",
        "|:--|:--|:--|--:|--:|--:|--:|:--|:--|",
    ]
    for key, label, before, after, r in rows:
        verdict = "PASS（0 差异）" if r["diff_px"] == 0 else (
            "PASS（≤极小容差）" if r["ratio"] <= TOLERANCE else "FAIL")
        bbox = "-" if r["bbox"] is None else "x[%d..%d] y[%d..%d]" % (r["bbox"][0], r["bbox"][2], r["bbox"][1], r["bbox"][3])
        lines.append(
            f"| {key} | {label} | {r['w']}×{r['h']} | {r['diff_px']} | "
            f"{r['ratio']*100:.4f}% | {r['max_delta']} | {r['mean_delta_on_diff']:.2f} | {bbox} | {verdict} |")
    lines += ["", "## 图身份（sha256）", "", "| 对象 | before sha256 | after sha256 |", "|:--|:--|:--|"]
    for key, label, before, after in PAIRS:
        lines.append(f"| {label} | `{_sha256(os.path.join(CAP, before))}` | `{_sha256(os.path.join(CAP, after))}` |")
    lines += ["", f"CAPTURE_DIR = `{CAP}`", ""]
    with open(os.path.join(CAP, "pixel-diff-report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    for key, label, before, after, r in rows:
        assert r["ratio"] <= TOLERANCE, (key, label, r)
