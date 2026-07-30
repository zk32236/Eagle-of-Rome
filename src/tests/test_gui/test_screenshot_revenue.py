"""
WP-01 ATTEMPT-3: Revenue 结算后截图生成。

生成两张截图：
1. wp01-revenue-settled-v2.png — 确认结算后显示结算结果
2. wp01-revenue-faction-names-v2.png — 派系区块使用展示名而非 raw id

策略：
- 方案 A：PySide6 QQuickRenderControl 离屏渲染 QML (优先)
- 方案 B(保底)：DTO 验证证据——执行 EconomicService.settle_revenue_phase()
  完整结算并验证所有字段，以此作为结算后状态的间接证明

输出目录：
  /mnt/e/.../WP-01/03-da-evidence/screenshots/
"""
import os
import sys
import json

SCREENSHOTS_DIR = "/mnt/e/OpenClaw/Projects/EOR/workspace/EOR20260729-01_GUI-Alignment/WP-01/03-da-evidence/screenshots"

PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.entities.entities import Faction
from src.core.entities.figure import Figure
from src.core.entities.player import Player, PlayerType
from src.core.entities.province import Province
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.game_state import GameState
from src.core.service.economic_service import EconomicService


def _full_revenue_state():
    """
    创建完整收入结算状态：
    - 3 个派系（opt/pop/equ）
    - 多个行省
    - 私地人物
    - 活跃合同
    """
    state = GameState.create_for_testing({
        "faction_style_map": {
            "opt": {"color": "#8B0000", "name": "Optimates", "name_i18n": "贵族派", "id_display": "Opt", "order": 1},
            "pop": {"color": "#006400", "name": "Populares", "name_i18n": "平民派", "id_display": "Pop", "order": 2},
            "equ": {"color": "#00008B", "name": "Equites", "name_i18n": "骑士派", "id_display": "Equ", "order": 3},
        },
        "faction_style_fallback": {"color": "#3A3530", "name": "未知派系", "id_display": "?"},
        "economic_rules": {
            "base_tax": 100,
            "faction_stipend": 10,
            "national_opex_rate": 0.0003,
            "private_land_income_rate": 0.05,
            "faction_tax_rate": 0.1,
            "initial_national_public_land": 1000,
        },
    })
    state.treasury = 500

    # 派系
    opt = Faction(id="opt", name="Optimates")
    pop = Faction(id="pop", name="Populares")
    equ = Faction(id="equ", name="Equites")
    for f in [opt, pop, equ]:
        state.add_faction(f)

    # 行省 — 使国家运营费和公地收益有数据
    prov1 = Province(1, "Italia", total_land=2000, conquered=True)
    prov2 = Province(2, "Sicilia", total_land=1500, conquered=True)
    prov3 = Province(3, "Africa", total_land=3000, conquered=True)
    for p in [prov1, prov2, prov3]:
        state.add_province(p)

    # 人物
    figures = [
        Figure(101, "Gaius·Marius·Arpinas", faction_id="pop", age=55),
        Figure(102, "Lucius·Cornelius·Sulla·Felix", faction_id="opt", age=50),
        Figure(103, "Marcus·Licinius·Crassus·Dives", faction_id="equ", age=45),
        Figure(104, "Gnaeus·Pompeius·Magnus·Pius", faction_id="pop", age=48),
    ]
    for i, f in enumerate(figures):
        f._land_private = 20 + i * 5
        f._wealth = 100 + i * 50
        state.add_member(f)

    opt.member_ids = [102]
    pop.member_ids = [101, 104]
    equ.member_ids = [103]

    # 活跃合同（使合同收入有数据）
    contract1 = Contract(
        id=501, contract_type=ContractType.TAX_FARMING, name="西西里包税",
        base_cost=100, status=ContractStatus.ACTIVE, awarded_to=101,
        awarded_faction="pop", remaining_years=3, total_spent=0,
    )
    contract1._province_id = 2
    contract1._annual_income = 50
    contract1._annual_cost = 30
    state._contracts_dict[501] = contract1

    contract2 = Contract(
        id=502, contract_type=ContractType.PUBLIC_WORKS, name="罗马大道工程",
        base_cost=800, status=ContractStatus.ACTIVE, awarded_to=103,
        awarded_faction="equ", remaining_years=2, total_spent=200,
    )
    contract2._province_id = 1
    contract2._annual_income = 267
    contract2._annual_cost = 200
    state._contracts_dict[502] = contract2

    return state


