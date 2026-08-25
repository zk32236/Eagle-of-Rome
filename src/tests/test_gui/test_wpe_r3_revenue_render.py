"""WP-E-R3 Revenue canonical ledger render contract checks."""

from pathlib import Path


QML_PATH = Path(__file__).parents[2] / "ui" / "gui" / "qml" / "stages" / "RevenueStage.qml"


def test_revenue_stage_renders_only_canonical_treasury_rows():
    source = QML_PATH.read_text(encoding="utf-8-sig")

    assert 'objectName: "revenueCanonicalLedger"' in source
    assert "root._accounting.treasury_ledger_rows" in source
    assert "modelData.signed_amount" in source
    assert "共和国国库（本次 Revenue 结算）" in source
    assert "residual" not in source.lower()
    assert "平账" not in source


def test_revenue_stage_labels_non_treasury_bases_and_reconcile_failure():
    source = QML_PATH.read_text(encoding="utf-8-sig")

    assert "人物财富（不计入国库净变化）" in source
    assert "派系金库（不计入国库净变化；国库拨款已在国库支出列示）" in source
    assert "合同质保事件（非现金）" in source
    assert 'objectName: "revenueReconciliationError"' in source
    assert "结算展示不一致" in source
    assert 'objectName: "revenueCanonicalTotals"' in source
    assert "displayed_net_total" in source
