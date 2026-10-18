import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

/*!
 * PlayerHandoffOverlay — REUSED (Owner S-2 / R5 §5). One overlay only; no second
 * overlay, no new card geometry.
 *
 * Two modes share the inherited layout:
 *   * legacy informational handoff (EOR20261011-01): show(nextPlayerId), the
 *     existing primary button copy 确认交接 and the raw ``nextPlayerId`` property
 *     are preserved so the closed Query acceptance chain is unchanged;
 *   * S-B masked handoff authority (G2/R2): an OPAQUE full-window cover with a
 *     full pointer/touch/wheel/key swallow, pending copy showing the safe FACTION
 *     NAME ONLY (「下一位：<faction>」 — never a raw player id / player name /
 *     initials / "PL"), a neutral replaceable avatar/emblem slot, and the primary
 *     activation button 「接管」.
 *
 * The cover is 100% opaque (alpha=1); no translucent holes.
 */
Rectangle {
    id: root
    objectName: "playerHandoffOverlay"
    // Fully opaque neutral cover (Owner S-2 / R5 §5 — never #CC000000).
    color: "#FF202020"
    visible: false
    focus: visible
    activeFocusOnTab: visible

    // ---- legacy (EOR20261011-01) informational state ----------------------
    property string nextPlayerId: ""

    // ---- S-B masked handoff authority state -------------------------------
    property bool maskedMode: false
    property string pendingFactionName: ""
    property bool busy: false
    property bool failureVisible: false
    property string failureKind: ""
    property bool canRetry: false
    property bool canExit: false
    // W2a: set only by the neutral startup provider ("single_human"). Empty
    // for every 3H / legacy path, which is byte-semantics unchanged.
    property string startupMode: ""
    // One-shot carrier used by showMaskedStartup() so the historical
    // showMaskedPending(faction) meta signature stays 1-argument compatible.
    property string pendingStartupMode: ""
    readonly property bool startupIntro: maskedMode && startupMode === "single_human"
    // SD-R02 (§1.1.R): the ONE safe, exclusive failure-origin routing token
    // ("activation" | "continuation") carried by the barrier-witness provider copy
    // call. It is a routing enum only — never player/domain data, never copy.
    property string failureRoute: ""

    // Structural mutual exclusion: a SINGLE exclusive route value drives both
    // booleans, so the two failure actions can never co-appear.
    readonly property bool activationRetryEligible: maskedMode && failureVisible
        && failureRoute === "activation"
    readonly property bool continuationRecoverEligible: maskedMode && failureVisible
        && failureRoute === "continuation"

    // Accessible description for the masked modal (safe copy only; never a
    // player name / handle / raw player_* id / epoch / token).
    Accessible.role: Accessible.Dialog
    Accessible.name: root.dialogAccessibleName
    // Readable a11y projection (the attached property itself is not a normal
    // QML property). 1H startup copy is faction-free and locale-bound.
    readonly property string dialogAccessibleName: startupIntro
        ? GuiText.startupDialogA11y
        : "玩家交接"

    function show(playerId) {
        maskedMode = false
        startupMode = ""
        nextPlayerId = playerId
        failureVisible = false
        failureRoute = ""
        busy = false
        canExit = false
        visible = true
        forceActiveFocus()
    }
    function showMaskedBusy() {
        maskedMode = true
        startupMode = ""
        pendingFactionName = ""
        failureVisible = false
        failureRoute = ""
        busy = true
        canExit = false
        visible = true
        forceActiveFocus()
    }
    function showMaskedPending(factionName) {
        maskedMode = true
        startupMode = pendingStartupMode || ""
        pendingStartupMode = ""
        pendingFactionName = factionName || ""
        failureVisible = false
        failureRoute = ""
        busy = false
        canExit = true
        visible = true
        forceActiveFocus()
    }
    // W2a entry used ONLY by the neutral startup provider. Kept separate so
    // every existing 1-argument showMaskedPending(faction) call still binds.
    function showMaskedStartup(factionName, mode) {
        pendingStartupMode = mode || ""
        showMaskedPending(factionName)
    }
    // SD-R02 §1.1.R: the failure surface now receives the safe, exclusive
    // failure-origin token (route) from the widened copy path
    // (GuiApp.show_failure -> GameShell.showHandoffFailure). Copy-only.
    function showMaskedFailure(kind, route) {
        maskedMode = true
        startupMode = ""
        // SB-V06: a stale pending target label must NOT survive the failure surface.
        pendingFactionName = ""
        failureVisible = true
        failureKind = kind || ""
        failureRoute = route || ""
        busy = false
        canExit = true
        visible = true
        forceActiveFocus()
    }
    function hideOverlay() {
        visible = false
        canExit = false
    }
    // Bounded focus trap (R5 §4 / SB-V06): Tab / Shift-Tab cycle ONLY across the
    // visible primary / retry / exit controls; traversal can never reach any
    // underlying control while masked.
    function _focusableButtons() {
        var out = []
        if (primaryButton.visible && primaryButton.enabled) out.push(primaryButton)
        if (retryButton.visible && retryButton.enabled) out.push(retryButton)
        if (recoverButton.visible && recoverButton.enabled) out.push(recoverButton)
        if (exitButton.visible && exitButton.enabled) out.push(exitButton)
        return out
    }
    // SD-R02 §1.1.R: ONE shared action path for the bounded continuation recovery.
    // Both the pointer onClicked and the explicit local Keys handlers call it, so
    // one user gesture = exactly one dispatch. Guarded by visible && enabled &&
    // !busy; the single dispatch point is chosen on PRESS (no dispatch on release).
    function _activateRecovery() {
        if (!recoverButton.visible || !recoverButton.enabled || root.busy) return
        if (sessionStore && sessionStore.doRecoverContinuation
                && typeof sessionStore.doRecoverContinuation === "function") {
            sessionStore.doRecoverContinuation()
        }
    }
    function _cycleFocus(dir) {
        var btns = _focusableButtons()
        if (btns.length === 0) return
        var cur = -1
        for (var i = 0; i < btns.length; i++) {
            if (btns[i].activeFocus) { cur = i; break }
        }
        var next
        if (cur === -1) next = dir > 0 ? 0 : btns.length - 1
        else next = (cur + dir + btns.length) % btns.length
        btns[next].forceActiveFocus()
    }
    // Bounded safe-exit request (MASKED_PENDING / MASKED_FAILURE only; the Store
    // revalidates). Never used to bypass activation.
    function requestExit() {
        if (sessionStore && sessionStore.requestHandoffExit
                && typeof sessionStore.requestHandoffExit === "function") {
            sessionStore.requestHandoffExit()
        } else {
            Qt.quit()
        }
    }

    // ---- modal focus trap (R5 §4) -----------------------------------------
    // Entering suspension steals focus; Tab/Shift-Tab are consumed so traversal
    // cannot reach any underlying control while masked. (Rectangle is not a
    // FocusScope, so a child FocusScope owns keyboard focus.)
    FocusScope {
        id: focusTrap
        objectName: "handoffFocusTrap"
        anchors.fill: parent
        focus: root.visible
        activeFocusOnTab: root.visible
        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
                var back = (event.key === Qt.Key_Backtab)
                        || ((event.modifiers & Qt.ShiftModifier) !== 0)
                root._cycleFocus(back ? -1 : 1)
                event.accepted = true
                return
            }
            event.accepted = true
        }
        Keys.onReleased: function(event) { event.accepted = true }

        // ---- full-window pointer/touch/wheel swallow (R2 / R5 §4) ---------
        // Consumes press/release/double-click/wheel/hover so no event reaches the
        // underlying stage/query handlers. The primary button sits ABOVE this layer.
        MouseArea {
            objectName: "handoffInputBarrier"
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.AllButtons
            onWheel: function(wheel) { wheel.accepted = true }
            onPressed: function(mouse) { mouse.accepted = true }
            onReleased: function(mouse) { mouse.accepted = true }
            onClicked: function(mouse) { mouse.accepted = true }
            onDoubleClicked: function(mouse) { mouse.accepted = true }
            onPositionChanged: function(mouse) { mouse.accepted = true }
        }

        ColumnLayout {
            anchors.centerIn: parent
            width: 400
            spacing: 24

            Text {
                objectName: "handoffDialogTitle"
                Layout.alignment: Qt.AlignHCenter
                visible: !root.startupIntro
                text: "🔒 玩家交接"
                color: theme.textPrimary
                font.pixelSize: 24
                font.family: theme.fontTitle
                font.bold: true
            }

            // Neutral, non-interactive, replaceable avatar/emblem slot (Owner S-2 /
            // R5 §5). No ID-derived initials, no "PL", no real assets/dependencies
            // this round; a future approved avatar/emblem may replace the neutral
            // geometric placeholder without changing the layout.
            Rectangle {
                objectName: "handoffAvatarSlot"
                Layout.alignment: Qt.AlignHCenter
                width: 80; height: 80
                radius: 40
                color: theme.bgSurface2
                border.color: theme.panelBorder
                border.width: 1
            }

            // ---- W2a: neutral 1H+AI startup intro -----------------------------
            // Owner copy (2026-10-18 21:54): title + description + three real
            // state-backed lines. Every string resolves through the GUI catalog.
            ColumnLayout {
                objectName: "startupIntroBlock"
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 400
                spacing: 8
                visible: root.startupIntro && !root.busy && !root.failureVisible

                Text {
                    objectName: "startupIntroTitle"
                    Layout.alignment: Qt.AlignHCenter
                    text: GuiText.startupIntroTitle
                    color: theme.textPrimary
                    font.pixelSize: 20
                    font.family: theme.fontTitle
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    Accessible.name: text
                }

                Text {
                    objectName: "startupIntroDescription"
                    Layout.fillWidth: true
                    text: GuiText.startupIntroDescription
                    color: theme.textSecondary
                    font.pixelSize: 14
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    Accessible.name: text
                }

                Text {
                    objectName: "startupIntroYear"
                    Layout.fillWidth: true
                    text: sessionStore
                          ? GuiText.startupYearLine(sessionStore.startupYearText)
                          : "—"
                    color: theme.textSecondary
                    font.pixelSize: 14
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    Accessible.name: text
                }

                Text {
                    objectName: "startupIntroTreasury"
                    Layout.fillWidth: true
                    text: sessionStore
                          ? GuiText.startupTreasuryLine(sessionStore.startupTreasuryText)
                          : "—"
                    color: theme.textSecondary
                    font.pixelSize: 14
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    Accessible.name: text
                }

                Text {
                    objectName: "startupIntroTerritory"
                    Layout.fillWidth: true
                    text: sessionStore
                          ? GuiText.startupTerritoryLine(
                                sessionStore.startupTerritoryText,
                                sessionStore.startupTerritorySuffix)
                          : "—"
                    color: theme.textSecondary
                    font.pixelSize: 14
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    Accessible.name: text
                }
            }

            // ---- masked pending: safe FACTION NAME ONLY -----------------------
            Text {
                objectName: "handoffPendingLabel"
                Layout.alignment: Qt.AlignHCenter
                visible: root.maskedMode && !root.startupIntro
                    && !root.busy && !root.failureVisible
                text: "下一位：" + root.pendingFactionName
                color: theme.textPrimary
                font.pixelSize: 16
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                Accessible.name: text
            }

            Text {
                objectName: "handoffPendingInstruction"
                Layout.alignment: Qt.AlignHCenter
                visible: root.maskedMode && !root.startupIntro
                    && !root.busy && !root.failureVisible
                text: "请该派系玩家点击“接管”。"
                color: theme.textSecondary
                font.pixelSize: 14
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }

            // ---- legacy informational copy ------------------------------------
            Text {
                objectName: "handoffLegacyLabel"
                Layout.alignment: Qt.AlignHCenter
                visible: !root.maskedMode
                text: "当前玩家操作已完成。\n\n下一玩家：" + root.nextPlayerId
                color: theme.textSecondary
                font.pixelSize: 14
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }

            // ---- masked busy / failure ----------------------------------------
            Text {
                objectName: "handoffBusyLabel"
                Layout.alignment: Qt.AlignHCenter
                visible: root.maskedMode && root.busy
                text: "正在处理，请稍候。"
                color: theme.textSecondary
                font.pixelSize: 14
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }

            Text {
                objectName: "handoffFailureLabel"
                Layout.alignment: Qt.AlignHCenter
                visible: root.maskedMode && root.failureVisible
                text: root.failureKind === "after_commit"
                      ? "操作已记录，界面尚未准备好。请重试进入回合。"
                      : "暂未进入回合，请重试。"
                color: theme.textSecondary
                font.pixelSize: 14
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }

            // ---- primary activation -------------------------------------------
            // Legacy: 确认交接 -> guiApp.confirmHandoff(nextPlayerId) (unchanged).
            // Masked:  接管    -> sessionStore.requestTakeover() (the private pending
            // token never reaches QML; the Store supplies it internally).
            AppButton {
                id: primaryButton
                objectName: "grHandoffStart"
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 200
                text: root.maskedMode
                      ? (root.startupIntro ? GuiText.startupStartGame : "接管")
                      : "确认交接"
                enabled: !root.busy && !root.failureVisible
                visible: !root.failureVisible
                onClicked: {
                    if (root.maskedMode) {
                        sessionStore.requestTakeover()
                    } else {
                        if (guiApp.confirmHandoff(root.nextPlayerId)) {
                            root.visible = false
                        }
                    }
                }
            }

            // ---- bounded activation retry (activation MASKED_FAILURE only) -----
            // SD-R02.2: visibility narrowed to the `activation` route AND an added
            // EXPLICIT `enabled: !busy` binding (the base AppButton had none, so it
            // defaulted to true). objectName / route / activation-only semantics
            // are preserved.
            AppButton {
                id: retryButton
                objectName: "grHandoffRetry"
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 200
                text: "重试"
                visible: root.activationRetryEligible
                enabled: !root.busy
                onClicked: sessionStore.retryHandoff()
            }

            // ---- bounded continuation recovery (AI-drain MASKED_FAILURE only) --
            // §1.1.R (SD-R02): the ONE new bounded recovery control, in the
            // INHERITED neutral recovery layout (same layout class as
            // grHandoffRetry; existing Theme AppButton; no new overlay/card/
            // container; no geometry authority). Visible/enabled ONLY for the
            // `continuation` failureRoute, so it is structurally mutually
            // exclusive with grHandoffRetry (activation) and the resolution-
            // entry-only grResolutionRetrySettlement.
            // AppButton is a Rectangle + MouseArea with NO default Enter/Space
            // activation, so the keyboard activation is wired EXPLICITLY and
            // locally (no AppButton component change).
            AppButton {
                id: recoverButton
                objectName: "grContinuationRecover"
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 200
                text: "继续处理"
                visible: root.continuationRecoverEligible
                enabled: !root.busy
                onClicked: root._activateRecovery()
                Keys.onReturnPressed: function(event) {
                    event.accepted = true
                    if (event.isAutoRepeat) return
                    root._activateRecovery()
                }
                Keys.onEnterPressed: function(event) {
                    event.accepted = true
                    if (event.isAutoRepeat) return
                    root._activateRecovery()
                }
                Keys.onSpacePressed: function(event) {
                    event.accepted = true
                    if (event.isAutoRepeat) return
                    root._activateRecovery()
                }
            }

            // ---- bounded safe exit (MASKED_PENDING / MASKED_FAILURE) -----------
            // Reuses the safe application exit path; no Save/Load capability.
            AppButton {
                id: exitButton
                objectName: "grHandoffExit"
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 200
                text: root.startupIntro ? GuiText.startupExit : "退出"
                visible: root.maskedMode && root.canExit
                onClicked: root.requestExit()
            }
        }
    }
}