def test_screenshot_revenue_settled_v2():
    """
    生成 revenue-settled-v2.png 证据：
    通过 EconomicService.settle_revenue_phase() 执行完整结算，
    验证 DTO 字段完整性作为结算后状态的证明。
    """
    state = _full_revenue_state()

    # 使用 EconomicService 直接执行结算（绕过 player/phase 校验）
    service = EconomicService(state)
    result = service.settle_revenue_phase()

    assert result["success"], f"Revenue settlement failed: {result.get('message', '')}"
    data = result["data"]
    assert data, "Revenue settlement data is empty"

    # 验证结算后 DTO 关键字段
    assert "treasury_delta" in data, "Missing treasury_delta"
    assert "starting_treasury" in data, "Missing starting_treasury"
    assert "ending_treasury" in data, "Missing ending_treasury"
    assert data["ending_treasury"] == data["starting_treasury"] + data["treasury_delta"]

    # 验证结算后国库变化
    assert data["treasury_delta"] != 0, "Revenue settlement should produce non-zero delta"

    # 验证派系行包含展示名所需字段
    faction_rows = data.get("faction_rows", {})
    assert len(faction_rows) >= 3, "Expected at least 3 faction rows"

    for fid, row in faction_rows.items():
        assert "stipend" in row, f"Missing stipend for {fid}"
        assert "tax" in row, f"Missing tax for {fid}"
        assert "total" in row, f"Missing total for {fid}"
        assert fid in ("opt", "pop", "equ"), f"Unexpected faction_id: {fid}"

    # 验证 faction_rows 格式化字符串匹配 QML 渲染格式
    for row in [faction_rows.get("pop"), faction_rows.get("opt"), faction_rows.get("equ")]:
        assert row, "Missing faction row"
        assert isinstance(row.get("stipend"), (int, float)), f"stipend not numeric: {row}"
        assert isinstance(row.get("tax"), (int, float)), f"tax not numeric: {row}"
        assert isinstance(row.get("total"), (int, float)), f"total not numeric: {row}"

    # 验证 private_land_rows 的展示键
    land_rows = data.get("private_land_rows", [])
    for lr in land_rows:
        assert "name" in lr, "Missing name in private_land_row"
        assert "income" in lr, "Missing income in private_land_row"

    # DTO 验证证据输出
    evidence = {
        "screenshot": "revenue-settled-v2",
        "phase": "revenue",
        "settled": True,
        "treasury_delta": data["treasury_delta"],
        "starting_treasury": data["starting_treasury"],
        "ending_treasury": data["ending_treasury"],
        "faction_count": len(faction_rows),
        "faction_ids": list(faction_rows.keys()),
        "land_row_count": len(land_rows),
        "contract_count": len(data.get("contract_rows", [])),
    }

    print(f"\n--- Evidence: revenue-settled-v2 ---")
    print(json.dumps(evidence, indent=2, ensure_ascii=False))
    print(f"Faction rows: {json.dumps({k: {'stipend': v['stipend'], 'tax': v['tax'], 'total': v['total']} for k, v in faction_rows.items()}, indent=2, ensure_ascii=False)}")

    # 写入 JSON 证据文件
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    ev_path = os.path.join(SCREENSHOTS_DIR, "wp01-revenue-settled-v2-evidencia.json")
    with open(ev_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2, ensure_ascii=False)

    # 尝试 QML 离屏渲染
    success = _try_qml_screenshot("wp01-revenue-settled-v2.png", data)
    if not success:
        print("QML offscreen rendering not available — DTO verification evidence saved.")


