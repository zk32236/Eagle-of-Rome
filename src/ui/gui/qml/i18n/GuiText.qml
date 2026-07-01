pragma Singleton
import QtQuick 2.15

QtObject {
    readonly property string shellPhaseTitle: "年度阶段"
    readonly property string refreshStatus: "刷新状态"
    readonly property string phaseHelp: "阶段说明"
    readonly property string phaseLabelPrefix: "阶段："
    readonly property string treasuryPrefix: "国库 "
    readonly property string factionTreasuryPrefix: "派系金库 "
    readonly property string factionResources: "派系资源"
    readonly property string votedOffices: "已投官职"
    readonly property string currentPhase: "当前阶段"
    readonly property string populationFallbackName: "人口"
    readonly property string actionableShort: "可操作"
    readonly property string statusActionable: "状态：可操作真实切片"
    readonly property string statusPlaceholder: "状态：后续任务承接 / 暂不可操作"
    readonly property string completeCurrentPlayer: "完成当前玩家操作"
    readonly property string refreshAuthoritativeState: "刷新权威状态"
    readonly property string phaseHelpRequested: "Phase help requested"
    readonly property string placeholderFallbackTask: "GUI-P0"
    readonly property string placeholderFallbackName: "尚未迁移"
    readonly property string placeholderFallbackDescription: "该阶段将在后续任务中逐步接入 GUI。"
    readonly property string placeholderFallbackReason: "当前页面只显示承接信息，不执行阶段业务。"

    function playerScope(viewerName, viewerId) {
        var label = viewerName || viewerId || "当前"
        return "当前权限：仅显示 " + label + " 派系资源和人物；未迁移阶段不会改变游戏状态。"
    }
}
