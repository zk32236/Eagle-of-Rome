# src/tests/test_gui/test_defer_r3d_governor_absent_notice.py
"""DEFER-R3-D — 公示区「缺席说明」（因无可用候选人未生成总督任命卡的行省）。

覆盖 `DEFERD-AC-01..05`（`02-Frozen-Clause-DEFER-R3-D-2026-10-10.md`）：

* AC-01 公示区 #2 状态面呈现缺席行省行（集合 = 权威 DTO 差集；非空才显）
  - E1 `DATA(PRODUCTION_CHAIN)`：真 producer `session_api.get_senate_view` 造缺席条件；
  - E2 `RENDER_AUTOMATED`（offscreen `SenateStage.qml` + mock store）。
* AC-02 零伪卡 / 零污染（新行只读 `governorAppointments` + `senateProposalOptions`；
  不读 `senatePublicAnnouncement`；不改 `proposal_options`）。
* AC-03 i18n 合规（key 存于 zh-CN + en-US；QML 变更面经 `L10n.t`；无新增散落硬编码；回落不崩）。
* AC-04 非目标零回归（全量回归覆盖；此处守 FC-14 块标记仍在）。
* AC-05 负向（N-2 全有卡不显 / N-4 已任职行省不列 / N-5 DTO 空/缺不崩）。

注：证据分类——E1 = `DATA(PRODUCTION_CHAIN)`（真 producer）；E2 = `RENDER_AUTOMATED`
（offscreen mock，`PARITY-PROVEN`：mock store 镜像生产 Store 契约）。E3（git diff 命中面）
与全量回归由 DA 证据目录另行留痕。
"""
import json
import os
import random
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONUNBUFFERED", "1")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402
from PySide6.QtCore import QObject, Signal, Property, Slot, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent  # noqa: E402

from src.api import senate_api  # noqa: E402
from src.api import session_api  # noqa: E402
from src.ui.gui.localization import DEFAULT_LOCALE, gui_localization  # noqa: E402

QML_DIR = os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
I18N_DIR = os.path.join(PROJECT_ROOT, "data", "i18n")
SENATE_QML = os.path.join(QML_DIR, "stages", "SenateStage.qml")

KEY = "senate.governor.absent_provinces"
NOTICE_OBJECT_NAME = "senateAnnouncementGovernorAbsentNotice"
ZH_EXPECT_PREFIX = "以下行省无可用候选人，未生成总督任命卡："
EN_EXPECT_PREFIX = "No eligible governor candidate for "
EN_EXPECT_SUFFIX = "; no appointment card generated"


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_locale():
    gui_localization.setLocale(DEFAULT_LOCALE)
    yield
    gui_localization.setLocale(DEFAULT_LOCALE)


@pytest.fixture(autouse=True)
def _preserve_global_rng():
    """Save/restore the process-global ``random`` state around each test.

    ``create_gui_prototype_session`` draws from the unseeded global RNG
    (ScenarioLoader ``random.choice``/``random.randint``). Consuming draws here
    would shift the RNG sequence seen by *later* tests in the suite and can flip
    order-dependent expectations elsewhere. Restoring the exact prior state keeps
    this file RNG-neutral for the rest of the run.
    """
    state = random.getstate()
    yield
    random.setstate(state)


def _gov_option(pid, cid=1):
    return {
        "key": f"governor:{pid}",
        "type": "governor",
        "title": f"governor-{pid}",
        "detail": "",
        "params": {"province_id": pid, "candidate_id": cid},
    }


def _pending(pid, name):
    return {
        "province_id": pid,
        "name": name,
        "governor_type": "proconsul",
        "governor_type_name": "proconsul",
        "current_governor": None,
        "candidates": [],
    }


