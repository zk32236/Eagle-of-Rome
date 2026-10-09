import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15

import "../components"
import "../i18n"

Rectangle {
    id: root
    color: "transparent"

    property var selectedProposalKeys: []
    property var selectedVetoProposalIds: []
    // WP-J Group C G7 Test R7 Delta（delta v2.3 / FC-C41）：②「2 元老院表决」**专属**选择集
    // （仿 ③ selectedVetoProposalIds/hasSelectedVeto/setVetoSelected；**禁**与 ①/③ 串味）。
    // 勾选 = 同意；未勾选 = 否决（**默认未勾选**）。**随会期重置**（OBS-R7-3，见 syncSenateVoteSelection）。
    property var selectedSenateVoteIds: []
    property string _senateVoteSelectionKey: ""
    property bool proposalStepDone: sessionStore.senateCurrentStep !== "proposal"
    // R5（SA §5.1，DA-5）：统一 War Card 草稿暂存（仅本地输入；可编辑真值由 Core 在 Submit 时
    // 重验，QML 不得本地推导分类/N 上限/部署门 —— A-I18/D-SC02/D-SC15）
    property var warCardDrafts: ({})
    // R7（SA §B.7，DA-R7 B3）：逐卡 ack（仅展示层）——编辑受影响卡 → 仅清该卡红框；
    // **始终不声明 package 有效**（权威有效性仅由下一次 Submit 决定）。war_id(string) → true。
    property var errorAckWars: ({})

    FactionStyle { id: factionStyle }

    function itemText(item, fallbackName) {
        if (!item) return fallbackName || ""
        return item.name || item.leader_name || item.province_name || item.contract_id || fallbackName || ""
    }

    function detailText(item) {
        if (!item) return ""
        if (item.faction_name) return GuiText.senateInfluenceDetail(item.faction_name, item.influence)
        if (item.threat_level !== undefined) return GuiText.senateThreatDetail(item.threat_level, item.naval_required)
        if (item.indemnity !== undefined) return GuiText.senatePeaceDetail(item.indemnity, item.duration)
        if (item.governor_type_name) return item.governor_type_name
        if (item.base_cost !== undefined) return GuiText.senateContractDetail(item.base_cost, item.expected_profit)
        return item.status || item.type || ""
    }

    function proposalTitle(item) {
        if (!item) return ""
        return item.title || item.label || item.name || item.type || ""
    }

    function proposalDetail(item) {
        if (!item) return ""
        return item.detail || item.summary || item.description || ""
    }

    function resultMark(item) {
        if (!item) return "\u2713"
        return (item.result === "rejected" || item.result === "vetoed") ? "\u2717" : "\u2713"
    }

    function resultMarkColor(item) {
        if (!item) return theme.statusSuccess
        return (item.result === "rejected" || item.result === "vetoed") ? "#B3261E" : theme.statusSuccess
    }

    // WP-J Group C G7 Test R4 Delta（delta v1.9 / FC-C32）：②「2 元老院表决」面板
    // **非输入态结果字形**的 **②-local** 判定（**禁**改共享 `resultMark()`/`resultMarkColor()`——
    // ③ 否决面板仍需 `vetoed → ✗`）。口径 = 仅反映「元老院表决」：
    //   `rejected → ✗`；`passed`/`vetoed → ✓`（依据 `veto_candidate_ids = passed && !vetoed`
    //   ⇒ **`vetoed ⟹ 元老院已通过`**）；无表决数据行（`.result` 缺失/未知）→ **空白（禁 ✗）**。
    // WP-J Group C G7 Test R5 Delta（delta v2.0 / FC-C35 —— 数据源**扩展**，修订 FC-C32）：
    //   ② 结果字形须**元老院表决一完成（`tribune_veto` 步）即显**，不再等到 `results`。
    //   `results` 步：`item.result` 权威（复用上方口径）。`.result` **缺失**（`tribune_veto` 步、
    //   否决前）→ **回退** `root.voteResultFor(item.id)`（元老院表决投影 `vote_results`；该步已在
    //   read-model）——`vr && vr.total_influence > 0` ⇒ `vr.passed ? ✓ : ✗`；否则**空白**。
    //   **否决不改写 ②**：本回退分支**仅在 `.result` 缺失时命中**（即无否决的 `tribune_veto` 步），
    //   `vetoed` 只经 `item.result` 路径命中（→ ✓）；**绝不**被否决短路污染（FC-C32 禁项守恒）。
    function senateResultMark(item) {
        if (!item) return ""
        if (item.result === "rejected") return "\u2717"
        if (item.result === "passed" || item.result === "vetoed") return "\u2713"
        var vr = root.voteResultFor(item.id)
        // WP-J Group C G7 Test R6 Delta（delta v2.3 / FC-C39 协同，OBS-C39-1）：C1 后 vetoed 行带
        // 真 tally，回退分支须加 `!vr.vetoed` 门，否则「否决已记录、`item.result` 未打标」的中间态
        // 误显红 ✗，违 FC-C32『vetoed 不改写 ② / 禁第二红叉源』。vetoed 行仅经 `item.result` 路径（→ ✓）。
        if (vr && vr.total_influence > 0 && !vr.vetoed) return vr.passed ? "\u2713" : "\u2717"
        return ""
    }

    function senateResultMarkColor(item) {
        if (!item) return theme.statusSuccess
        if (item.result === "rejected") return "#B3261E"
        if (item.result === "passed" || item.result === "vetoed") return theme.statusSuccess
        var vr = root.voteResultFor(item.id)
        if (vr && vr.total_influence > 0 && !vr.vetoed && !vr.passed) return "#B3261E"
        return theme.statusSuccess
    }

    // WP-J Group C G7 Test R5 Delta（delta v2.0 / FC-C36，**FC-C22 SUPERSEDED**）：`senateVoteIdentityGap`
    // **退役** —— ② 身份文本已由 `CheckBox.contentItem` 承载**重构为行内同级 `Text`**（与 ①③ 同构），
    // 行内间距 = `RowLayout{ spacing:6 }`，不再需要「指示器宽 + 基准」的净缩进特例。

    // WP-J Group C G7 Test R4 Delta（delta v1.9 / FC-C31，Q2 方案回退）：**撤回全部自绘勾选框
    // `indicator`**（R3 方案甲 `FC-C28`/`FC-C29`/`FC-C30` = WITHDRAWN）⇒ ①②③ + 战争卡四行勾选框
    // **全部回归平台默认样式指示器**（系统勾选框；③ 勾选 = 系统 `☑`，Owner 明示可接受，
    // **不再要求 ⮽/自绘叉**）。四行不再有任何自绘勾/叉子图元；状态机（`checked`/`onToggled`/
    // `enabled`/选择与表决语义）**字节级不变**；行卡 `FC-C18` / ② 身份文本 wrap `FC-C15–C17` /
    // 单一 `ScrollView` 保留。
    // ② 非输入态结果字形**保留**（K2=A），但**移出被撤的 `indicator`**、改由**行内独立无框 `Text`**
    // 承载（②-local 谓词 `senateResultMark()`/`senateResultMarkColor()`，见 `FC-C32`）。

    // WP-F R1-F-03：per-proposal 支持率 helper（join 权威 vote_results，纯展示除法，禁重算/decider 重入）
    function voteResultFor(proposalId) {
        var rows = sessionStore.senateVoteResults || []
        for (var i = 0; i < rows.length; i++) {
            if (Number(rows[i].proposal_id) === Number(proposalId)) return rows[i]
        }
        return null
    }
    function supportRateText(vr) {
        if (!vr || vr.total_influence <= 0) return "\u652f\u6301\u7387 \u2014"
        var pct = Math.round(vr.support_influence * 100 / vr.total_influence)
        if (vr.vetoed) return "\u672a\u901a\u8fc7 \u00b7 \u652f\u6301\u7387 " + pct + "%"
        if (vr.passed) return "\u901a\u8fc7 \u00b7 \u652f\u6301\u7387 " + pct + "%"
        return "\u672a\u901a\u8fc7 \u00b7 \u652f\u6301\u7387 " + pct + "%"
    }

    function senateVoteButtonText() {
        if (sessionStore.senateCurrentStep === "proposal") return "\u7b49\u5f85\u6267\u653f\u5b98\u63d0\u4ea4\u6cd5\u6848"
        return "\u786e\u8ba4\u8868\u51b3 \u2192 \u79fb\u4ea4\u5426\u51b3\u73af\u8282"
    }

    // WP-F R2-01（F-01B/C/D）：Stage 3 只渲染权威 passed-only 候选集——按后端
    // senateVetoCandidateIds 映射 display rows（禁 QML 平行过滤/重算/阈值判定）
    function vetoCandidateRows() {
        var ids = sessionStore.senateVetoCandidateIds || []
        var rows = sessionStore.senateSubmittedProposals || []
        var out = []
        for (var i = 0; i < rows.length; i++) {
            for (var j = 0; j < ids.length; j++) {
                if (Number(rows[i].id) === Number(ids[j])) { out.push(rows[i]); break }
            }
        }
        return out
    }

    function passedResultRows() {
        var rows = sessionStore.senateSubmittedProposals || []
        var passed = []
        for (var i = 0; i < rows.length; i++) {
            if ((rows[i].result || "passed") === "passed") passed.push(rows[i])
        }
        return passed
    }

    function rejectedResultRows() {
        var rows = sessionStore.senateSubmittedProposals || []
        var rejected = []
        for (var i = 0; i < rows.length; i++) {
            if (rows[i].result === "rejected") rejected.push(rows[i])
        }
        return rejected
    }

    function resultTitleList(rows) {
        var names = []
        for (var i = 0; i < rows.length; i++) names.push(proposalTitle(rows[i]))
        return names.join("\uff1b")
    }

    function passedResultText() {
        var text = resultTitleList(passedResultRows())
        return text.length > 0 ? text : "\u65e0\u6700\u7ec8\u901a\u8fc7\u6cd5\u6848"
    }

    function rejectedResultText() {
        var text = resultTitleList(rejectedResultRows())
        return text.length > 0 ? text : "\u65e0"
    }

    // WP-F R3：被保民官否决（vetoed only）——缺陷 B：「保民官否决 N 项」权威计数
    function vetoedResultRows() {
        var rows = sessionStore.senateSubmittedProposals || []
        var out = []
        for (var i = 0; i < rows.length; i++) {
            if (rows[i].result === "vetoed") out.push(rows[i])
        }
        return out
    }

    // WP-F R3：Stage 3 结果态——进入否决环节的提案 = passed + vetoed（failed 排除）
    function vetoResultRows() {
        var rows = sessionStore.senateSubmittedProposals || []
        var out = []
        for (var i = 0; i < rows.length; i++) {
            if (rows[i].result === "passed" || rows[i].result === "vetoed") out.push(rows[i])
        }
        return out
    }

    // WP-F R3：vetoed 标题文案（镜像 rejectedResultText）
    function vetoedResultText() {
        var text = resultTitleList(vetoedResultRows())
        return text.length > 0 ? text : "\u65e0"
    }

    // WP-F R3：Stage 3 Repeater 数据源——结果态用 passed+vetoed，活态保持 vetoCandidateRows（权威 passed-only 候选集）
    function stageThreeRows() {
        if (sessionStore.senateCurrentStep === "results") return root.vetoResultRows()
        return root.vetoCandidateRows()
    }

    // S4: Governor assignment summary for results display
    function _governorSummary() {
        var rows = sessionStore.senateResult.governor_assignments || []
        if (rows.length === 0) return "\u65e0\u884c\u7701\u9700\u8981\u4efb\u547d\u603b\u7763"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            parts.push(rows[i].name + "(" + rows[i].province_id + ")")
        }
        return parts.join("\uff1b")
    }

    // S4: Rebellion commander assignment summary for results display
    function _commanderSummary() {
        var rows = sessionStore.senateResult.rebellion_commander_assignments || []
        if (rows.length === 0) return "\u65e0\u8d77\u4e49\u9700\u8981\u6307\u6325\u5b98"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            parts.push(rows[i].name + "(" + rows[i].rebellion_id + ")")
        }
        return parts.join("\uff1b")
    }

    // S4: Fleet assignment summary for results display
    function _fleetSummary() {
        var rows = sessionStore.senateResult.fleet_assignments || []
        if (rows.length === 0) return "\u65e0"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            parts.push(rows[i].war_name + "(" + rows[i].total_power + ")")
        }
        return parts.join("\uff1b")
    }

    // ---- WP-D AU-6: Public Announcement 渲染（数据来自 authoritative DTO，禁 QML 推导） ----
    function _announcementEnactedText() {
        var rows = (sessionStore.senatePublicAnnouncement || {}).enacted_proposals || []
        if (rows.length === 0) return "\u65e0"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            var r = rows[i]
            var line = r.title || ""
            var kp = r.key_parameters || {}
            if (r.type === "land" && kp.amount_C !== undefined) {
                line += "（" + (kp.act_type === "sale" ? "\u51fa\u552e" : "\u5206\u914d") + " " + kp.amount_C + " C \u516c\u5730）"
            } else if (r.type === "war" && kp.legions !== undefined) {
                line += "（" + kp.legions + " \u519b\u56e2\uff09"
            } else if (r.type === "budget" && kp.modified_budget !== undefined) {
                line += "（\u9884\u7b97 " + kp.modified_budget + " T\uff09"
            }
            parts.push(line)
        }
        return parts.join("\uff1b")
    }

    function _directActionText() {
        var rows = (sessionStore.senatePublicAnnouncement || {}).direct_actions || []
        if (rows.length === 0) return "\u65e0"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            var a = rows[i]
            parts.push("\u63a5\u7ba1\u6218\u4e89 \u2014 " + (a.war_name || a.war_id) + " \u00b7 " + (a.commander_name || a.commander_id))
        }
        return parts.join("\uff1b")
    }

    // ---- R6 §D.4（DA-4 B3）：Consul 冻结 direct 决定（三身份之一；待边界执行） ----
    function _consulDirectRows() {
        return (sessionStore.senatePublicAnnouncement || {}).consul_direct_decisions || []
    }

    function _consulDirectLabel() {
        // R8（SA §5.2 C-04，D-R8-02）：结果 direct 行身份词 = 人话「执政官决定」
        // （step 退出后允许）；**禁**透传 producer 技术串。
        var rows = root._consulDirectRows()
        if (rows.length === 0) return ""
        return "执政官决定"
    }

    function _consulDirectStatus() {
        // R8（SA §5.2 C-05/C-06，FC-UI-03）：结果 direct 行执行状态（边界前「待战斗阶段执行」）。
        var rows = root._consulDirectRows()
        if (rows.length === 0) return ""
        return root.consulExecutionStatus(rows[0])
    }

    function _consulDirectText() {
        // R8（SA §5.2 C-04）：结果 direct 行人话决策摘要（身份取冻结快照，不猜 subtype）。
        var rows = root._consulDirectRows()
        if (rows.length === 0) return "\u65e0"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            parts.push(root.consulDecisionSummary(rows[i]))
        }
        return parts.join("\uff1b")
    }

    // ---- R7（SA §A.5，DA-R7 B1）：冻结 Consul direct 行——step 无关可见（数据源 = 顶层 DTO，非 PA） ----
    function frozenDirectRows() { return sessionStore.senateConsulDirectDecisions || [] }
    function frozenDirectIdentityText(row) {
        var n = (row.reinforcement_n === undefined || row.reinforcement_n === null) ? 0 : row.reinforcement_n
        return (row.war_label || row.war_id) + " · " + (row.target_commander_label || row.target_commander_id)
             + " · N=" + n
    }
    // R8（SA §5.2 C-04，D-R8-02）：冻结/结果 direct 行人话决策摘要——身份取冻结 ledger
    // 快照（war_label / target_commander_label / reinforcement_n）；**不**从 live state
    // 猜接管/继续 subtype、不重建身份；仅 step 退出后由 copy 门呈现。
    function consulDecisionSummary(row) {
        row = row || ({})
        var n = (row.reinforcement_n === undefined || row.reinforcement_n === null) ? 0 : row.reinforcement_n
        return "执政官决定：" + (row.war_label || row.war_id)
             + "，由 " + (row.target_commander_label || row.target_commander_id) + " 指挥"
             + "，增援 " + n + " 个军团"
    }
    // R8（SA §5.2 C-05/C-06，FC-UI-03，D-R8-03）：执行状态人话——仅 execution=="executed"
    // （receipt COMMITTED）显示「已执行」；边界前「待战斗阶段执行（尚未执行）」。
    // UI 只读 execution、不推断；**禁**透传 producer 技术 receipt 文案。
    function consulExecutionStatus(row) {
        row = row || ({})
        return (row.execution === "executed") ? "已执行" : "待战斗阶段执行（尚未执行）"
    }

    // ---- R7（SA §B.2，DA-R7 B2）：bounded 错误呈现 helper 体（G3 P2-2 落地）。
    // 取数源 = sessionStore.senateSubmitErrors（+ ByWar 索引）；纯只读展示，
    // 零判定 / 零 Store 写 / 不触任何 _refresh_*（保证 error 呈现不破坏草稿）。 ----
    function pendingErrorWarIds() {
        var byWar = sessionStore.senateSubmitErrorsByWar || {}
        var out = []
        for (var k in byWar) {
            if (byWar.hasOwnProperty(k) && byWar[k] && byWar[k].length > 0) out.push(String(k))
        }
        return out
    }
    function senateErrorStripText() {
        var pending = root.pendingErrorWarIds()
        if (pending.length > 0) return "仍有 " + pending.length + " 张战卡待修正"
        // R7（SA §B.7 + G3 P2-1，DA-R7 B3）：pending==0 区分「已逐卡确认（编辑过）」
        // vs「从未编辑（仅包级错误）」；**永不**出现「有效/通过」green 声明。
        var edited = false
        for (var k in root.errorAckWars) {
            if (root.errorAckWars.hasOwnProperty(k)) { edited = true; break }
        }
        if (edited) return "已修改受影响字段，请重新提交以校验（尚未校验）"
        return "请修正后重新提交（尚未校验）"
    }
    // R7（SA §B.7，DA-R7 B3）：逐卡 error 装配——卡集合仍取 Core 权威
    // senateSubmitErrorsByWar（details.claims/requests 关联）；已 ack 的卡返回空（仅清该卡红框）。
    function cardErrorsFor(warId) {
        if (root.errorAckWars[String(warId)]) return []
        var byWar = sessionStore.senateSubmitErrorsByWar || {}
        return byWar[warId] || []
    }
    // R7（SA §B.7，DA-R7 B3）：编辑受影响卡 → 逐卡 ack（仅清该卡红框；**不**声明有效）。
    function onWarDraftEdited(warId, newDraft) {
        root.setWarDraft(warId, newDraft)
        var byWar = sessionStore.senateSubmitErrorsByWar || {}
        var errs = byWar[warId]
        if (errs !== undefined && errs !== null && errs.length > 0) {
            var next = {}
            for (var k in root.errorAckWars) {
                if (root.errorAckWars.hasOwnProperty(k)) next[k] = root.errorAckWars[k]
            }
            next[String(warId)] = true
            root.errorAckWars = next
        }
    }
    function _errCode(item) {
        if (!item) return ""
        return (item.code !== undefined && item.code !== null) ? String(item.code) : ""
    }
    function _errField(item) {
        if (!item) return ""
        return (item.field !== undefined && item.field !== null) ? String(item.field) : ""
    }
    function _errMessage(item) {
        if (!item) return ""
        return (item.message !== undefined && item.message !== null) ? String(item.message) : ""
    }
    // 人话摘要：错误项数 + 受影响 War 数；**不声明任何「有效 / 通过」**。
    function senateErrorSummaryText() {
        var items = sessionStore.senateSubmitErrors || []
        var warCount = root.pendingErrorWarIds().length
        var s = "共 " + items.length + " 项校验错误"
        if (warCount > 0) s += "，涉及 " + warCount + " 张战卡"
        return s + "。请修正后重新提交（尚未校验）。"
    }
    // R8（SA §5.3，FC-UI-04）：结算 warning 不直显 finalization/stage 技术串（人话呈现）。
    function senateFinalizationWarningText() {
        if (sessionStore.senateFinalizationWarning === "") return ""
        return "元老院结算未完成：提案包已发布（不撤销、不允许重发包），请稍后自动重试。"
    }
    // R8（SA §5.3，FC-UI-04，D-R8-04）：诊断**人话映射**——code 作内部查表键，玩家面
    // 直出「发生什么 + 如何修复」，**禁** machine code / field token / opaque ID。
    function senateErrorHumanMessage(item) {
        var code = root._errCode(item)
        if (code === "REINFORCEMENT_INVALID") return "增援军团数量不符合要求，请修改数量。"
        if (code === "LEGION_POOL_EXCEEDED") {
            var d = (item && item.details) ? item.details : {}
            var advice = "增援请求超过可用军团，请减少增援军团数量"
            if (d.requested_total !== undefined && d.available_total !== undefined) {
                advice += "（请求 " + d.requested_total + " / 可用 " + d.available_total
                if (d.reduce_by !== undefined) advice += " → 请减少 " + d.reduce_by
                advice += "）"
            }
            return advice + "。"
        }
        if (code === "COMMANDER_CLAIM_DUPLICATE") return "同一指挥官不能同时指挥这些战争，请为涉事战争选择不同指挥官。"
        if (code === "COMMANDER_TARGET_INVALID") return "所选指挥官不可用，请重新选择指挥官。"
        if (code === "COMMANDER_INELIGIBLE") return "所选人物不符合指挥官资格，请另行选择。"
        if (code === "PACKAGE_ALREADY_SUBMITTED") return "本会期已提交，请查看已提交内容。"
        return "配置未能提交，请检查标记字段后重试。"
    }
    // R8（SA §5.3）：涉事战争人话名称（label 优先；缺失 → 明示不可用，**不回退 raw ID、不猜名字**）。
    function senateWarLanguageName(warId) {
        var cards = sessionStore.senateWarCards || []
        for (var i = 0; i < cards.length; i++) {
            if (String(cards[i].war_id) === String(warId)) {
                var nm = cards[i].war_name
                if (nm !== undefined && nm !== null && String(nm) !== "") return String(nm)
            }
        }
        return "战争名称暂不可用"
    }
    // R8（SA §5.3）：涉事指挥官人话名称（候选/冻结 label 优先；缺失 → 明示不可用，不露 opaque ID）。
    function senateCommanderDisplayName(cmdId) {
        var cards = sessionStore.senateWarCards || []
        for (var i = 0; i < cards.length; i++) {
            var c = cards[i]
            if (c.current_commander_label && String(c.current_commander_id) === String(cmdId)) return String(c.current_commander_label)
            if (c.target_commander_label && String(c.target_commander_id) === String(cmdId)) return String(c.target_commander_label)
            var cands = c.commander_candidates || []
            for (var j = 0; j < cands.length; j++) {
                if (String(cands[j].figure_id) === String(cmdId)) {
                    var lbl = cands[j].label
                    if (lbl !== undefined && lbl !== null && String(lbl) !== "") return String(lbl)
                }
            }
        }
        return "指挥官身份暂不可用"
    }
    // 单行详情：人话（发生什么 + 如何修复）；**不**透出 machine code / field token。
    function senateErrorDetailLine(item) {
        return root.senateErrorHumanMessage(item)
    }
    // 受影响对象人话清单（只读展示；取 Core 权威 details；用 label，不用 opaque ID）。
    function senateErrorDetailExtra(item) {
        var d = (item && item.details) ? item.details : {}
        var parts = []
        var claims = d.claims || []
        for (var i = 0; i < claims.length; i++) {
            var c = claims[i]
            if (c.war_id === undefined || c.war_id === null) continue
            var line = "涉事战争：" + root.senateWarLanguageName(c.war_id)
            if (c.commander_id !== undefined && c.commander_id !== null) {
                line += " · 指挥官：" + root.senateCommanderDisplayName(c.commander_id)
            }
            parts.push(line)
        }
        var requests = d.requests || []
        for (var j = 0; j < requests.length; j++) {
            var r = requests[j]
            if (r.war_id === undefined || r.war_id === null) continue
            var rline = "涉事战争：" + root.senateWarLanguageName(r.war_id)
            if (r.reinforcement_n !== undefined && r.reinforcement_n !== null) {
                rline += "（请求增援 " + r.reinforcement_n + " 个军团）"
            }
            parts.push(rline)
        }
        var out = []
        for (var k = 0; k < parts.length; k++) {
            if (out.indexOf(parts[k]) < 0) out.push(parts[k])
        }
        return out.join("；")
    }
    // R8（SA §5.3 / D-R8-04，FC-UI-04）：machine JSON 渲染**已退役**——不再进玩家面。
    // 保留函数签名（R7 契约）但不再产出 raw JSON（无调用点）；诊断留 Store / 运行日志。
    function senateErrorMachineJson() {
        return ""
    }

    function tribuneActionText() {
        // WP-J Group B ④ (J-AC-02 / FC-B10/B12/B13): 归属绑定**权威 actor/source**——
        //   sessionStore.senateVetoControlMode（← politics.resolve_veto_control），
        //   **非**可用性位 canManuallySelectSenateVeto（本缺陷根因）。执行后（results，
        //   mode 仍 HUMAN）不得回塌「AI判定」；NONE → 「无保民官，跳过否决」不空白。
        var mode = sessionStore.senateVetoControlMode
        if (mode === "HUMAN") return "\u5224\u5b9a\u5426\u51b3 \u2192 \u516c\u793a\u7ed3\u679c"
        if (mode === "NONE") return "\u65e0\u4fdd\u6c11\u5b98\uff0c\u8df3\u8fc7\u5426\u51b3"
        return "AI\u5224\u5b9a\u5426\u51b3 \u2192 \u516c\u793a\u7ed3\u679c"
    }

    function hasSelectedVeto(id) {
        return selectedVetoProposalIds.indexOf(id) >= 0
    }

    function setVetoSelected(id, checked) {
        if (id === undefined || id === null || isNaN(id)) return
        var next = selectedVetoProposalIds.slice()
        var pos = next.indexOf(id)
        if (checked && pos < 0) next.push(id)
        if (!checked && pos >= 0) next.splice(pos, 1)
        selectedVetoProposalIds = next
    }

    // WP-J Group C G7 Test R7 Delta（delta v2.3 / FC-C41）：② 专属选择集读写（仿 ③；**仅 ②**）。
    function hasSelectedSenateVote(id) {
        return selectedSenateVoteIds.indexOf(id) >= 0
    }

    function setSenateVoteSelected(id, checked) {
        if (id === undefined || id === null || isNaN(id)) return
        var next = selectedSenateVoteIds.slice()
        var pos = next.indexOf(id)
        if (checked && pos < 0) next.push(id)
        if (!checked && pos >= 0) next.splice(pos, 1)
        selectedSenateVoteIds = next
    }

    // WP-J Group C G7 Test R7 Delta（delta v2.3 / FC-C41(4)，OBS-R7-3）：② 选择集**随会期重置**——
    // 会期提案集（id 集合）变化即清空（新会期 `proposal_id` 可能复用，防残留串味）。
    function syncSenateVoteSelection() {
        var rows = sessionStore.senateSubmittedProposals || []
        var ids = []
        for (var i = 0; i < rows.length; i++) {
            if (rows[i].id !== undefined && rows[i].id !== null) ids.push(Number(rows[i].id))
        }
        ids.sort(function(a, b) { return a - b })
        var key = ids.join(",")
        if (key !== _senateVoteSelectionKey) {
            _senateVoteSelectionKey = key
            selectedSenateVoteIds = []
        }
    }

    function leaderCountCopy(count) {
        return GuiText.senateLeaderCount(count)
    }

    // ---- WP-05V V3: 派系色（FC-08 冻结值：Opt=#8B0000 / Pop=#006400 / Equ=#00008B） ----
    // WP-F S1-2 (003/R-01): 本地三分支硬编码已删除 → 共享 FactionStyle 实例（factionStyle.factionColor）。

    // ---- WP-05V V4 (G6 Narrow): FC-09 阶级枚举名 → 中文标签 ----
    function classTierLabel(tier) {
        if (tier === "NOBILE") return "贵族"
        if (tier === "EQUES") return "骑士"
        if (tier === "PLEBEIAN") return "平民"
        return tier || ""
    }

    // ---- WP-05V G6 Narrow: FC-14 governor 候选人只读信息（复用 governorAppointments DTO） ----
    function governorCandidateInfo(proposal) {
        if (!proposal || !proposal.params) return null
        var provId = proposal.params.province_id
        var candId = proposal.params.candidate_id
        var appts = sessionStore.governorAppointments || {}
        var pending = appts.pending_provinces || []
        for (var i = 0; i < pending.length; i++) {
            if (pending[i].province_id !== provId) continue
            var cands = pending[i].candidates || []
            for (var j = 0; j < cands.length; j++) {
                if (cands[j].id === candId) return cands[j]
            }
        }
        return null
    }

    function governorCandidateNameLine(proposal) {
        var c = governorCandidateInfo(proposal)
        if (!c) return ""
        return '<font color="' + factionStyle.factionColor(c.faction_name) + '">' + (c.name || "") + "</font>"
            + " · " + classTierLabel(c.class_tier)
    }

    function governorCandidateAttrsLine(proposal) {
        var c = governorCandidateInfo(proposal)
        if (!c) return ""
        return "\u519B\u7565 " + (c.martial !== undefined ? c.martial : "\u2014")
            + " \u00B7 \u667A\u7565 " + (c.intelligence !== undefined ? c.intelligence : "\u2014")
            + " \u00B7 \u9B45\u529B " + (c.charisma !== undefined ? c.charisma : "\u2014")
            + " \u00B7 \u5F71\u54CD\u529B " + (c.influence !== undefined ? c.influence : "\u2014")
    }

    function seatLineRich() {
        var rows = sessionStore.senateSeatShares || []
        if (rows.length === 0) return "席位占比：暂无"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            var name = rows[i].faction_name || rows[i].faction_id || ""
            var color = factionStyle.factionColor(rows[i].faction_name)
            parts.push('<font color="' + color + '">' + name + " " + (rows[i].percent || 0) + "%" + "</font>")
        }
        return "席位占比：" + parts.join(" · ")
    }

    function presidingLine() {
        var po = sessionStore.senatePresidingOfficer || {}
        var name = po.name || "暂无"
        var office = po.office || "官职未定"
        var factionName = po.faction_name || ""
        var base = "会议主持："
        if (factionName.length > 0) {
            return base
                + '<font color="' + factionStyle.factionColor(factionName) + '">' + name + '</font>'
                + "（" + office + "）"
                + ' · <font color="' + factionStyle.factionColor(factionName) + '">' + factionName + '</font>'
        }
        return base + name + "（" + office + "）"
    }

    function seatLine() {
        var rows = sessionStore.senateSeatShares || []
        if (rows.length === 0) return "席位占比：暂无"
        var parts = []
        for (var i = 0; i < rows.length; i++) {
            var name = rows[i].faction_name || rows[i].faction_id || ""
            parts.push(name + " " + (rows[i].percent || 0) + "%")
        }
        return "席位占比：" + parts.join(" · ")
    }

    function hasSelectedProposal(key) { return selectedProposalKeys.indexOf(key) >= 0 }

    function setProposalSelected(key, checked) {
        var next = selectedProposalKeys.slice()
        var pos = next.indexOf(key)
        if (checked && pos < 0) next.push(key)
        if (!checked && pos >= 0) next.splice(pos, 1)
        selectedProposalKeys = next
        // AU-R1-04a（R1-04 冻结契约）：checkbox 为控制交互——checked 自动展开 /
        // unchecked 折叠（无陈旧参数面板残留）；三角 toggleBillExpanded 保留为手动覆盖。
        var expanded = expandedBillKeys.slice()
        var epos = expanded.indexOf(key)
        if (checked && epos < 0) expanded.push(key)
        if (!checked && epos >= 0) expanded.splice(epos, 1)
        expandedBillKeys = expanded
    }

    // ---- R5（SA §5.1，DA-5）：统一 War Card 草稿 helper（纯本地输入暂存；初值取 DTO defaults）----
    function warDraftFor(warId) {
        var drafts = root.warCardDrafts || {}
        if (drafts[warId] !== undefined) return drafts[warId]
        var cards = sessionStore.senateWarCards || []
        for (var i = 0; i < cards.length; i++) {
            if (String(cards[i].war_id) === String(warId)) return cards[i].defaults || {}
        }
        return {}
    }
    function setWarDraft(warId, draft) {
        var next = {}
        for (var k in root.warCardDrafts) { if (root.warCardDrafts.hasOwnProperty(k)) next[k] = root.warCardDrafts[k] }
        next[String(warId)] = draft
        warCardDrafts = next
    }
    function selectedWarDrafts() {
        var rows = []
        var cards = sessionStore.senateWarCards || []
        for (var i = 0; i < cards.length; i++) {
            var d = root.warDraftFor(cards[i].war_id)
            if (!d || !d.checked) continue
            var m = d.mode || "command"
            // R6（SA §A.2）fail-closed：route 仅读 card.authority_by_mode[mode]；
            // 缺 route 的卡不提交（禁止 fallback direct）。
            var routes = cards[i].authority_by_mode || {}
            var authority = routes[m]
            if (authority !== "senate_vote" && authority !== "consul_direct") continue
            rows.push({
                "type": "war_proposal",
                "war_id": cards[i].war_id,
                "checked": true,
                "mode": m,
                "target_commander_id": d.target_commander_id,
                "reinforcement_n": d.reinforcement_n
            })
        }
        return rows
    }
    // 非 War 提案（governor/budget/land）：war/peace 已由统一 War Card 承担，不重复渲染
    function nonWarProposalOptions() {
        var out = []
        var options = sessionStore.senateProposalOptions || []
        for (var i = 0; i < options.length; i++) {
            var t = options[i].type
            if (t === "war" || t === "peace") continue
            out.push(options[i])
        }
        return out
    }

    function selectedProposals() {
        var rows = root.selectedWarDrafts()   // R5（SA §5.2）：统一 War Card → war drafts
        var options = root.nonWarProposalOptions()
        for (var i = 0; i < options.length; i++) {
            var o = options[i]
            if (!hasSelectedProposal(o.key)) continue
            var overrides = billParams[o.key]
            if (!overrides) { rows.push(o); continue }
            var merged = {}
            for (var k in o) { if (o.hasOwnProperty(k)) merged[k] = o[k] }
            var p = {}
            var baseParams = o.params || {}
            for (var pk in baseParams) { if (baseParams.hasOwnProperty(pk)) p[pk] = baseParams[pk] }
            for (var ok in overrides) { if (overrides.hasOwnProperty(ok)) p[ok] = overrides[ok] }
            merged.params = p
            rows.push(merged)
        }
        return rows
    }

    function syncDefaultSelection() {
        var options = root.nonWarProposalOptions()
        var next = []
        for (var i = 0; i < options.length; i++) {
            if (options[i].type === "budget") next.push(options[i].key)
        }
        selectedProposalKeys = next
    }

    // ---- WP-05V V2: accordion 展开状态 + 参数覆盖 ----

    property var expandedBillKeys: []
    property var billParams: ({})

    function toggleBillExpanded(key) {
        var next = expandedBillKeys.slice()
        var pos = next.indexOf(key)
        if (pos >= 0) next.splice(pos, 1)
        else next.push(key)
        expandedBillKeys = next
    }

    function expandCheckedBills() {
        expandedBillKeys = selectedProposalKeys.slice()
    }

    function billParamValue(key, name, fallback) {
        var o = billParams[key]
        if (o && o[name] !== undefined) return o[name]
        return fallback
    }

    function setBillParam(key, name, value) {
        var next = {}
        for (var k in billParams) {
            if (!billParams.hasOwnProperty(k)) continue
            var sub = {}
            for (var n in billParams[k]) { if (billParams[k].hasOwnProperty(n)) sub[n] = billParams[k][n] }
            next[k] = sub
        }
        var target = next[key] || {}
        target[name] = value
        next[key] = target
        billParams = next
    }

    function legionIndexFor(v, model) {
        if (!model || !v) return -1
        return model.indexOf(v)
    }

    function hasZeroValueLandSelection() {
        var options = root.nonWarProposalOptions()
        for (var i = 0; i < options.length; i++) {
            var o = options[i]
            if (o.type !== "land" || !hasSelectedProposal(o.key)) continue
            var amountC = billParamValue(o.key, "amount_C", (o.params && o.params.amount_C) || 0)
            var publicLand = o.public_land || 0
            if (amountC <= 0 || publicLand <= 0) return true
        }
        return false
    }

    // ---- WP-05V V4: FC-12 表决参数描述（复用 proposal params，回退 label） ----
    function voteParamDescription(item) {
        if (!item) return ""
        if (item.type === "war") return ""  // 后端 _proposal_label 已含「（征召 N 个军团）」，避免重复（G5 识图缺陷）
        if (item.type === "budget") return ""  // 后端 _proposal_label 已含「（预算 N T）」，避免重复（G5 识图缺陷，与 war 同源）
        if (item.type === "land") return ""  // AU-7：后端 _proposal_label 已含「出售 N C（约 M%）」，与 war/budget 同源避免重复（实现注记：计划 Q-4 字面会与 label 重复，按文件内既有模式取 label 为准）
        return ""
    }

    function refreshAccordion() {
        syncDefaultSelection()
        expandCheckedBills()
    }

    Component.onCompleted: {
        refreshAccordion()
    }

    Connections {
        target: sessionStore
        function onSenateViewChanged() {
            // WP-J Group C G7 Test R7 Delta（FC-C41(4)，OBS-R7-3）：② 选择集随会期重置。
            root.syncSenateVoteSelection()
            // 提案阶段：选项加载完成后同步默认选中并展开（G7「只有法案条目无控件」闭合）
            if (sessionStore.senateCurrentStep === "proposal") {
                if (selectedProposalKeys.length === 0) root.refreshAccordion()
                else root.expandCheckedBills()
            }
        }
    }

    // R7（SA §B.2，DA-R7 B2）：失败即开（bounded）/ 成功（权威清空）即关；
    // **关闭不清除错误态**（状态条仍在、可重开），仅成功 revalidate 才清。
    Connections {
        target: sessionStore
        function onSenateSubmitErrorsChanged() {
            // R7（SA §B.7，DA-R7 B3）：每次新失败重置逐卡 ack（R-02 缓解）；成功亦清。
            root.errorAckWars = ({})
            if (sessionStore.hasSenateSubmitErrors) senateValidationDialog.open()
            else senateValidationDialog.close()
        }
    }

    // R8（SA §4.1 **L-D v1.3**，FC-UI-05，AC-05；G2-delta-2，Owner 2026-09-21 Q2）——Dialog 专用
    // envelope（**非** L-5/L-7）。唯一位置基准 W = 游戏窗口当前 client rect（= Window.contentItem
    // rect；**禁用**最大尺寸 / 声明父项 width·height(rect) / 上一次打开的尺寸·位置 / 屏幕 rect）；
    // 尺寸**内容自适应**（短内容小框、无大留白）；高度上限 Dh ≤ round(0.40×W.h)（±2px），超限正文内滚；
    // 以 W 居中（谓词①②）；可见标题条**可拖动**且拖动中**实时夹取**于 W 内；每次 open **复位居中**
    // （不记忆位置）；产品级 **WIN_MIN=1280×720**（Owner 2026-09-21 11:59 确认）⇒ 删除旧「极小窗
    // 兜底 / 阻塞」分支（predicate 简化）。
    // 隐藏测量镜像（**声明式、零副作用**）：单行 intrinsic 宽 / 换行后自然高。
    // 用真实 Text 排版测量（按实际 font），**不写回自身属性** → 无 binding loop。
    Column {
        id: ldWidthMirror
        visible: false
        Text { text: "战争配置无法提交"; font.pixelSize: 13; font.bold: true; wrapMode: Text.NoWrap }
        Text { text: root.senateErrorSummaryText(); font.pixelSize: 12; wrapMode: Text.NoWrap }
        Repeater {
            model: sessionStore.senateSubmitErrors || []
            delegate: Column {
                Text { text: root.senateErrorDetailLine(modelData); font.pixelSize: 11; wrapMode: Text.NoWrap }
                Text { text: root.senateErrorDetailExtra(modelData); font.pixelSize: 10; wrapMode: Text.NoWrap }
            }
        }
    }
    Column {
        id: ldHeightMirror
        visible: false
        width: Math.max(1, senateValidationDialog._dw - 2 * root.ldDialogPadding)
        spacing: 4
        Text {
            width: parent.width
            text: root.senateErrorSummaryText()
            font.pixelSize: 12
            wrapMode: Text.Wrap
        }
        Repeater {
            model: sessionStore.senateSubmitErrors || []
            delegate: Column {
                width: ldHeightMirror.width
                spacing: 1
                Text {
                    width: parent.width
                    text: root.senateErrorDetailLine(modelData)
                    font.pixelSize: 11
                    wrapMode: Text.Wrap
                }
                Text {
                    width: parent.width
                    visible: text !== ""
                    text: root.senateErrorDetailExtra(modelData)
                    font.pixelSize: 10
                    wrapMode: Text.Wrap
                }
            }
        }
    }
    // L-D v1.3 冻结常量（SA §4.1）
    readonly property int ldWmin: 320
    readonly property int ldDialogPadding: 12
    readonly property int ldHhead: 40
    readonly property int ldHfoot: 40
    readonly property int ldChrome: 116              // Hhead40 + Hfoot40 + 2×padding12 + 2×gap6
    readonly property int ldWinMinW: 1280            // WIN_MIN（Owner 2026-09-21 11:59 确认）
    readonly property int ldWinMinH: 720
    // W = 游戏窗口当前 client rect（client 尺寸；无窗口时回退 root 尺寸）。
    function ldWindowW() {
        var w = (root.Window && root.Window.width !== undefined) ? root.Window.width : 0
        if (!w || w <= 0) w = (root.width > 0 ? root.width : 1440)
        return w
    }
    function ldWindowH() {
        var h = (root.Window && root.Window.height !== undefined) ? root.Window.height : 0
        if (!h || h <= 0) h = (root.height > 0 ? root.height : 900)
        return h
    }
    // Wmax=min(round(0.50×W.w), W.w−32)；Hmax=round(0.40×W.h)
    function ldMaxW() { return Math.min(Math.round(0.50 * root.ldWindowW()), root.ldWindowW() - 32) }
    function ldMaxH() { return Math.round(0.40 * root.ldWindowH()) }
    // Wnat = 最宽单行内容 intrinsic 宽 + 2×padding。
    function ldNaturalWidth() {
        return Math.ceil(ldWidthMirror.implicitWidth) + 2 * root.ldDialogPadding
    }
    // HbodyNat = 正文（换行后）自然高。
    function ldBodyNaturalHeight() {
        return Math.ceil(ldHeightMirror.implicitHeight)
    }
    // 拖动夹取（谓词②：拖动后四边仍落 W 内）。
    function ldClampX(v) { return Math.max(0, Math.min(v, root.ldWindowW() - senateValidationDialog.width)) }
    function ldClampY(v) { return Math.max(0, Math.min(v, root.ldWindowH() - senateValidationDialog.height)) }

    // R7（SA §B.2，DA-R7 B2）：**bounded 错误详情 Dialog**——modal + ESC + Close，
    // 属 Popup/Overlay 层，**不参与**根 ColumnLayout 布局 ⇒ 永不 resize 主布局（R7-AC-08/10/15）。
    Dialog {
        id: senateValidationDialog
        objectName: "senateValidationDialog"
        // L-D v1.3：parent 锚到窗口顶层 Overlay.overlay（W 坐标空间原点 = 窗口 client 左上角）。
        parent: Overlay.overlay
        modal: true
        focus: true
        dim: true
        closePolicy: Popup.CloseOnEscape
        padding: 12
        // 尺寸（内容自适应）：宽 Dw=clamp(Wnat, 320, min(round(0.50×W.w), W.w−32))；
        // 高 Dh=min(Hchrome + HbodyNat, round(0.40×W.h))（短内容小框；超限正文内滚）。
        readonly property int _dw: Math.max(root.ldWmin, Math.min(Math.ceil(root.ldNaturalWidth()), root.ldMaxW()))
        readonly property int _hbodyCap: Math.max(12, root.ldMaxH() - root.ldChrome)
        readonly property int _hbodyNat: Math.max(12, root.ldBodyNaturalHeight())
        readonly property int _hbody: Math.max(12, Math.min(_hbodyNat, _hbodyCap))
        // 拖动状态：只改 (x,y)，不改 Dw/Dh、body contentY、内容或五框 scene rect。
        property bool _dragging: false
        property real _dragX: 0
        property real _dragY: 0
        property real _dragStartX: 0
        property real _dragStartY: 0
        width: _dw
        height: root.ldChrome + _hbody
        // 居中定位：未拖动时以 W 居中（每次 open 复位）；拖动中改用夹取后的 (x,y)。
        x: _dragging ? _dragX : Math.round((root.ldWindowW() - width) / 2)
        y: _dragging ? _dragY : Math.round((root.ldWindowH() - height) / 2)
        // 拖动入口：标题条指针拖动 → 仅改 (x,y)（实时夹取于 W 内）。
        function applyDrag(dx, dy) {
            _dragX = root.ldClampX(_dragStartX + dx)
            _dragY = root.ldClampY(_dragStartY + dy)
            _dragging = true
        }
        function resetDialogPosition() { _dragging = false }
        onOpened: resetDialogPosition()
        onClosed: resetDialogPosition()
        background: Rectangle {
            color: theme.ivoryDesk
            radius: 8
            border.color: theme.statusError
            border.width: 2
        }
        contentItem: ColumnLayout {
            spacing: 6
            // R8（SA §4.1 L-D v1.3，C-07）：固定 header 40——**可见拖动条**（grip + SizeAll 光标）
            // + 短标题「战争配置无法提交」；多行摘要 / 全部对象 / 修正建议进入下方唯一 body
            // ScrollView（禁 variable summary 侵占 footer）。
            Item {
                id: ldDialogHeaderBar
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                Rectangle {
                    id: ldDialogGrip
                    objectName: "senateDialogGrip"
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    width: 14
                    height: 18
                    radius: 3
                    color: "transparent"
                    Column {
                        anchors.centerIn: parent
                        spacing: 3
                        Repeater {
                            model: 3
                            delegate: Rectangle { width: 10; height: 2; radius: 1; color: theme.statusError }
                        }
                    }
                }
                Text {
                    objectName: "senateDialogHeader"
                    anchors.left: ldDialogGrip.right
                    anchors.leftMargin: 6
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: "战争配置无法提交"
                    color: theme.statusError
                    font.pixelSize: 13
                    font.bold: true
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                }
                HoverHandler { cursorShape: Qt.SizeAllCursor }
                DragHandler {
                    id: ldDialogDragHandler
                    target: null
                    onActiveChanged: {
                        if (active) {
                            senateValidationDialog._dragStartX = senateValidationDialog.x
                            senateValidationDialog._dragStartY = senateValidationDialog.y
                            senateValidationDialog._dragX = senateValidationDialog.x
                            senateValidationDialog._dragY = senateValidationDialog.y
                        }
                    }
                    onTranslationChanged: {
                        if (active) senateValidationDialog.applyDrag(translation.x, translation.y)
                    }
                }
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentWidth: availableWidth
                // L-D v1.3：仅垂直 AsNeeded（仅 HbodyNat>HbodyCap 时显滑块）；水平 AlwaysOff。
                ScrollBar.vertical.policy: ScrollBar.AsNeeded
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ColumnLayout {
                    width: parent.width
                    spacing: 4
                    Text {
                        text: root.senateErrorSummaryText()
                        color: theme.textDark
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                    Repeater {
                        model: sessionStore.senateSubmitErrors || []
                        delegate: ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Text {
                                text: root.senateErrorDetailLine(modelData)
                                color: theme.statusError
                                font.pixelSize: 11
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                elide: Text.ElideNone
                            }
                            Text {
                                visible: root.senateErrorDetailExtra(modelData) !== ""
                                text: root.senateErrorDetailExtra(modelData)
                                color: theme.textSecondary
                                font.pixelSize: 10
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }
            }
            // 固定 footer 40（Close 控件 ≥34 可 hit-test；ESC 与 Close 两种事件均关闭）。
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                ActionButton {
                    anchors.fill: parent
                    anchors.margins: 3
                    text: "关闭（可继续修改后重新提交）"
                    onTriggered: senateValidationDialog.close()
                }
            }
        }
    }

    // =========================================================================
    // R8（SA §4.1 L-1…L-9，FC-UI-06/07，AC-06/07）——**五框模型**布局（SLICE-R8-03 refit2 / design v1.6）
    //   #1 = GameShell Senate step bar（Region C InstructionSlot，保真不改）
    //   #2 = 本文件公示框（议事/表决合并单框，正文 5L + 独立滑块）senateAnnouncementBox
    //   #3–5 = 三个子环节框（占满余量、各自内滚、footer 固定不入滚动）
    // 唯一高度算法（U_S = Senate content surface = root viewport，SA §4.1 v1.6 唯一化；
    //   U_S 底缘 = Region C 外框底缘，shell 让渡 18px 底内边距；L 正文行高；Lt 标题行高）：
    //   Hnotice = 20 + Lt + 6 + 5L；rowW = U_S.w − 28；Hrow = U_S.h − 28 − Hnotice − 10
    //   公示 x=y=14 w=rowW h=Hnotice；row x=14 y=14+Hnotice+10 w=rowW h=Hrow
    //   （row.bottom = U_S.h − δ_in，δ_in = 14 ⇒ PF-1；scene Δ = E.top − row.bottom ≤ Δ_frozen = 28 ⇒ PF-2）
    //   panel 内 topMargin44 / left·right·bottom10，footer34 gap7 ⇒ Hbody = Hrow − 95 ≥ 4L
    //   **禁** 360/460 clamp、独立 132/78 结果框、外层兜底滚动、Qt 自动压缩、按内容改高。
    // =========================================================================
    FontMetrics {
        id: senateBodyMetrics
        font.family: theme.fontFamily
        font.pixelSize: theme.bodySize
    }
    FontMetrics {
        id: senateTitleMetrics
        font.family: theme.fontFamily
        font.pixelSize: 13
        font.bold: true
    }
    readonly property int lBody: Math.max(1, Math.ceil(senateBodyMetrics.lineSpacing))
    readonly property int lTitle: Math.max(1, Math.ceil(senateTitleMetrics.lineSpacing))
    readonly property int hNotice: 20 + lTitle + 6 + 5 * lBody
    readonly property int rowW: Math.max(1, Math.round(root.width) - 28)
    readonly property int hRow: Math.max(0, Math.round(root.height) - 28 - hNotice - 10)
    readonly property int noticeBodyH: Math.max(1, 5 * lBody)
    property string _lastAnnouncementStep: ""

    // #2 公示框（议事/表决合并单框）：固定标题「元老院议事」+ 正文 viewport 恰 5L + 独立 AsNeeded 滑块；
    // 正文首部依次 validation→finalization→议事内容→results 内容（L-6）；滑块出现/消失不改框几何（L-7）。
    Rectangle {
        id: senateAnnouncementBox
        objectName: "senateAnnouncementBox"
        x: 14
        y: 14
        width: root.rowW
        height: root.hNotice
        color: "#FFF7E9"
        border.color: "#D9AF63"
        border.width: 1
        radius: 6
        clip: true

        // 固定标题（title 区 Lt）
        Text {
            id: announcementTitle
            objectName: "senateAnnouncementTitle"
            x: 10
            y: 10
            width: parent.width - 20
            height: root.lTitle
            text: "🏛 元老院议事"
            color: "#2C1E12"
            font.pixelSize: 13
            font.bold: true
            wrapMode: Text.NoWrap
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
            lineHeightMode: Text.FixedHeight
            lineHeight: root.lTitle
        }

        // header 右侧保留位：短「结算异常」状态位 + 「错误详情」入口（仅 errors 时启用）；隐藏时保留同几何。
        Row {
            objectName: "senateAnnouncementHeaderSlots"
            anchors.right: parent.right
            anchors.rightMargin: 10
            anchors.verticalCenter: announcementTitle.verticalCenter
            spacing: 10
            Text {
                objectName: "senateAnnouncementFinalizationBadge"
                visible: sessionStore.senateFinalizationWarning !== ""
                text: "结算异常"
                color: "#9A2D0A"
                font.pixelSize: 11
                font.bold: true
            }
            Text {
                objectName: "senateAnnouncementErrorEntry"
                visible: sessionStore.hasSenateSubmitErrors
                text: "错误详情 ›"
                color: theme.statusError
                font.pixelSize: 11
                font.bold: true
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: senateValidationDialog.open()
                }
            }
        }

        // 正文 viewport 恰 5L（±1）；独立垂直 AsNeeded / 水平 AlwaysOff；滑块出现/消失不改框几何。
        ScrollView {
            id: senateAnnouncementBody
            objectName: "senateAnnouncementBody"
            x: 10
            y: 10 + root.lTitle + 6
            width: parent.width - 20
            height: root.noticeBodyH
            clip: true
            contentWidth: availableWidth
            ScrollBar.vertical.policy: ScrollBar.AsNeeded
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: parent.width
                spacing: 6

                // ① 包级校验失败摘要（28px 单行；保留 R7 bounded 语义；移至 #2 正文首部 - L-6）。
                Rectangle {
                    objectName: "senateValidationStrip"
                    visible: sessionStore.hasSenateSubmitErrors
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    Layout.minimumHeight: 28
                    Layout.maximumHeight: 28
                    radius: 6
                    color: Qt.rgba(theme.statusError.r, theme.statusError.g, theme.statusError.b, 0.08)
                    border.color: theme.statusError
                    border.width: 1
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        spacing: 8
                        Text {
                            text: "提交失败（未发布任何提案）"
                            color: theme.statusError
                            font.pixelSize: 11
                            font.bold: true
                            Layout.alignment: Qt.AlignVCenter
                        }
                        Text {
                            text: root.senateErrorStripText()
                            color: theme.statusError
                            font.pixelSize: 11
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                            wrapMode: Text.NoWrap
                            elide: Text.ElideRight
                            maximumLineCount: 1
                        }
                        Text {
                            text: "重开详情 ›"
                            color: theme.statusError
                            font.pixelSize: 11
                            font.bold: true
                            Layout.alignment: Qt.AlignVCenter
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: senateValidationDialog.open()
                            }
                        }
                    }
                }

                // ② 结算异常摘要（28px 单行；保留 R7 bounded 语义 + ToolTip 全文可达；移至 #2 正文首部 - L-6）。
                Rectangle {
                    objectName: "senateFinalizationWarningStrip"
                    visible: sessionStore.senateFinalizationWarning !== ""
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    Layout.minimumHeight: 28
                    Layout.maximumHeight: 28
                    radius: 6
                    color: "#FDF3E0"
                    border.color: "#E6A542"
                    border.width: 1
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        spacing: 8
                        Text {
                            text: "结算异常（提案包已发布 · 不撤销 / 不允许重发包）"
                            color: "#9A2D0A"
                            font.pixelSize: 11
                            font.bold: true
                            Layout.alignment: Qt.AlignVCenter
                        }
                        Text {
                            text: root.senateFinalizationWarningText()
                            color: "#7A1A00"
                            font.pixelSize: 11
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                            wrapMode: Text.NoWrap
                            elide: Text.ElideRight
                            maximumLineCount: 1
                            ToolTip.delay: 250
                            ToolTip.visible: finalizationWarnHover.containsMouse
                            ToolTip.text: root.senateFinalizationWarningText()
                            MouseArea {
                                id: finalizationWarnHover
                                anchors.fill: parent
                                hoverEnabled: true
                                acceptedButtons: Qt.NoButton
                            }
                        }
                    }
                }

                // ③ 议事内容（主持行 / 席位行，完整 wrap）
                Text {
                    text: root.presidingLine()
                    textFormat: Text.RichText
                    color: "#2C1E12"
                    font.pixelSize: 12
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    lineHeightMode: Text.FixedHeight
                    lineHeight: root.lBody
                }
                Text { text: root.seatLineRich(); textFormat: Text.RichText; color: "#9A2D0A"; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap; lineHeightMode: Text.FixedHeight; lineHeight: root.lBody }

                // ④ results 内容（step==results 时于同一 body 追加；不替换主持/席位、不重复造第二框 - L-5）
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    visible: sessionStore.senateCurrentStep === "results"
                    Text {
                        visible: root.vetoedResultRows().length > 0
                        text: "\u26d4 \u4fdd\u6c11\u5b98\u5426\u51b3 " + root.vetoedResultRows().length + " \u9879\uff1a" + root.vetoedResultText()
                        color: "#B3261E"
                        font.pixelSize: 12
                        font.bold: true
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                        lineHeightMode: Text.FixedHeight
                        lineHeight: root.lBody
                    }
                    Text {
                        visible: root.rejectedResultRows().length > 0
                        text: "\u26d4 \u672a\u901a\u8fc7 " + root.rejectedResultRows().length + " \u9879\uff1a" + root.rejectedResultText()
                        color: "#8A6D3B"
                        font.pixelSize: 12
                        font.bold: true
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                        lineHeightMode: Text.FixedHeight
                        lineHeight: root.lBody
                    }
                    Text {
                        visible: ((sessionStore.senatePublicAnnouncement || {}).enacted_proposals || []).length > 0
                        text: "\u2705 \u6700\u7ec8\u901a\u8fc7\uff1a" + root._announcementEnactedText()
                        color: "#2E7D32"
                        font.pixelSize: 12
                        font.bold: true
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        lineHeightMode: Text.FixedHeight
                        lineHeight: root.lBody
                    }
                    Text {
                        visible: root._consulDirectRows().length > 0
                        text: "\uD83C\uDFDB " + root._consulDirectLabel() + "\uff1a" + root._consulDirectText()
                              + "\uff1b" + root._consulDirectStatus()
                        color: "#9A2D0A"
                        font.pixelSize: 12
                        font.bold: true
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        lineHeightMode: Text.FixedHeight
                        lineHeight: root.lBody
                    }
                    Text {
                        visible: ((sessionStore.senatePublicAnnouncement || {}).direct_actions || []).length > 0
                        text: "\u26a1 \u76f4\u63a5\u751f\u6548\uff1a" + root._directActionText()
                        color: "#9A2D0A"
                        font.pixelSize: 12
                        font.bold: true
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        lineHeightMode: Text.FixedHeight
                        lineHeight: root.lBody
                    }
                    Text {
                        visible: (sessionStore.senateResult.governor_assignments || []).length > 0
                        text: "\u2022 \u884c\u7701\u603b\u7763\u4efb\u547d\uff1a" + root._governorSummary()
                        color: "#2C1E12"
                        font.pixelSize: 11
                        font.bold: true
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        lineHeightMode: Text.FixedHeight
                        lineHeight: root.lBody
                    }
                    Text {
                        visible: (sessionStore.senateResult.rebellion_commander_assignments || []).length > 0
                        text: "\u2022 \u8d77\u4e49\u6307\u6325\u5b98\u4efb\u547d\uff1a" + root._commanderSummary()
                        color: "#2C1E12"
                        font.pixelSize: 11
                        font.bold: true
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        lineHeightMode: Text.FixedHeight
                        lineHeight: root.lBody
                    }
                    Text {
                        visible: (sessionStore.senateResult.fleet_assignments || []).length > 0
                        text: "\u2022 \u8230\u961f\u6307\u6d3e\uff1a" + root._fleetSummary()
                        color: "#2C1E12"
                        font.pixelSize: 11
                        font.bold: true
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        lineHeightMode: Text.FixedHeight
                        lineHeight: root.lBody
                    }
                }
            }
        }
    }

    // #2 正文在 step 改变 / 新错误首次出现时复位到顶部（呈现初始化；非证据替代）。
    Connections {
        target: sessionStore
        function onSenateViewChanged() {
            if (sessionStore.senateCurrentStep !== root._lastAnnouncementStep) {
                root._lastAnnouncementStep = sessionStore.senateCurrentStep
                if (senateAnnouncementBody && senateAnnouncementBody.contentItem)
                    senateAnnouncementBody.contentItem.contentY = 0
            }
        }
    }



        // R8（SA §4.1 L-1/L-2，FC-UI-06，AC-06）：#3–5 三子环节框——占满 ContentSlot 余量
        // （rowW × Hrow，唯一算法见上），各自独立内滚，footer 固定不入滚动；min=preferred=max=Hrow，
        // **禁** fillHeight 自由竞争 / 禁由 step·内容·results 决定 / 无 360·460 clamp / 无外层兜底。
        RowLayout {
            id: threePanelRow
            objectName: "senateThreePanelRow"
            x: 14
            y: 14 + root.hNotice + 10
            width: root.rowW
            height: root.hRow
            spacing: 12

            SenateWorkPanel {
                title: "1  执政官提案 · 配置参数"
                fpNum: "1"
                active: sessionStore.senateCurrentStep === "proposal"
                completed: root.proposalStepDone
                Layout.fillWidth: true
                Layout.fillHeight: true

                ColumnLayout {
                    // R8（SA §4.1 L-3/L-7，FC-UI-06/07，AC-06/07）：Panel1 body 为单栏；topMargin 44 /
                    // 左右+下 10（内列高 = Hrow − 54）。footer 提交按钮固定在 body 外。
                    anchors.fill: parent
                    anchors.margins: 10
                    anchors.topMargin: 44
                    spacing: 7

                    // R8（SA §4.1 L-3/L-7，FC-UI-07）：**主 body ScrollView** 统一 scroll ownership——
                    // 包住 说明 + War Card Repeater + frozen direct 区 + nonWar/submitted 列；
                    // 旧只包 nonWar 的局部 ScrollView 已移除（War/frozen 随之纳入主 body）。
                    // 可读 viewport = Hrow − 95（= body 高 Hrow−54 − footer34 − spacing7）≥ 265。
                    ScrollView {
                        id: panel1BodyScroll
                        objectName: "senatePanel1BodyScroll"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentWidth: availableWidth
                        ColumnLayout {
                            width: parent.width
                            spacing: 7
                    Text {
                        text: sessionStore.senateCurrentStep === "proposal" ? "勾选执政官本轮提交元老院的法案。" : "已提交法案，等待元老院表决。"
                        color: theme.textSecondary
                        font.pixelSize: 11
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                    }

                    // R5（SA §5.1/§5.2 + Overlay E-01，DA-5）：统一 War Card 区——替换旧
                    // 「接管选区（:752-881）+ Continue 块（:883-961，含旧 :954 即时触发点）」
                    // 两个旧块。E-01 ：旧即时 Continue 触发点已被删除（退役彻底）。
                    // QML 只消费 war_cards 能力/DTO（defaults/allowed_modes/commander_candidates），
                    // 零生命周期推导（A-I18/D-SC02/D-SC15）。
                    Repeater {
                        model: sessionStore.senateCurrentStep === "proposal" ? (sessionStore.senateWarCards || []) : []
                        delegate: WarProposalCard {
                            Layout.fillWidth: true
                            card: modelData
                            draft: root.warDraftFor(modelData.war_id)
                            commanderCandidates: modelData.commander_candidates || []
                            peaceCapable: (modelData.allowed_modes || []).indexOf("peace") >= 0
                            editable: sessionStore.canCreateSenateProposal
                            // R7（SA §B.7，DA-R7 B3）：卡级错误注入改 cardErrorsFor()（逐卡 ack
                            // 后该卡返回空 → 仅清该卡红框）；编辑受影响卡走 onWarDraftEdited
                            // 逐卡 ack（**始终不声明有效**）。
                            cardErrors: root.cardErrorsFor(modelData.war_id)
                            onDraftEdited: function(warId, newDraft) { root.onWarDraftEdited(warId, newDraft) }
                        }
                    }

                    // R7（SA §A.5，DA-R7 B1）：冻结 Consul Direct Action 只读区（step 无关；bounded）。
                    // 数据源 = Store 顶层 DTO senateConsulDirectDecisions（非 PA）——Submit 成功后
                    // step 转 results、可编辑卡按 step 门卸载，本区仍可见（Results 步亦然）；
                    // 纯只读、无输入控件 ⇒ 永不可被再次 Submit（INV-A5）。高度 bounded，不无界撑高。
                    ColumnLayout {
                        id: frozenDirectSection
                        Layout.fillWidth: true
                        Layout.maximumHeight: 168
                        Layout.preferredHeight: Math.min(168, frozenDirectCol.implicitHeight + 34)
                        visible: root.frozenDirectRows().length > 0
                        spacing: 4
                        Text {
                            // R8（SA §5.2 C-04，FC-UI-01，PM P2-2）：**copy 门**——仅标题/文案随
                            // proposalStepDone 切换；frozen 区可见性谓词（上方 visible）逐字不变。
                            text: root.proposalStepDone
                                  ? "🏛 执政官决定（只读 · 待 Senate→Combat 边界执行）"
                                  : "🏛 战争法案配置（只读）"
                            color: theme.textSecondary
                            font.pixelSize: 11
                            font.bold: true
                            Layout.fillWidth: true
                            wrapMode: Text.Wrap
                        }
                        ScrollView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            contentWidth: availableWidth
                            ColumnLayout {
                                id: frozenDirectCol
                                width: parent.width
                                spacing: 4
                                Repeater {
                                    model: root.frozenDirectRows()
                                    delegate: Rectangle {
                                        objectName: "senateFrozenDirectRow"
                                        Layout.fillWidth: true
                                        implicitHeight: frozenRowCol.implicitHeight + 10
                                        radius: 4
                                        color: "#FFF6E6"
                                        border.color: "#9A2D0A"
                                        border.width: 1
                                        ColumnLayout {
                                            id: frozenRowCol
                                            anchors.fill: parent
                                            anchors.margins: 6
                                            spacing: 2
                                            Text {
                                                // R8（SA §5.2 C-04）：人话决策摘要（禁透传 producer 技术串）。
                                                text: "⚡ " + root.consulDecisionSummary(modelData)
                                                color: "#9A2D0A"
                                                font.pixelSize: 12
                                                font.bold: true
                                                Layout.fillWidth: true
                                                wrapMode: Text.Wrap
                                                elide: Text.ElideNone
                                            }
                                            Text {
                                                text: root.frozenDirectIdentityText(modelData)
                                                color: "#2C1E12"
                                                font.pixelSize: 11
                                                Layout.fillWidth: true
                                                wrapMode: Text.Wrap
                                                elide: Text.ElideNone
                                            }
                                            Text {
                                                // R8（SA §5.2 C-05/C-06，FC-UI-03）：状态人话（C-06 不透传 receipt 技术串）。
                                                text: "状态：" + root.consulExecutionStatus(modelData)
                                                color: modelData.execution === "executed"
                                                       ? theme.statusSuccess : theme.textSecondary
                                                font.pixelSize: 11
                                                Layout.fillWidth: true
                                                wrapMode: Text.Wrap
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    // R8（SA §4.1 L-3）：nonWar/submitted 列并入 Panel1 主 body（旧只包 nonWar 的局部 ScrollView 移除）。
                    ColumnLayout {
                        width: parent.width
                        spacing: 6
                        Repeater {
                            model: sessionStore.senateCurrentStep === "proposal" ? root.nonWarProposalOptions() : (sessionStore.senateSubmittedProposals || [])
                                delegate: Rectangle {
                                    id: billCard
                                    Layout.fillWidth: true
                                    property bool isProposal: sessionStore.senateCurrentStep === "proposal"
                                    property bool expanded: isProposal && root.expandedBillKeys.indexOf(modelData.key) >= 0
                                    property string billKey: (modelData && modelData.key) ? modelData.key : ""
                                    property real defaultBudget: (modelData.budget_range) ? modelData.budget_range.default : 0
                                    Layout.preferredHeight: isProposal
                                        ? (expanded ? cardColumn.implicitHeight + 12 : headerRow.implicitHeight + 12)
                                        : (cardColumn.implicitHeight + 12)
                                    Layout.minimumHeight: 32
                                    radius: 4
                                    color: "#FFF6E6"
                                    border.color: "#E0B56C"
                                    border.width: 1

                                    ColumnLayout {
                                        id: cardColumn
                                        anchors.fill: parent
                                        anchors.margins: 6
                                        spacing: 4

                                        RowLayout {
                                            id: headerRow
                                            Layout.fillWidth: true
                                            spacing: 6

                                            CheckBox {
                                                id: proposalSelectCheck
                                                visible: isProposal
                                                enabled: sessionStore.canCreateSenateProposal
                                                checked: root.hasSelectedProposal(modelData.key)
                                                onToggled: root.setProposalSelected(modelData.key, checked)
                                                // WP-J Group C G7 Test R4 Delta（delta v1.9 / FC-C31）：
                                                // **移除** R3 方案甲（FC-C28）自绘框 `indicator` ⇒ 回落**平台默认样式**
                                                // 指示器（系统勾选框，勾选 = 系统 ☑）。状态机
                                                // （visible/enabled/checked/onToggled）逐字不变；不动 ① 结果标记 Text
                                                // （紧随其后，硬编码绿 ✓，不受本次回退影响）。
                                            }

                                            Text {
                                                visible: !isProposal
                                                text: "\u2713"
                                                color: theme.statusSuccess
                                                font.pixelSize: 13
                                                font.bold: true
                                            }

                                            Text {
                                                text: root.proposalTitle(modelData)
                                                color: "#2C1E12"
                                                font.pixelSize: 12
                                                font.bold: true
                                                Layout.fillWidth: true
                                                wrapMode: Text.Wrap
                                                elide: Text.ElideNone
                                            }

                                            Text {
                                                visible: isProposal
                                                text: expanded ? "\u25BC" : "\u25B6"
                                                color: "#766652"
                                                font.pixelSize: 10
                                                horizontalAlignment: Text.AlignHCenter
                                                verticalAlignment: Text.AlignVCenter
                                            }

                                            MouseArea {
                                                visible: isProposal
                                                width: 18
                                                height: 20
                                                cursorShape: Qt.PointingHandCursor
                                                // AU-R1-03a：非执政官 viewer 三角禁用（参数面板不可展开）
                                                enabled: sessionStore.canCreateSenateProposal
                                                onClicked: root.toggleBillExpanded(billKey)
                                            }
                                        }

                                        Text {
                                            visible: !isProposal && root.proposalDetail(modelData).length > 0
                                            text: root.proposalDetail(modelData)
                                            color: "#766652"
                                            font.pixelSize: 10
                                            Layout.fillWidth: true
                                            wrapMode: Text.Wrap
                                            elide: Text.ElideNone
                                        }

                                        ColumnLayout {
                                            id: billBody
                                            visible: isProposal && expanded
                                            Layout.fillWidth: true
                                            spacing: 6

                                            Text {
                                                visible: root.proposalDetail(modelData).length > 0
                                                text: root.proposalDetail(modelData)
                                                color: "#766652"
                                                font.pixelSize: 10
                                                Layout.fillWidth: true
                                                wrapMode: Text.Wrap
                                            }

                                            // FC-01 宣战军团数量下拉（authoritative：legion_options = config 派生 [min..可用池]）
                                            RowLayout {
                                                visible: modelData.type === "war"
                                                Layout.fillWidth: true
                                                spacing: 6
                                                Text { text: "征召军团"; color: "#2C1E12"; font.pixelSize: 11; Layout.preferredWidth: 60 }
                                                ComboBox {
                                                    id: legionCombo
                                                    Layout.fillWidth: true
                                                    // AU-R1-03a：非执政官 viewer 不可编辑（authority 门控）
                                                    enabled: sessionStore.canCreateSenateProposal && ((modelData.legion_options && modelData.legion_options.allowed && modelData.legion_options.allowed.length > 0) ? true : false)
                                                    model: (modelData.legion_options && modelData.legion_options.allowed) ? modelData.legion_options.allowed : []
                                                    currentIndex: root.legionIndexFor(root.billParamValue(billKey, "legions", (modelData.params && modelData.params.legions) || 0), (modelData.legion_options && modelData.legion_options.allowed) || [])
                                                    onActivated: root.setBillParam(billKey, "legions", model[currentIndex])
                                                }
                                                Text {
                                                    visible: !(modelData.legion_options && modelData.legion_options.allowed)
                                                    text: "值域待定义"
                                                    color: "#9A2D0A"
                                                    font.pixelSize: 11
                                                }
                                            }

                                            // FC-03/FC-04 预算 slider（authoritative：budget_range = config 派生 per-contract 值域）
                                            ColumnLayout {
                                                visible: modelData.type === "budget"
                                                Layout.fillWidth: true
                                                spacing: 2
                                                RowLayout {
                                                    Layout.fillWidth: true
                                                    Text { text: "预算金额"; color: "#2C1E12"; font.pixelSize: 11; Layout.preferredWidth: 60 }
                                                    Text {
                                                        text: Math.round(budgetSlider.value) + " T"
                                                        color: "#9A2D0A"
                                                        font.pixelSize: 11
                                                        font.bold: true
                                                    }
                                                }
                                                Slider {
                                                    id: budgetSlider
                                                    Layout.fillWidth: true
                                                    // AU-R1-03a：非执政官 viewer 不可编辑（authority 门控）
                                                    enabled: sessionStore.canCreateSenateProposal && (modelData.budget_range ? true : false)
                                                    from: (modelData.budget_range) ? modelData.budget_range.min : 0
                                                    to: (modelData.budget_range) ? modelData.budget_range.max : 0
                                                    stepSize: (modelData.budget_range) ? modelData.budget_range.step : 1
                                                    value: (modelData.params && modelData.params.modified_budget !== undefined) ? modelData.params.modified_budget : defaultBudget
                                                    onValueChanged: root.setBillParam(billKey, "modified_budget", Math.round(value))
                                                }
                                                Text {
                                                    visible: !modelData.budget_range
                                                    text: "值域待定义"
                                                    color: "#9A2D0A"
                                                    font.pixelSize: 11
                                                }
                                            }

                                            // FC-05/FC-06 卖地/分地 amount_C slider（AU-7：authoritative = params.amount_C int 主输入；
                                            // percent 仅派生展示 = amount_C / root public_land，禁独立编辑）
                                            ColumnLayout {
                                                visible: modelData.type === "land"
                                                Layout.fillWidth: true
                                                spacing: 2
                                                RowLayout {
                                                    Layout.fillWidth: true
                                                    Text { text: "土地数量"; color: "#2C1E12"; font.pixelSize: 11; Layout.preferredWidth: 60 }
                                                    Text {
                                                        text: Math.round(landSlider.value) + " C（约 " + Math.round((landSlider.value / (modelData.public_land || 1)) * 100) + "%）"
                                                        color: "#9A2D0A"
                                                        font.pixelSize: 11
                                                        font.bold: true
                                                    }
                                                }
                                                Slider {
                                                    id: landSlider
                                                    Layout.fillWidth: true
                                                    // AU-R1-03a：非执政官 viewer 不可编辑（authority 门控）；
                                                    // AU-R1-06c：public_land 缺失 → 回退 1（null-safe）
                                                    enabled: sessionStore.canCreateSenateProposal
                                                    from: 1
                                                    to: modelData.public_land || 1
                                                    stepSize: 1
                                                    value: (modelData.params && modelData.params.amount_C !== undefined) ? modelData.params.amount_C : 1
                                                    onValueChanged: root.setBillParam(billKey, "amount_C", Math.round(value))
                                                }
                                            }

                                            // FC-14 + FC-09 + FC-13: governor 候选人只读展示 + 合格条件提示（G6 Narrow）
                                            ColumnLayout {
                                                visible: modelData.type === "governor"
                                                Layout.fillWidth: true
                                                spacing: 4

                                                Text {
                                                    text: "合格条件：元老院成员，曾任大法官以上官职"
                                                    color: "#766652"
                                                    font.pixelSize: 10
                                                    Layout.fillWidth: true
                                                    wrapMode: Text.Wrap
                                                }

                                                Text {
                                                    visible: root.governorCandidateNameLine(modelData).length > 0
                                                    text: root.governorCandidateNameLine(modelData)
                                                    textFormat: Text.RichText
                                                    color: "#2C1E12"
                                                    font.pixelSize: 11
                                                    font.bold: true
                                                    Layout.fillWidth: true
                                                    wrapMode: Text.Wrap
                                                }

                                                Text {
                                                    visible: root.governorCandidateAttrsLine(modelData).length > 0
                                                    text: root.governorCandidateAttrsLine(modelData)
                                                    color: "#766652"
                                                    font.pixelSize: 10
                                                    Layout.fillWidth: true
                                                    wrapMode: Text.Wrap
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        radius: 4
                        // WP-D AU-3/AU-1：移除 selectedProposalKeys.length>0（空批合法）；
                        // AI 分支（canTriggerAIProposer）按钮同样可点（frozen §11 Scenario B，见偏离 D-7）
                        enabled: (sessionStore.canCreateSenateProposal || sessionStore.canTriggerAIProposer) && !root.hasZeroValueLandSelection()
                        opacity: enabled ? 1.0 : 0.45
                        gradient: Gradient { GradientStop { position: 0.0; color: "#D9AA52" } GradientStop { position: 1.0; color: "#BC7B28" } }
                        Text {
                            anchors.centerIn: parent
                            text: root.proposalStepDone ? "\u2190 \u6cd5\u6848\u5df2\u63d0\u4ea4"
                                : (sessionStore.canTriggerAIProposer ? "AI \u6267\u653f\u5b98\u81ea\u52a8\u63d0\u6848 \u2192"
                                   : (root.selectedProposalKeys.length === 0 ? "\u672c\u4f1a\u671f\u4e0d\u63d0\u4ea4\u6cd5\u6848 \u2192 \u7ed3\u675f\u63d0\u6848" : "\u63d0\u4ea4\u9009\u4e2d\u6cd5\u6848 \u2192 \u79fb\u4ea4\u8868\u51b3"))
                            color: "#2C1E12"; font.pixelSize: 12; font.bold: true
                        }
                        MouseArea { anchors.fill: parent; enabled: parent.enabled; onClicked: sessionStore.doSubmitSenateProposals(root.selectedProposals()) }
                    }
                }
            }

            SenateWorkPanel {
                title: "2  元老院表决"
                fpNum: "2"
                active: sessionStore.senateCurrentStep === "senate_vote"
                completed: sessionStore.senateCurrentStep === "tribune_veto" || sessionStore.senateCurrentStep === "results"
                Layout.fillWidth: true
                Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    anchors.topMargin: 44
                    spacing: 7
                    // R8（SA §4.1 L-3）：说明文本移入 body 内滚内容（计入 contentHeight）；footer 固定 body 外。
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentWidth: availableWidth
                        ColumnLayout {
                            width: parent.width
                            spacing: 6
                            Text { text: "勾选同意（多选），未勾选 = 否决。所有派系执行完毕后进入否决环节。"; color: theme.textSecondary; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
                            Repeater {
                                model: sessionStore.senateSubmittedProposals || []
                                delegate: Rectangle {
                                    // WP-J Group C Pre-G6 VisualDelta（delta v1.3 / FC-C18）：本面板每行套用与
                                    // ③ 保民官否决行（L1829–1836）/ ① 执政官提案卡（L1484–1498）逐字一致的
                                    // 带边框卡；行高内容驱动；整行仍可点选/勾选；单一 scroll owner 不变。
                                    id: voteRowCard
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: voteRowColumn.implicitHeight + 16
                                    Layout.minimumHeight: 32
                                    radius: 4
                                    color: "#FFF6E6"
                                    border.color: "#E0B56C"
                                    border.width: 1
                                    ColumnLayout {
                                        id: voteRowColumn
                                        anchors.fill: parent
                                        anchors.margins: 8
                                        spacing: 2
                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 6
                                            // WP-J Group C G7 Test R4 Delta（delta v1.9 / FC-C31 + FC-C32）：
                                            // ② 非输入态（step ∈ {tribune_veto, results}）行**最左端** = **无框**结果字形，
                                            // 由**行内独立 `Text`** 承载（**移出**已撤的自绘 `indicator`）。
                                            // 谓词 = ②-local `senateResultMark()`（FC-C35；`rejected→✗`，`passed/vetoed→✓`，
                                            // `results` 步源=`item.result`；`tribune_veto` 步 `.result` 缺失 → `voteResultFor()`
                                            // 回退 → 表决完成即显；无表决数据→空白）。
                                            Text {
                                                visible: sessionStore.senateCurrentStep !== "senate_vote"
                                                text: root.senateResultMark(modelData)
                                                color: root.senateResultMarkColor(modelData)
                                                font.pixelSize: 13
                                                font.bold: true
                                            }
                                            // WP-J Group C G7 Test R5 Delta（delta v2.0 / FC-C36）：② 勾选框
                                            // **非输入态隐藏**（新增 `visible` 门）⇒ `tribune_veto` / `results`
                                            // （及 `proposal` 锁态）**不渲染勾选框（含平台默认指示器）**。
                                            // WP-J Group C G7 Test R7 Delta（delta v2.3 / FC-C41）：② 勾选框由常量
                                            // `checked:true` 改为**真实可切换选择态**——`checked` 绑定 ② 专属选择集
                                            // （默认未勾选 = 否决），新增 `onToggled` 写回选择集。平台默认指示器守恒
                                            // （**禁**覆写 `indicator`；`FC-C31`）。**仅 ②**。
                                            CheckBox {
                                                id: proposalVoteCheck
                                                visible: sessionStore.senateCurrentStep === "senate_vote"
                                                enabled: sessionStore.senateCurrentStep === "senate_vote"
                                                checked: root.hasSelectedSenateVote(Number(modelData.id))
                                                onToggled: root.setSenateVoteSelected(Number(modelData.id), checked)
                                                font.pixelSize: 12
                                                // WP-J Group C G7 Test R4 Delta（FC-C31）：**移除** FC-C25/FC-C28 自绘
                                                // `indicator`（输入态 USS 方框 + 结果态无框字形）⇒ 回落**平台默认样式**
                                                // 指示器；结果字形已**移出**为行内独立 `Text`（见上）。`enabled` / 状态机 /
                                                // 数据源逐字不变；`checked` 由常量改为绑定 ② 专属选择集（FC-C41）。
                                            }
                                            // WP-J Group C G7 Test R5 Delta（delta v2.0 / FC-C36，**FC-C15–C17 修订**）：
                                            // ② 身份文本由 `CheckBox.contentItem` **移出**为行内**同级 `Text`**（与 ①③ 同构）；
                                            // **保留 wrap 语义**（`wrapMode: Text.Wrap` + `elide: Text.ElideNone`）。
                                            // 非输入态 = [结果字形][身份文本]；输入态（senate_vote） = [勾选框][身份文本]。
                                            // **FC-C22 退役**：不再使用 `senateVoteIdentityGap` / contentItem 净缩进。
                                            Text {
                                                text: (modelData.label || modelData.type) + root.voteParamDescription(modelData)
                                                color: "#2C1E12"
                                                font.pixelSize: 12
                                                Layout.fillWidth: true
                                                wrapMode: Text.Wrap
                                                elide: Text.ElideNone
                                            }
                                        }
                                        // WP-F R2-01（F-01A）：投票完成后（voted_all → 中间投影已产出）
                                        // Stage 2 即显示权威通过/未通过 + 支持率（纯展示除法，禁 QML 阈值判定）
                                        Text {
                                            visible: root.voteResultFor(modelData.id) !== null
                                            text: root.supportRateText(root.voteResultFor(modelData.id))
                                            color: "#766652"
                                            font.pixelSize: 10
                                            Layout.fillWidth: true
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        ActionButton {
                            anchors.fill: parent
                            text: root.senateVoteButtonText()
                            enabled: sessionStore.canSubmitSenateVote
                            onTriggered: sessionStore.doSubmitSenateVotes(root.selectedSenateVoteIds)
                        }
                    }
                }
                LockedOverlay { anchors.fill: parent; anchors.margins: 10; anchors.topMargin: 44; visible: sessionStore.senateCurrentStep === "proposal"; text: "⏳ 等待执政官提交法案" }
            }

            SenateWorkPanel {
                title: "3  保民官否决"
                fpNum: "3"
                active: sessionStore.senateCurrentStep === "tribune_veto"
                completed: sessionStore.senateCurrentStep === "results"
                Layout.fillWidth: true
                Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    anchors.topMargin: 44
                    spacing: 7
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentWidth: availableWidth
                        ColumnLayout {
                            width: parent.width
                            spacing: 6
                            Text { text: "\u901a\u8fc7\u6cd5\u6848\u5217\u8868\u3002\u4fdd\u6c11\u5b98\u52fe\u9009\u5426\u51b3\uff08\u591a\u9009\uff09\uff0c\u672a\u52fe\u9009 = \u540c\u610f\u3002"; color: theme.textSecondary; font.pixelSize: 11; Layout.fillWidth: true; wrapMode: Text.Wrap }
                            Repeater {
                                model: root.stageThreeRows()
                                delegate: Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: stageThreeRow.implicitHeight + 16
                                    Layout.minimumHeight: 40
                                    radius: 4
                                    color: "#FFF6E6"
                                    border.color: "#E0B56C"
                                    border.width: 1
                                    RowLayout {
                                        id: stageThreeRow
                                        anchors.fill: parent
                                        anchors.margins: 8
                                        spacing: 6
                                        Text {
                                            visible: sessionStore.senateCurrentStep === "results"
                                            text: root.resultMark(modelData)
                                            color: root.resultMarkColor(modelData)
                                            font.pixelSize: 13
                                            font.bold: true
                                        }
                                        CheckBox {
                                            id: vetoCheck
                                            visible: sessionStore.senateCurrentStep !== "results"
                                            enabled: sessionStore.senateCurrentStep === "tribune_veto" && sessionStore.canManuallySelectSenateVeto
                                            checked: root.hasSelectedVeto(Number(modelData.id))
                                            onToggled: root.setVetoSelected(Number(modelData.id), checked)
                                            // 历史：WP-J Group C G7-Delta（FC-C23，取代 FC-C20）/ G7 Test 2（FC-C26）/
                                            // G7 Test R3（FC-C28/FC-C29）—— 现由本 R4 Delta（FC-C31）**回退**。
                                            // WP-J Group C G7 Test R4 Delta（delta v1.9 / FC-C31）：**移除**自绘框/自绘叉
                                            // `indicator`（方案甲已放弃）⇒ 回落**平台默认样式**指示器（勾选 = 系统 ☑；
                                            // Owner 明示可接受，**不再要求 ⮽**）。状态机
                                            // （checked/onToggled/enabled/hasSelectedVeto/setVetoSelected）逐字不变；
                                            // results 态红 ✗ 由既有**独立** `resultMark()` Text 承载（不动）。
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 1
                                            Text {
                                                text: root.proposalTitle(modelData)
                                                color: "#2C1E12"
                                                font.pixelSize: 12
                                                font.bold: true
                                                Layout.fillWidth: true
                                                wrapMode: Text.Wrap
                                                elide: Text.ElideNone
                                            }
                                            Text {
                                                visible: root.proposalDetail(modelData).length > 0
                                                text: root.proposalDetail(modelData)
                                                color: "#766652"
                                                font.pixelSize: 10
                                                Layout.fillWidth: true
                                                wrapMode: Text.Wrap
                                                elide: Text.ElideNone
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        ActionButton {
                            anchors.fill: parent
                            text: root.tribuneActionText()
                            enabled: sessionStore.canSubmitSenateVeto
                            onTriggered: sessionStore.doSubmitSenateVetoes(root.selectedVetoProposalIds)
                        }
                    }
                }
                LockedOverlay { anchors.fill: parent; anchors.margins: 10; anchors.topMargin: 44; visible: sessionStore.senateCurrentStep !== "tribune_veto" && sessionStore.senateCurrentStep !== "results"; text: "⏳ 等待元老院表决完成" }
            }
        }

    component StageStep: Row {
        property bool done: false
        property bool active: false
        property string label: ""
        spacing: 5
        Layout.alignment: Qt.AlignVCenter
        Rectangle {
            width: 20
            height: 20
            radius: 10
            color: done ? theme.statusSuccess : (active ? "#E8B84B" : "#E8D5C4")
            Text { anchors.centerIn: parent; text: done ? "✓" : label.substring(0, 1); color: done ? "white" : "#2C1E12"; font.pixelSize: 11; font.bold: true }
        }
        Text { text: label.replace(/^[0-9] /, ""); color: active || done ? theme.textPrimary : theme.textMuted; font.pixelSize: 12; font.bold: active; anchors.verticalCenter: parent.verticalCenter }
    }

    component StepArrow: Text { text: "→"; color: "#B8A080"; font.pixelSize: 12; Layout.alignment: Qt.AlignVCenter }

    component SenateWorkPanel: Rectangle {
        property string title: ""
        property string fpNum: ""
        property bool active: false
        property bool completed: false
        color: "#FFF7E9"
        border.color: active ? "#9A2D0A" : "#D9AF63"
        border.width: 1
        radius: 6
        clip: true
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 36
            color: active || completed ? "#8F2506" : "#B98A76"
            Rectangle {
                anchors.left: parent.left
                anchors.leftMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                width: 20
                height: 20
                radius: 10
                color: "#D9AA52"
                visible: fpNum.length > 0
                Text { anchors.centerIn: parent; text: fpNum; color: "#8F2506"; font.pixelSize: 11; font.bold: true }
            }
            Text { anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left; anchors.leftMargin: fpNum.length > 0 ? 38 : 10; text: title; color: "white"; font.pixelSize: 13; font.bold: true }
        }
    }

    component ActionButton: Rectangle {
        property string text: ""
        signal triggered()
        Layout.fillWidth: true
        Layout.preferredHeight: 26
        radius: 4
        opacity: enabled ? 1.0 : 0.45
        gradient: Gradient { GradientStop { position: 0.0; color: enabled ? "#D9AA52" : "#D8B16C" } GradientStop { position: 1.0; color: enabled ? "#BC7B28" : "#D8B16C" } }
        Text { anchors.centerIn: parent; text: parent.text; color: "#2C1E12"; font.pixelSize: 12; font.bold: true }
        MouseArea { anchors.fill: parent; enabled: parent.enabled; onClicked: parent.triggered() }
    }

    component ActionStub: Rectangle {
        property string text: ""
        Layout.fillWidth: true
        Layout.preferredHeight: 26
        radius: 4
        color: "#D8B16C"
        opacity: 0.65
        Text { anchors.centerIn: parent; text: parent.text; color: "#60411E"; font.pixelSize: 12; font.bold: true }
    }

    component LockedOverlay: Rectangle {
        property string text: ""
        color: "#C7A79899"
        radius: 6
        z: 20
        Text { anchors.centerIn: parent; text: parent.text; color: "white"; font.pixelSize: 12; font.bold: true }
    }
}