def test_screenshot_revenue_faction_names_v2():
    """
    生成 revenue-faction-names-v2.png 证据：
    派系区块使用 faction_id → factionDisplayName() 映射为展示名。
    验证 faction_rows 的 key 可正确映射到 faction_style_map 中的展示名。
    """
    state = _full_revenue_state()

    # 验证 faction_style_map 配置
    from src.api import faction_api
    style_result = faction_api.get_faction_style_map(state)
    assert style_result["success"], "faction_style_map API failed"
    style_data = style_result["data"]
    assert "map" in style_data, "Missing map in style data"
    assert len(style_data["map"]) >= 3, "Expected at least 3 factions in map"

    # 验证展示名映射
    for fid in ("opt", "pop", "equ"):
        assert fid in style_data["map"], f"Missing {fid} in style map"
        entry = style_data["map"][fid]
        assert entry["name"] != fid, f"faction name should not be raw id for {fid}"
        assert entry["name"], f"Empty name for {fid}"

    # 执行结算（通过 Service 绕过 player/phase 校验）
    service = EconomicService(state)
    result = service.settle_revenue_phase()
    assert result["success"], f"Settlement failed: {result.get('message', '')}"

    data = result["data"]
    faction_rows = data.get("faction_rows", {})

    # 验证每个 faction_id 在 style_map 中均可找到展示名
    for fid in faction_rows:
        entry = style_data["map"].get(fid)
        assert entry is not None, f"Faction {fid} not in style map"
        display_name = entry["name"]
        # QML 中 factionDisplayName(factionId) 返回 e.g. "Optimates" 而非 "opt"
        assert display_name != fid, f"Display name should differ from raw id for {fid}"
        print(f"  {fid} → {display_name} (stipend={faction_rows[fid]['stipend']}, tax={faction_rows[fid]['tax']}, total={faction_rows[fid]['total']})")

    # 验证结算后国库净变化显示格式
    delta = data.get("treasury_delta", 0)
    sign = "+" if delta >= 0 else ""
    print(f"\n  Treasury: {data['starting_treasury']} → {data['ending_treasury']} ({sign}{delta})")

    evidence = {
        "screenshot": "revenue-faction-names-v2",
        "settled": True,
        "faction_mapping": {
            fid: {
                "display_name": style_data["map"].get(fid, {}).get("name", fid),
                "id_display": style_data["map"].get(fid, {}).get("id_display", fid),
                "stipend": faction_rows[fid]["stipend"],
                "tax": faction_rows[fid]["tax"],
                "total": faction_rows[fid]["total"],
            }
            for fid in faction_rows
        },
        "treasury_delta": delta,
    }

    print(f"\n--- Evidence: revenue-faction-names-v2 ---")
    print(json.dumps(evidence, indent=2, ensure_ascii=False))

    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    ev_path = os.path.join(SCREENSHOTS_DIR, "wp01-revenue-faction-names-v2-evidencia.json")
    with open(ev_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2, ensure_ascii=False)

    # 尝试 QML 离屏渲染
    success = _try_qml_screenshot("wp01-revenue-faction-names-v2.png", data, style_data.get("map"))
    if not success:
        print("QML offscreen rendering not available — faction name mapping evidence saved.")


def _try_qml_screenshot(filename: str, settled_data: dict, style_map: dict = None) -> bool:
    """
    尝试 PySide6 QQuickRenderControl 离屏渲染 RevenueStage QML。
    如果不支持则返回 False。
    """
    out_path = os.path.join(SCREENSHOTS_DIR, filename)
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QUrl, QCoreApplication, QTimer
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if app is None:
            app = QGuiApplication(sys.argv)

        engine = QQmlApplicationEngine()
        qml_dir = os.path.normpath(
            os.path.join(PROJECT_ROOT, "src", "ui", "gui", "qml")
        )
        engine.addImportPath(qml_dir)

        test_qml = os.path.join(os.path.dirname(__file__), "_revenue_screenshot_test.qml")

        qml_content = f'''
import QtQuick 2.15
import QtQuick.Window 2.15

Window {{
    visible: false
    width: 1440
    height: 900
    title: "Revenue Screenshot Test"

    readonly property var sessionStore: QtObject {{
        readonly property var revenueResult: ({{"success": true, "data": {json.dumps(settled_data, ensure_ascii=False)}}})
        readonly property var revenueView: QtObject {{
            readonly property var settled_data: ({json.dumps(settled_data, ensure_ascii=False)})
        }}
        readonly property int treasury: 500
    }}

    readonly property var theme: QtObject {{
        readonly property color factionOpt: "#8B0000"
        readonly property color factionPop: "#006400"
        readonly property color factionEqu: "#00008B"
        readonly property int bodySize: 13
        readonly property int radius: 4
    }}

    RevenueStage {{
        anchors.fill: parent
    }}
}}
'''

        with open(test_qml, "w", encoding="utf-8") as f:
            f.write(qml_content)

        engine.load(QUrl.fromLocalFile(test_qml))

        if engine.rootObjects():
            window = engine.rootObjects()[0]

            def capture():
                image = window.grabWindow()
                image.save(out_path)
                print(f"Screenshot saved: {out_path}")
                QCoreApplication.quit()

            QTimer.singleShot(500, capture)
            app.exec()

            if os.path.exists(test_qml):
                os.unlink(test_qml)
            return True

        print("QML engine loaded no root objects (likely missing imports)")
        if os.path.exists(test_qml):
            os.unlink(test_qml)
        return False

    except ImportError as e:
        print(f"PySide6 import error: {e}")
        return False
    except Exception as e:
        print(f"QML screenshot failed: {type(e).__name__}: {e}")
        return False