class _MockSenateStore(QObject):
    """Offscreen mock store mirroring the production Store DTO contract
    (I-03 §2.2 INV-2 parity: same Store contract / same binding surface)."""

    senateViewChanged = Signal()

    def __init__(self, options, appointments=None, current_step="proposal"):
        super().__init__()
        self._options = options
        self._appointments = appointments or {}
        self._current_step = current_step

    @Property(list, notify=senateViewChanged)
    def senateProposalOptions(self):
        return self._options

    @Property(dict, notify=senateViewChanged)
    def governorAppointments(self):
        return self._appointments

    @Property(str, notify=senateViewChanged)
    def senateCurrentStep(self):
        return self._current_step

    @Property(list, notify=senateViewChanged)
    def senateSubmittedProposals(self):
        return []

    @Property(list, notify=senateViewChanged)
    def senateTakeoverOptions(self):
        return []

    @Property(bool, notify=senateViewChanged)
    def canTakeoverSenateWar(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canCreateSenateProposal(self):
        return self._current_step == "proposal"

    @Property(bool, notify=senateViewChanged)
    def canSubmitSenateVote(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canSubmitSenateVeto(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canManuallySelectSenateVeto(self):
        return False

    @Property(bool, notify=senateViewChanged)
    def canAdvanceSenate(self):
        return False

    @Property(dict, notify=senateViewChanged)
    def senatePresidingOfficer(self):
        return {}

    @Property(list, notify=senateViewChanged)
    def senateSeatShares(self):
        return []

    @Property(dict, notify=senateViewChanged)
    def senateResult(self):
        return {}

    @Property(dict, notify=senateViewChanged)
    def senatePublicAnnouncement(self):
        return {}

    @Slot("QVariant", result=dict)
    def doSubmitSenateProposals(self, proposals):
        return {"success": True, "message": "ok"}

    @Slot(result=dict)
    def doSubmitSenateVotes(self):
        return {"success": False, "message": "no"}

    @Slot("QVariant", result=dict)
    def doSubmitSenateVetoes(self, proposal_ids):
        return {"success": False, "message": "no"}


def _get_app():
    return QGuiApplication.instance() or QGuiApplication([])


def _load_senate_stage(store):
    app = _get_app()
    engine = QQmlApplicationEngine()
    engine.addImportPath(QML_DIR)

    theme_component = QQmlComponent(engine)
    theme_component.loadUrl(QUrl.fromLocalFile(os.path.join(QML_DIR, "theme", "Theme.qml")))
    assert not theme_component.isError(), theme_component.errorString()
    theme = theme_component.create()
    assert theme is not None

    ctx = engine.rootContext()
    ctx.setContextProperty("theme", theme)
    ctx.setContextProperty("sessionStore", store)
    ctx.setContextProperty("localization", gui_localization)
    ctx.setContextProperty("guiApp", None)

    engine.load(QUrl.fromLocalFile(SENATE_QML))
    app.processEvents()
    roots = engine.rootObjects()
    assert roots, "SenateStage.qml loaded with no root object"
    engine._test_refs = (store, theme)
    return engine, roots[0]


def _notice_text(root):
    obj = root.findChild(QObject, NOTICE_OBJECT_NAME)
    assert obj is not None, f"{NOTICE_OBJECT_NAME} not found in SenateStage.qml tree"
    return obj.property("text")


def _all_texts(root):
    out = []
    for obj in root.findChildren(QObject):
        v = obj.property("text")
        if isinstance(v, str) and v:
            out.append(v)
    return out


def _read_catalog(locale):
    with open(os.path.join(I18N_DIR, f"{locale}.json"), "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# E1 — DATA(PRODUCTION_CHAIN): real producer (get_senate_view) yields absence
# ---------------------------------------------------------------------------

def test_e1_production_chain_absence_condition_from_real_producer():
    from src.core.entities.province import Province
    from src.core.systems.political_system import PoliticalSystem

    result = session_api.create_gui_prototype_session(start_phase="senate")
    assert result["success"], result.get("message")
    state = result["data"]["state"]
    viewer = result["data"]["human_players"][0]

    politics = PoliticalSystem(state)
    eligible = [
        c for c in politics.get_eligible_governor_candidates("proconsul")
        if not politics.is_governor_position_occupied(c.id)
    ]
    n_eligible = len(eligible)

    # 造 (可用候选数 + 2) 个同型 proconsul 空缺行省 → 行省数 > 可用候选数 ⇒ 必然出现无卡行省
    base = 9000
    n_prov = n_eligible + 2
    for i in range(n_prov):
        state.add_province(Province(
            province_id=base + i, name=f"P{base + i}", total_land=1000,
            conquered=True, governor_type="proconsul",
        ))

    view = senate_api.get_senate_view(state, viewer)
    assert view["success"], view.get("message")
    data = view["data"]

    pending = data["governor_appointments"]["pending_provinces"]
    gov_opts = [o for o in data["proposal_options"] if o["type"] == "governor"]

    pending_ids = {p["province_id"] for p in pending}
    covered_ids = {o["params"]["province_id"] for o in gov_opts}
    absent_ids = pending_ids - covered_ids

    # 缺席条件由真 producer 产出（非 mock）：有卡行省 < 待分配行省，差集非空且 >= 2
    assert len(gov_opts) < len(pending), (len(gov_opts), len(pending))
    assert absent_ids, "producer must yield at least one governor-absent province"
    assert len(absent_ids) >= 2, sorted(absent_ids)
    assert not (covered_ids & absent_ids)
    # 尾部新增行省（候选耗尽后，producer 顺序分配）必在缺席集中
    tail_two = {base + n_prov - 2, base + n_prov - 1}
    assert tail_two <= absent_ids, (sorted(absent_ids), sorted(tail_two))


# ---------------------------------------------------------------------------
# E2 — RENDER_AUTOMATED (offscreen): the notice line renders the absent set
# ---------------------------------------------------------------------------

def test_e2_renders_absent_notice_with_uncovered_province():
    """DEFERD-AC-01 / N-3：2 空缺行省、仅 1 卡 → 恰好列出未出卡行省。"""
    store = _MockSenateStore(
        [_gov_option(10)],
        appointments={
            "pending_provinces": [_pending(10, "西西里"), _pending(11, "撒丁")],
            "completed_provinces": [],
        },
    )
    _engine, root = _load_senate_stage(store)

    text = _notice_text(root)
    assert text == ZH_EXPECT_PREFIX + "撒丁", text
    # 已出卡行省（西西里）不得出现在缺席说明中
    assert "西西里" not in text, text


def test_e2_all_covered_provinces_hide_notice():
    """DEFERD-AC-05 / N-2：全部空缺行省均有卡 → 该行不渲染（空串）。"""
    store = _MockSenateStore(
        [_gov_option(10), _gov_option(11, cid=2)],
        appointments={
            "pending_provinces": [_pending(10, "西西里"), _pending(11, "撒丁")],
            "completed_provinces": [],
        },
    )
    _engine, root = _load_senate_stage(store)

    assert _notice_text(root) == ""


def test_e2_completed_province_not_listed():
    """DEFERD-AC-05 / N-4：已任职行省（completed_provinces）不列入缺席说明。"""
    store = _MockSenateStore(
        [_gov_option(10)],
        appointments={
            "pending_provinces": [_pending(10, "西西里")],
            "completed_provinces": [
                {"province_id": 12, "name": "科西嘉", "governor_type": "proconsul",
                 "governor_type_name": "proconsul", "designated_governor": "X",
                 "designated_id": 7},
            ],
        },
    )
    _engine, root = _load_senate_stage(store)

    assert _notice_text(root) == ""
    # 已任职行省名不得出现在公示区任何文本中（缺席说明面）
    assert not any("科西嘉" in t for t in _all_texts(root))


def test_e2_empty_or_missing_dto_does_not_crash():
    """DEFERD-AC-05 / N-5：DTO 缺失/为空 → 空串、不崩。"""
    store = _MockSenateStore([], appointments={})
    _engine, root = _load_senate_stage(store)
    assert _notice_text(root) == ""

    # 缺 pending_provinces 键（异常形状）同样不崩
    store2 = _MockSenateStore([], appointments={"completed_provinces": []})
    _engine2, root2 = _load_senate_stage(store2)
    assert _notice_text(root2) == ""


# ---------------------------------------------------------------------------
# E4 — i18n compliance
# ---------------------------------------------------------------------------

def test_e4_key_present_in_both_catalogs():
    """DEFERD-AC-03：key 存于 zh-CN + en-US 两库（单目录权威）。"""
    zh = _read_catalog("zh-CN")
    en = _read_catalog("en-US")
    assert KEY in zh, KEY
    assert KEY in en, KEY
    assert zh[KEY] == "以下行省无可用候选人，未生成总督任命卡：{provinces}"
    assert en[KEY] == "No eligible governor candidate for {provinces}; no appointment card generated"
    assert "{provinces}" in zh[KEY] and "{provinces}" in en[KEY]


def test_e4_notice_resolves_zh_and_en_reactively():
    """DEFERD-AC-03 / N-7：locale 切换 → 该行就地刷新（zh↔en），状态中性。"""
    store = _MockSenateStore(
        [_gov_option(10)],
        appointments={
            "pending_provinces": [_pending(10, "西西里"), _pending(11, "撒丁")],
            "completed_provinces": [],
        },
    )
    _engine, root = _load_senate_stage(store)

    assert _notice_text(root) == ZH_EXPECT_PREFIX + "撒丁"

    gui_localization.setLocale("en-US")
    _get_app().processEvents()
    assert _notice_text(root) == EN_EXPECT_PREFIX + "撒丁" + EN_EXPECT_SUFFIX

    gui_localization.setLocale(DEFAULT_LOCALE)
    _get_app().processEvents()
    assert _notice_text(root) == ZH_EXPECT_PREFIX + "撒丁"


def test_e4_l10n_missing_key_falls_back_to_literal():
    """DEFERD-AC-03 / N-6：缺键 → 键字面（L10n 确定性回落，不崩）。"""
    assert gui_localization.text("senate.governor.__nonexistent__") == \
        "senate.governor.__nonexistent__"


def test_e4_notice_surface_has_no_hardcoded_copy():
    """DEFERD-AC-03：新函数/新行经 L10n.t；不含散落硬编码（含 \\uXXXX）for copy。"""
    with open(SENATE_QML, "r", encoding="utf-8") as fh:
        src = fh.read()

    # 缺席说明经 i18n key 绑定
    assert 'L10n.t("senate.governor.absent_provinces"' in src
    assert f'objectName: "{NOTICE_OBJECT_NAME}"' in src

    # 仅取「两函数」+「新 Text 节点」两个区域，剔除注释后断言无 raw CJK（值全部走 catalog）
    fn_start = src.index("function governorAbsentProvinces()")
    fn_end = src.index("// ---- WP-D AU-6", fn_start)
    node_start = src.index(f'objectName: "{NOTICE_OBJECT_NAME}"')
    node_end = src.index("// ④ results 内容", node_start)
    regions = [src[fn_start:fn_end], src[node_start:node_end]]
    for region in regions:
        region = re.sub(r"/\*.*?\*/", "", region, flags=re.S)
        region = re.sub(r"//[^\n]*", "", region)
        for ch in region:
            assert not ("\u4e00" <= ch <= "\u9fff"), f"hardcoded CJK in notice surface: {ch!r}"


# ---------------------------------------------------------------------------
# AC-02 — zero fake-card / zero pollution (source-first)
# ---------------------------------------------------------------------------

def test_ac02_notice_reads_only_authoritative_dto():
    """DEFERD-AC-02：新行只读 governorAppointments + senateProposalOptions；
    不读 senatePublicAnnouncement（D-06）；不写 proposal_options。"""
    with open(SENATE_QML, "r", encoding="utf-8") as fh:
        src = fh.read()

    start = src.index("function governorAbsentProvinces()")
    end = src.index("function governorAbsentNoticeText()")
    fn_absent = src[start:end]
    fn_notice_start = end
    fn_notice_end = src.index("// ---- WP-D AU-6", fn_notice_start)
    fn_notice = src[fn_notice_start:fn_notice_end]

    assert "sessionStore.governorAppointments" in fn_absent
    assert "sessionStore.senateProposalOptions" in fn_absent
    # 不读 public_announcement（D-06）
    assert "senatePublicAnnouncement" not in fn_absent
    assert "senatePublicAnnouncement" not in fn_notice
    # 不进 proposal_options（不产生任何 option / 不写 DTO）
    assert "proposal_options" not in fn_absent
    assert "proposal_options" not in fn_notice


def test_ac02_fc14_block_marker_intact():
    """DEFERD-AC-02 / DEFERD-AC-04：FC-14 提案列表只读块仍在（零 diff 守护的源码锚点）。"""
    with open(SENATE_QML, "r", encoding="utf-8") as fh:
        src = fh.read()
    assert 'visible: modelData.type === "governor"' in src
    assert "governorCandidateNameLine" in src


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main([__file__, "-v"])
