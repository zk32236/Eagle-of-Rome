pragma Singleton
import QtQuick 2.15

QtObject {
    readonly property string appMark: "SPQR"
    readonly property string appName: "Eagle of Rome"
    readonly property string defaultYearDisplay: "282 BC"
    readonly property string defaultPlayerAvatar: "OP"
    readonly property string defaultPlayerId: "player"
    readonly property string defaultFactionName: "Optimates"
    readonly property string calendarIcon: "📅"
    readonly property string turnIcon: "🔄"
    readonly property string treasuryIcon: "💰"
    readonly property string votedIcon: "V"
    readonly property string keyValueSeparator: ": "
    readonly property string shellPhaseTitle: "年度阶段"
    readonly property string refreshStatus: "刷新状态"
    readonly property string phaseHelp: "阶段说明"
    readonly property string phaseLabelPrefix: "阶段："
    readonly property string treasuryPrefix: "国库 "
    readonly property string factionTreasuryPrefix: "派系金库 "
    readonly property string factionResources: "派系资源"
    readonly property string factionTreasuryLabel: "派系金库"
    readonly property string totalInfluenceLabel: "总影响力"
    readonly property string factionMemberLabel: "派系人物"
    readonly property string peopleUnit: "人"
    readonly property string votedOffices: "已投官职"
    readonly property string currentPhase: "当前阶段"
    readonly property string authoritativePhase: "权威阶段"
    readonly property string selectedPhase: "选中阶段"
    readonly property string playerPermission: "玩家权限"
    readonly property string queryResultTitle: "查询结果"
    readonly property string queryResultEmpty: "点击底部查询按钮查看只读摘要。"
    readonly property string closeQueryResult: "关闭"
    readonly property string feedbackLogTitle: "结构化反馈与最近事件"
    readonly property string clearFeedback: "清空"
    readonly property string guiSessionStarted: "GUI 会话已启动"
    readonly property string currentPhaseLogPrefix: "当前阶段："
    readonly property string stageAnnouncementTitle: "阶段公告"
    readonly property string stageAnnouncementReadonly: "只读"
    readonly property string stageAnnouncementPlaceholder: "占位"
    readonly property string stageAnnouncementInteractive: "可操作"
    readonly property string populationFallbackName: "人口"
    readonly property string actionableShort: "可操作"
    readonly property string connectedShort: "已接入"
    readonly property string statusActionable: "状态：可操作真实切片"
    readonly property string statusReady: "状态：已接入 / 等待正确阶段或玩家"
    readonly property string statusPlaceholder: "状态：后续任务承接 / 暂不可操作"
    readonly property string completeCurrentPlayer: "完成当前玩家操作"
    readonly property string refreshAuthoritativeState: "刷新权威状态"
    readonly property string mortalityTitle: "天命阶段"
    readonly property string mortalityIntro: "抽取年度天命事件，并将结果写入共和国权威状态。"
    readonly property string mortalityReady: "准备执行天命"
    readonly property string mortalityResolved: "天命已执行"
    readonly property string executeMortality: "执行天命"
    readonly property string advanceMortality: "进入收入阶段"
    readonly property string mortalityNoResult: "尚未执行天命。"
    readonly property string mortalityEventsTitle: "天命结果"
    readonly property string mortalityContinueHint: "天命完成后将进入真实下一阶段：收入。"
    readonly property string mortalityStepExecute: "执行天命"
    readonly property string mortalityStepView: "查看事件结果"
    readonly property string mortalityHintInitial: "点击下方按钮，触发一个随机事件。"
    readonly property string mortalityBadge: "1 / 7"
    readonly property string mortalityExecuteBtn: "执行天命"
    readonly property string mortalityExecutedLabel: "已执行"
    readonly property string mortalityAdvanceBtn: "进入收入"
    readonly property string senateTitle: "元老院阶段"
    readonly property string senateReadonlyBadge: "只读状态"
    readonly property string senateReadonlyIntro: "展示元老院公开状态；提案、投票与结算由后续任务接入。"
    readonly property string senatePresidingOfficer: "主持官"
    readonly property string senateFactionLeaders: "派系领袖"
    readonly property string senateActiveWars: "进行中的对外战争"
    readonly property string senateWarThreats: "战争威胁"
    readonly property string senatePendingPeace: "待审停战草案"
    readonly property string senateGovernorVacancies: "总督空缺"
    readonly property string senatePendingContracts: "待处理合同"
    readonly property string senateNoItems: "暂无记录"
    readonly property string senateActionsDisabled: "政治行动暂未开放"
    readonly property string senateFutureTaskHint: "提案创建、表决、否决与结算将在 GUI-P0-02C 后续子任务承接。"
    readonly property string senateInfluenceLabel: "影响力"
    readonly property string senateThreatLabel: "威胁"
    readonly property string senateNavalRequiredLabel: "需要海战"
    readonly property string senateIndemnityLabel: "赔款"
    readonly property string senateYearUnit: "年"
    readonly property string senateCostLabel: "成本"
    readonly property string senateExpectedProfitLabel: "预期收益"
    readonly property string senateLeaderCountUnit: "位"
    readonly property string phaseHelpRequested: "Phase help requested"
    readonly property string placeholderFallbackTask: "GUI-P0"
    readonly property string placeholderFallbackName: "尚未迁移"
    readonly property string placeholderFallbackDescription: "该阶段将在后续任务中逐步接入 GUI。"
    readonly property string placeholderFallbackReason: "当前页面只显示承接信息，不执行阶段业务。"
    readonly property string bottomQueryBarTitle: "全局查询"
    readonly property string queryStatusConnected: "已接入"
    readonly property string queryStatusReadonly: "只读"
    readonly property string queryStatusPlaceholder: "占位"
    readonly property string topBarPublicLand: "公地"
    readonly property string topBarLegionUnit: "个"
    readonly property string topBarFleetUnit: "个"
    readonly property string topBarProvinceUnit: "个"
    readonly property string topBarPersonUnit: "人"
    readonly property string topBarPhaseSuffix: "阶段"
    readonly property string senateDeadlockHint: "全否决后将进入死锁逃生模式"
    readonly property string senateCompletionTitle: "元老院阶段已完成"
    readonly property string senateWaitingProposal: "等待提案完成"
    readonly property string senateWaitingVote: "等待表决开始"
    readonly property string senateWaitingVeto: "等待否决开始"
    readonly property string queryGameStatus: "游戏状态"
    readonly property string queryFactionInfo: "派系信息"
    readonly property string queryWarList: "战争列表"
    readonly property string queryLegionStatus: "军团状态"
    readonly property string queryFigureSearch: "人物查询"
    readonly property string queryFactionTreasury: "派系金库"
    readonly property string queryPublicLand: "公地信息"
    readonly property string queryPrivateLand: "私地信息"
    readonly property string queryContractStatus: "合同状态"
    readonly property string queryProvinceInfo: "行省信息"
    readonly property string queryFleetStatus: "舰队状态"
    readonly property string queryHelp: "帮助"

    function get(key) {
        if (key === "query.game_status") return queryGameStatus
        if (key === "query.faction_info") return queryFactionInfo
        if (key === "query.war_list") return queryWarList
        if (key === "query.legion_status") return queryLegionStatus
        if (key === "query.figure_search") return queryFigureSearch
        if (key === "query.faction_treasury") return queryFactionTreasury
        if (key === "query.public_land") return queryPublicLand
        if (key === "query.private_land") return queryPrivateLand
        if (key === "query.contract_status") return queryContractStatus
        if (key === "query.province_info") return queryProvinceInfo
        if (key === "query.fleet_status") return queryFleetStatus
        if (key === "query.help") return queryHelp
        return key
    }

    function turnText(turnNumber) {
        return "回合 " + (turnNumber || 1)
    }

    function currentPlayerText(playerId, factionName, factionId) {
        return (playerId || defaultPlayerId) + " / " + (factionName || factionId || defaultFactionName)
    }

    function countPeople(count) {
        return (count || 0) + " " + peopleUnit
    }

    function stageModeText(summary) {
        if (!summary) return stageAnnouncementPlaceholder
        if (summary.actionable) return stageAnnouncementInteractive
        if (summary.interaction_mode === "readonly") return stageAnnouncementReadonly
        return stageAnnouncementPlaceholder
    }

    function queryStatusText(status) {
        if (status === "connected") return queryStatusConnected
        if (status === "readonly") return queryStatusReadonly
        return queryStatusPlaceholder
    }

    function playerScope(viewerName, viewerId) {
        var label = viewerName || viewerId || "当前"
        return "当前权限：仅显示 " + label + " 派系资源和人物；未迁移阶段不会改变游戏状态。"
    }

    function mortalityImpactText(impact) {
        if (!impact) return ""
        if (impact.type === "figure_death") {
            return "死亡：" + (impact.figure_name || impact.figure_id || "未知人物")
        }
        if (impact.type === "active_event") {
            return "本回合事件：" + (impact.key || "")
        }
        if (impact.type === "province_grievance") {
            return "民怨：" + (impact.province_name || impact.province_id || "") + " " + impact.old + "→" + impact.new
        }
        if (impact.type === "war_threat") {
            return "战争威胁：" + (impact.war_name || impact.war_id || "") + " " + impact.old + "→" + impact.new
        }
        if (impact.type === "hero_spawn") {
            return impact.subtype === "historical" ? "英雄登场：" + impact.name : "英雄登场：随机猛人"
        }
        if (impact.type === "disaster") {
            return "灾害：" + (impact.province_name || impact.province_id || "") + " 损失 " + Math.round((impact.loss_ratio || 0) * 100) + "%"
        }
        return impact.type || ""
    }

    function senateCountLine(view) {
        if (!view || !view.summary) return ""
        return "战争 " + (view.summary.active_foreign_war_count || 0)
            + " / 威胁 " + (view.summary.war_threat_count || 0)
            + " / 草案 " + (view.summary.pending_peace_treaty_count || 0)
            + " / 合同 " + (view.summary.pending_contract_count || 0)
    }

    function senateInfluenceDetail(factionName, influence) {
        return factionName + " / " + senateInfluenceLabel + " " + (influence || 0)
    }

    function senateThreatDetail(threatLevel, navalRequired) {
        return senateThreatLabel + " " + threatLevel + (navalRequired ? " / " + senateNavalRequiredLabel : "")
    }

    function senatePeaceDetail(indemnity, duration) {
        return senateIndemnityLabel + " " + indemnity + " T / " + (duration || 0) + " " + senateYearUnit
    }

    function senateContractDetail(baseCost, expectedProfit) {
        return senateCostLabel + " " + baseCost + " T / " + senateExpectedProfitLabel + " " + (expectedProfit || 0) + " T"
    }

    function senateLeaderCount(count) {
        return count + " " + senateLeaderCountUnit
    }
}
