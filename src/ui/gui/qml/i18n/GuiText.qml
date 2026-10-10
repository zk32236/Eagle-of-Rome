pragma Singleton
import QtQuick 2.15
import "." as I18n

/*!
 * \brief GuiText — GUI copy binding layer (GUI-I18N Foundation, slice S2).
 *
 * Player-visible copy is bound to the single catalog authority
 * (``data/i18n/*.json`` via ``L10n.t``); see FC-GI18N-02/05. Non-player-visible
 * constants (brand / defaults / icons / separator) are kept literal — they are
 * not translation debt (catalog-key-map §C.3).
 */
QtObject {
    // -- Non-player-visible constants (kept literal; not translation debt) ----
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
    readonly property string phaseHelpRequested: "Phase help requested"

    // -- Player-visible copy (bound to the catalog) --------------------------
    readonly property string shellPhaseTitle: I18n.L10n.t("shell.phase.title")
    readonly property string refreshStatus: I18n.L10n.t("shell.refresh.status")
    readonly property string phaseHelp: I18n.L10n.t("shell.phase.help")
    readonly property string phaseLabelPrefix: I18n.L10n.t("shell.phase.label_prefix")
    readonly property string treasuryPrefix: I18n.L10n.t("shell.treasury.prefix")
    readonly property string factionTreasuryPrefix: I18n.L10n.t("shell.faction_treasury.prefix")
    readonly property string factionResources: I18n.L10n.t("shell.faction_resources")
    readonly property string factionTreasuryLabel: I18n.L10n.t("shell.faction_treasury.label")
    readonly property string totalInfluenceLabel: I18n.L10n.t("shell.total_influence.label")
    readonly property string factionMemberLabel: I18n.L10n.t("shell.faction_member.label")
    readonly property string peopleUnit: I18n.L10n.t("unit.people")
    readonly property string votedOffices: I18n.L10n.t("shell.voted_offices")
    readonly property string currentPhase: I18n.L10n.t("shell.current_phase")
    readonly property string authoritativePhase: I18n.L10n.t("shell.authoritative_phase")
    readonly property string selectedPhase: I18n.L10n.t("shell.selected_phase")
    readonly property string playerPermission: I18n.L10n.t("shell.player_permission")
    readonly property string queryResultTitle: I18n.L10n.t("query.result.title")
    readonly property string queryResultEmpty: I18n.L10n.t("query.result.empty")
    readonly property string closeQueryResult: I18n.L10n.t("query.result.close")
    readonly property string feedbackLogTitle: I18n.L10n.t("feedback.panel.title")
    readonly property string clearFeedback: I18n.L10n.t("feedback.panel.clear")
    readonly property string guiSessionStarted: I18n.L10n.t("feedback.session.started")
    readonly property string currentPhaseLogPrefix: I18n.L10n.t("feedback.current_phase.prefix")
    readonly property string stageAnnouncementTitle: I18n.L10n.t("stage.announcement.title")
    readonly property string stageAnnouncementReadonly: I18n.L10n.t("stage.mode.readonly")
    readonly property string stageAnnouncementPlaceholder: I18n.L10n.t("stage.mode.placeholder")
    readonly property string stageAnnouncementInteractive: I18n.L10n.t("stage.mode.interactive")
    readonly property string populationFallbackName: I18n.L10n.t("phase.population.name")
    readonly property string actionableShort: I18n.L10n.t("stage.short.actionable")
    readonly property string connectedShort: I18n.L10n.t("stage.short.connected")
    readonly property string statusActionable: I18n.L10n.t("stage.status.actionable")
    readonly property string statusReady: I18n.L10n.t("stage.status.ready")
    readonly property string statusPlaceholder: I18n.L10n.t("stage.status.placeholder")
    readonly property string completeCurrentPlayer: I18n.L10n.t("shell.complete_current_player")
    readonly property string refreshAuthoritativeState: I18n.L10n.t("shell.refresh.authoritative_state")
    readonly property string mortalityTitle: I18n.L10n.t("mortality.title")
    readonly property string mortalityIntro: I18n.L10n.t("mortality.intro")
    readonly property string mortalityReady: I18n.L10n.t("mortality.ready")
    readonly property string mortalityResolved: I18n.L10n.t("mortality.resolved")
    readonly property string executeMortality: I18n.L10n.t("mortality.action.execute")
    readonly property string advanceMortality: I18n.L10n.t("mortality.advance")
    readonly property string mortalityNoResult: I18n.L10n.t("mortality.no_result")
    readonly property string mortalityEventsTitle: I18n.L10n.t("mortality.events.title")
    readonly property string mortalityContinueHint: I18n.L10n.t("mortality.continue_hint")
    readonly property string senateTitle: I18n.L10n.t("senate.title")
    readonly property string senateReadonlyBadge: I18n.L10n.t("senate.badge.readonly")
    readonly property string senateReadonlyIntro: I18n.L10n.t("senate.intro.readonly")
    readonly property string senatePresidingOfficer: I18n.L10n.t("senate.label.presiding_officer")
    readonly property string senateFactionLeaders: I18n.L10n.t("senate.label.faction_leaders")
    readonly property string senateActiveWars: I18n.L10n.t("senate.label.active_wars")
    readonly property string senateWarThreats: I18n.L10n.t("senate.label.war_threats")
    readonly property string senatePendingPeace: I18n.L10n.t("senate.label.pending_peace")
    readonly property string senateGovernorVacancies: I18n.L10n.t("senate.label.governor_vacancies")
    readonly property string senatePendingContracts: I18n.L10n.t("senate.label.pending_contracts")
    readonly property string senateNoItems: I18n.L10n.t("senate.no_items")
    readonly property string senateActionsDisabled: I18n.L10n.t("senate.actions_disabled")
    readonly property string senateFutureTaskHint: I18n.L10n.t("senate.future_task_hint")
    readonly property string senateInfluenceLabel: I18n.L10n.t("senate.label.influence")
    readonly property string senateThreatLabel: I18n.L10n.t("senate.label.threat")
    readonly property string senateNavalRequiredLabel: I18n.L10n.t("senate.label.naval_required")
    readonly property string senateIndemnityLabel: I18n.L10n.t("senate.label.indemnity")
    readonly property string senateYearUnit: I18n.L10n.t("unit.year")
    readonly property string senateCostLabel: I18n.L10n.t("senate.label.cost")
    readonly property string senateExpectedProfitLabel: I18n.L10n.t("senate.label.expected_profit")
    readonly property string senateLeaderCountUnit: I18n.L10n.t("unit.leader_count")
    readonly property string placeholderFallbackTask: I18n.L10n.t("stage.placeholder.task")
    readonly property string placeholderFallbackName: I18n.L10n.t("stage.placeholder.name")
    readonly property string placeholderFallbackDescription: I18n.L10n.t("stage.placeholder.description")
    readonly property string placeholderFallbackReason: I18n.L10n.t("stage.placeholder.reason")
    readonly property string bottomQueryBarTitle: I18n.L10n.t("query.bar.title")
    readonly property string queryStatusConnected: I18n.L10n.t("stage.short.connected")
    readonly property string queryStatusReadonly: I18n.L10n.t("stage.mode.readonly")
    readonly property string queryStatusPlaceholder: I18n.L10n.t("stage.mode.placeholder")
    readonly property string queryGameStatus: I18n.L10n.t("query.game_status.title")
    readonly property string queryFactionInfo: I18n.L10n.t("query.faction_info.title")
    readonly property string queryWarList: I18n.L10n.t("query.war_list.title")
    readonly property string queryLegionStatus: I18n.L10n.t("query.legion_status.title")
    readonly property string queryFigureSearch: I18n.L10n.t("query.figure_search.title")
    readonly property string queryFactionTreasury: I18n.L10n.t("query.faction_treasury.title")
    readonly property string queryPublicLand: I18n.L10n.t("query.public_land.title")
    readonly property string queryPrivateLand: I18n.L10n.t("query.private_land.title")
    readonly property string queryContractStatus: I18n.L10n.t("query.contract_status.title")
    readonly property string queryProvinceInfo: I18n.L10n.t("query.province_info.title")
    readonly property string queryFleetStatus: I18n.L10n.t("query.fleet_status.title")
    readonly property string queryHelp: I18n.L10n.t("query.help.title")

    function turnText(turnNumber) {
        return I18n.L10n.t("topStatusBar.turn", { turn: turnNumber || 1 })
    }

    function currentPlayerText(playerId, factionName, factionId) {
        return (playerId || defaultPlayerId) + " / " + (factionName || factionId || defaultFactionName)
    }

    function countPeople(count) {
        return I18n.L10n.t("unit.people.count", { count: count || 0 })
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
        return I18n.L10n.t("shell.player_scope", { name: label })
    }

    function mortalityImpactText(impact) {
        if (!impact) return ""
        if (impact.type === "figure_death") {
            return I18n.L10n.t("mortality.impact.death",
                               { name: impact.figure_name || impact.figure_id || "未知人物" })
        }
        if (impact.type === "active_event") {
            return I18n.L10n.t("mortality.impact.event", { key: impact.key || "" })
        }
        if (impact.type === "province_grievance") {
            return I18n.L10n.t("mortality.impact.grievance", {
                name: impact.province_name || impact.province_id || "",
                old: impact.old,
                new: impact.new
            })
        }
        if (impact.type === "war_threat") {
            return I18n.L10n.t("mortality.impact.war_threat", {
                name: impact.war_name || impact.war_id || "",
                old: impact.old,
                new: impact.new
            })
        }
        if (impact.type === "hero_spawn") {
            return impact.subtype === "historical"
                ? I18n.L10n.t("mortality.impact.hero.historical", { name: impact.name })
                : I18n.L10n.t("mortality.impact.hero.random")
        }
        if (impact.type === "disaster") {
            return I18n.L10n.t("mortality.impact.disaster", {
                name: impact.province_name || impact.province_id || "",
                pct: Math.round((impact.loss_ratio || 0) * 100)
            })
        }
        return impact.type || ""
    }

    function senateCountLine(view) {
        if (!view || !view.summary) return ""
        return I18n.L10n.t("senate.count.line", {
            war: view.summary.active_foreign_war_count || 0,
            threat: view.summary.war_threat_count || 0,
            draft: view.summary.pending_peace_treaty_count || 0,
            contract: view.summary.pending_contract_count || 0
        })
    }

    function senateInfluenceDetail(factionName, influence) {
        return I18n.L10n.t("senate.detail.influence", { name: factionName, influence: influence || 0 })
    }

    function senateThreatDetail(threatLevel, navalRequired) {
        return navalRequired
            ? I18n.L10n.t("senate.detail.threat.naval", { level: threatLevel })
            : I18n.L10n.t("senate.detail.threat", { level: threatLevel })
    }

    function senatePeaceDetail(indemnity, duration) {
        return I18n.L10n.t("senate.detail.peace", { indemnity: indemnity, duration: duration || 0 })
    }

    function senateContractDetail(baseCost, expectedProfit) {
        return I18n.L10n.t("senate.detail.contract", { cost: baseCost, profit: expectedProfit || 0 })
    }

    function senateLeaderCount(count) {
        return I18n.L10n.t("senate.leader.count", { count: count })
    }
}
