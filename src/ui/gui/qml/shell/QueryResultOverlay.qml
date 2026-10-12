import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

import "../components"
import "../i18n"

/*!
 * \brief QueryResultOverlay — EOR20261011-01 S1 shared read-only query shell.

 * Bounded read-only dialog (G2 contract ① v1.3 / D1 UI-P09):
 *   header40 FIXED (title elide, status badge; NO Close)
 *   divider1
 *   inner content padding14 / spacing8:
 *     filterRow32 FIXED ([localized label][TextField]; success list/EMPTY AND can_filter)
 *     status36 FIXED (the SINGLE status surface; no in-scroll copy, G16)
 *     divider1
 *     sole resultsScroll (Flickable owns BOTH axes: vertical + horizontal AsNeeded)
 *     actionRow28 ALWAYS reserved (Back LEFT detail/record-denied only; Close RIGHT every outcome)
 *
 * PT-01/PT-02: the results body renders the viewer-projected column schema
 * (list) / ordered field→value table (detail); FOREIGN records omit OWN_PRIVATE
 * columns/rows (absent, never blank) and no cell is truncated — an over-wide row
 * is reachable via the horizontal slider. Permanent 16px right + 16px bottom
 * gutters keep the frame geometry invariant across slider show/hide.
 *
 * Invalidation (v1.2 §2.1): the same-thread GameShell Connections calls
 * resetForInvalidation(keepOpen) which clears every local model, resets BOTH
 * scroll axes, and either keeps the window OPEN (neutral empty body) or closes
 * it. No recursive Store clear. No viewer/faction switch control inside.
 *
 * Localisation (contract ⑤ / F7): title/message/columns/fields resolve their
 * i18n keys — never a hardcoded title/raw enum.
 */
Rectangle {
    id: root
    objectName: "queryResultOverlay"
    color: "#720C1207"
    visible: false
    z: 80

    // Requested by any shell action; GameShell owns Store dispatch + routing.
    signal queryRequested(string queryId, string filterText, string recordId)

    readonly property bool guarded: sessionStore.queryGuarded
    readonly property var dto: sessionStore.globalQueryResult
    readonly property string resultState: dto ? (dto.result_state || "") : ""
    readonly property bool hasResult: dto !== null && dto !== undefined && (dto.id || "") !== ""
    readonly property bool isSuccess: resultState === "OK" || resultState === "EMPTY"
    readonly property bool isDetail: hasResult && dto.detail !== null && dto.detail !== undefined
    readonly property bool isDeniedRecord: resultState === "DENIED"
    readonly property bool canFilter: hasResult && dto.capabilities
                                      && dto.capabilities.can_filter === true
    readonly property bool canDetail: hasResult && dto.capabilities
                                      && dto.capabilities.can_detail === true
    readonly property string activeQueryId: hasResult ? (dto.id || "") : ""
    readonly property var items: (hasResult && dto.items) ? dto.items : []
    readonly property string titleText: hasResult ? GuiText.queryTitle(dto) : GuiText.queryResultTitle
    readonly property string messageText: hasResult ? GuiText.queryMessage(dto) : GuiText.queryResultEmpty
    readonly property string filterLabel: hasResult ? GuiText.queryFilterLabel(activeQueryId) : ""
    readonly property var summaryText: {
        if (!hasResult || !dto.summary) return ""
        var s = dto.summary
        if (s.count !== undefined && s.living_total !== undefined) {
            return GuiText.querySummaryShown + " " + s.count + " / " + s.living_total
        }
        if (s.viewer_faction_id !== undefined && s.factions !== undefined) {
            return GuiText.querySummaryFactions + " " + s.factions.length
        }
        return ""
    }

    // Empty/denied body copy — distinct from the DTO status sentence. The body
    // line is hidden for a record-DENIED outcome (the fixed h36 status frame
    // already conveys it, G16) and whenever the body text would merely repeat
    // the status sentence, so the status sentence is rendered exactly ONCE in
    // the whole dialog (the fixed frame, OUTSIDE resultsScroll).
    readonly property string resultBodyText: GuiText.queryResultEmpty
    readonly property bool showResultBody: hasResult && items.length === 0
                                          && !isDetail && !isDeniedRecord
                                          && resultBodyText !== messageText

    // ------------------------------------------------------------------
    // v1.4 LIST = TABLE — shared fixed-width column tracks (PT-01)
    // ------------------------------------------------------------------
    // The header row and every data row place their cells BY COLUMN TRACK INDEX
    // (never left-packed), so column j begins at the identical x in the header
    // and in all rows. track_w(col) = max(min_width_px, header caption, widest
    // visible cell); the alignment is LEFT for every column (CLI parity).
    readonly property int listCellSpacing: 10
    readonly property int listRowPadding: 10

    // Header schema (localized captions only, no values). Empty in DETAIL/EMPTY/
    // DENIED and for non-tabular lists, so the header hides with the list.
    readonly property var listHeader: (hasResult && !isDetail && dto && dto.columns)
                                      ? dto.columns : []

    // track_w(col): the shared column tracks, computed ONCE (loop-free) from
    // PLAIN inputs — the DTO column schema (min_width_px), the localized header
    // captions and the row VALUE STRINGS — and stored in a PLAIN (non-bound)
    // property. It is assigned only imperatively by recomputeTracks() (on a
    // result-set change or locale change), never by a live property binding, and
    // it never reads any Item's laid-out width. The sizing chain
    // (implicitWidth -> contentColumn.width -> resultsScroll.contentWidth)
    // therefore can never feed back into this array: no "trackWidths" binding
    // loop is possible (Q7 / G17).
    property var trackWidths: []

    // Loop-free recomputation hooks: assign the plain property ONCE per result
    // set. ``trackInputs`` depends on BOTH inputs (header schema + rows), so its
    // changed handler runs only after both are updated; recomputeTracks() is
    // invoked imperatively (never as a binding) here, on locale change and on
    // open. A plain-property assignment emits a normal change notification.
    readonly property var trackInputs: [listHeader, items]
    onTrackInputsChanged: root.recomputeTracks()
    Connections {
        target: localization
        function onLocaleChanged() { root.recomputeTracks() }
    }

    readonly property real listTableWidth: {
        var w = trackWidths
        if (!w || w.length === 0) return 0
        var total = 0
        for (var j = 0; j < w.length; j++) {
            total += w[j]
            if (j < w.length - 1) total += listCellSpacing
        }
        return total
    }
    readonly property real listRowNaturalWidth: listHeader.length > 0
                                                ? (listTableWidth + 2 * listRowPadding) : 0

    // Metrics mirrors of the header caption / cell value fonts (natural width = the
    // exact Text advance width), used to size the shared column tracks.
    TextMetrics {
        id: listHeaderMetrics
        font.pixelSize: 12
        font.bold: true
    }
    TextMetrics {
        id: listCellMetrics
        font.pixelSize: 12
    }

    function open() {
        visible = true
        if (hasResult && dto.filters && dto.filters.applied !== undefined
                && filterField.text !== dto.filters.applied) {
            filterField.text = dto.filters.applied
        }
        // One-shot loop-free track recompute for the freshly-opened result set.
        recomputeTracks()
    }

    function close() {
        visible = false
    }

    // Synchronous local reset for viewer/handoff/reset invalidation. Resets BOTH
    // scroll axes (v1.3 §6 / contract ④.3).
    function resetForInvalidation(keepOpen) {
        filterField.text = ""
        if (resultsScroll) {
            resultsScroll.contentY = 0
            resultsScroll.contentX = 0
        }
        visible = (keepOpen === true)
        // REAL receiver-completion ack (v1.2 §2.1 step 3, A3/F2): the Store must
        // read this acknowledgement — written only AFTER this receiver has
        // cleared every local/bound model — before it publishes a new viewer.
        // No ack (absent/queued/non-responding receiver) => Store fails closed.
        sessionStore.ackQueryInvalidation(sessionStore.queryInvalidationEpoch)
    }

    function statusText() {
        if (resultState === "OK") {
            return dto.status === "connected" ? GuiText.queryStatusConnected
                                              : GuiText.queryStatusReadonly
        }
        if (resultState === "EMPTY") return GuiText.queryStatusEmpty
        if (resultState === "DENIED") return GuiText.queryStatusDenied
        return GuiText.queryStatusError
    }

    function statusColor() {
        if (resultState === "OK") {
            return dto.status === "connected" ? "#70A17C" : "#6C8FA1"
        }
        if (resultState === "EMPTY") return "#9B856B"
        if (resultState === "DENIED") return "#C4933D"
        return "#B0413E"
    }

    function headerLabel(col) {
        if (!col) return ""
        var t = L10n.t(col.label_key)
        if (t !== col.label_key) return t
        return col.label || ""
    }

    // v1.4 regression fix (A6-V01): legacy NON-TABULAR row label resolution.
    // A row whose projected record has NO column schema (every original
    // non-figure list — game_status / faction_info / war_list / legion_status —
    // plus scalars/help) renders the localized item label (label_key -> label),
    // exactly as the pre-v1.4 inline list did (F7: never a hardcoded label).
    function legacyLabel(item) {
        if (!item) return ""
        if (item.label_key) {
            var t = L10n.t(item.label_key)
            if (t !== item.label_key) return t
        }
        return item.label || ""
    }

    function colIndex(colKey) {
        return colTrackIndex(listHeader, colKey)
    }

    // Track index of a column key within an EXPLICIT column-schema list (no
    // dependence on any Item/scroll width — used by the pure track computation).
    function colTrackIndex(cols, colKey) {
        if (!cols) return -1
        for (var j = 0; j < cols.length; j++) {
            if (cols[j].col_key === colKey) return j
        }
        return -1
    }

    function trackWidthFor(colKey) {
        var idx = colIndex(colKey)
        var w = trackWidths
        if (idx < 0 || !w || w[idx] === undefined) return 0
        return w[idx]
    }

    function trackOffsetFor(colKey) {
        var idx = colIndex(colKey)
        var w = trackWidths
        if (idx < 0 || !w) return 0
        var off = 0
        for (var j = 0; j < idx; j++) {
            off += (w[j] || 0) + listCellSpacing
        }
        return off
    }

    function _measureHeader(text) {
        listHeaderMetrics.text = text
        return listHeaderMetrics.width
    }

    function _measureCell(text) {
        listCellMetrics.text = text
        return listCellMetrics.width
    }

    // Pure, parameterised, LOOP-FREE column-track computation. The inputs are
    // ONLY plain DTO/header/row STRING data passed EXPLICITLY (the DTO column
    // schema + localized header captions + row value strings) — never any Item's
    // laid-out width and never a scroll/content width. The TextMetrics objects
    // are mutated and read ONLY here (inside a normal function CALL, never a
    // property-binding evaluation), which removes the in-binding write-then-read
    // that made the track array part of a re-entrant sizing chain.
    function computeTrackWidths(headerCols, rows) {
        if (!headerCols || headerCols.length === 0) return []
        var widths = []
        var j
        for (j = 0; j < headerCols.length; j++) {
            widths.push(Math.max(headerCols[j].min_width_px || 0,
                                 _measureHeader(headerLabel(headerCols[j]))))
        }
        for (var i = 0; i < rows.length; i++) {
            var cells = rows[i].columns || []
            for (var k = 0; k < cells.length; k++) {
                var idx = colTrackIndex(headerCols, cells[k].col_key)
                if (idx < 0) continue
                var cw = _measureCell(GuiText.queryValue(cells[k]))
                if (cw > widths[idx]) widths[idx] = cw
            }
        }
        return widths
    }

    // The ONLY writer of ``trackWidths`` — a one-shot assignment to a plain
    // property (a normal change notification), invoked from a change handler,
    // never from a binding.
    function recomputeTracks() {
        trackWidths = computeTrackWidths(listHeader, items)
    }

    // Header cells: identical x/width tracks as the data rows (index placement).
    function headerCellDescriptors() {
        var out = []
        var cols = listHeader
        for (var j = 0; j < cols.length; j++) {
            out.push({
                col_key: cols[j].col_key,
                x: listRowPadding + trackOffsetFor(cols[j].col_key),
                width: trackWidthFor(cols[j].col_key),
                text: headerLabel(cols[j])
            })
        }
        return out
    }

    // Data cells: value-only, placed on the shared tracks. A FOREIGN row simply
    // has no descriptor for an OWN_PRIVATE column (absent — no cell, no value, no
    // placeholder), and because placement is by track index the public columns
    // stay aligned under their header across ALL rows.
    function rowCellDescriptors(row) {
        var out = []
        if (!row) return out
        var cells = row.columns || []
        for (var k = 0; k < cells.length; k++) {
            var ck = cells[k].col_key
            out.push({
                recId: row.record_id,
                col_key: ck,
                x: listRowPadding + trackOffsetFor(ck),
                width: trackWidthFor(ck),
                text: GuiText.queryValue(cells[k])
            })
        }
        return out
    }

    MouseArea {
        anchors.fill: parent
        onClicked: sessionStore.clearGlobalQuery()
    }

    Rectangle {
        id: dialog
        objectName: "queryResultDialog"
        width: Math.min(parent.width - 160, 720)
        height: Math.min(parent.height - 140, 560)
        anchors.centerIn: parent
        color: "#FFF7E8"
        border.color: "#B8D9AF63"
        border.width: 2
        radius: 12

        MouseArea {
            anchors.fill: parent
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 0
            spacing: 0

            // -- Header (h40 FIXED; title + badge; NO Close) ---------------
            Rectangle {
                objectName: "queryResultHeader"
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                color: "#8B2500"
                radius: 10

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 8
                    spacing: 8

                    Text {
                        text: root.titleText
                        color: "#FFD700"
                        font.pixelSize: 14
                        font.bold: true
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }

                    Text {
                        text: root.statusText()
                        color: root.statusColor()
                        font.pixelSize: 10
                        font.bold: true
                        Layout.maximumWidth: 110
                        elide: Text.ElideRight
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: "#D4A574"
            }

            // -- Inner content: padding14 / spacing8 -----------------------
            ColumnLayout {
                id: content
                objectName: "queryResultContent"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: 14
                spacing: 8

                // -- Filter row (h32 FIXED): [label][TextField] -------------
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 32
                    visible: root.isSuccess && !root.isDetail && root.canFilter
                    color: "transparent"

                    RowLayout {
                        anchors.fill: parent
                        spacing: 6

                        Text {
                            objectName: "queryFilterLabel"
                            visible: text !== ""
                            text: root.filterLabel
                            color: "#8B2500"
                            font.pixelSize: 12
                            font.bold: true
                            Layout.preferredWidth: 96
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                        }

                        TextField {
                            id: filterField
                            objectName: "queryFilterField"
                            Layout.fillWidth: true
                            enabled: !root.guarded
                            placeholderText: GuiText.queryFilterPlaceholder
                            font.pixelSize: 12
                            onTextEdited: root.queryRequested(root.activeQueryId, text, "")
                        }
                    }
                }

                // -- Status preview (h36 FIXED) ----------------------------
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 36
                    color: "transparent"

                    Text {
                        objectName: "queryStatusText"
                        anchors.fill: parent
                        verticalAlignment: Text.AlignVCenter
                        text: root.messageText
                        color: "#8B7355"
                        font.pixelSize: 12
                        lineHeight: 18
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                        clip: true
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: "#40C9A84C"
                }

                // -- Sole results scroll (two-axis) ------------------------
                Flickable {
                    id: resultsScroll
                    objectName: "queryResultsScroll"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    flickableDirection: Flickable.HorizontalAndVerticalFlick
                    boundsBehavior: Flickable.StopAtBounds
                    // Permanent 16px right gutter; content width is independent of
                    // slider visibility (UI-P09(d)).
                    contentWidth: contentColumn.width
                    contentHeight: contentColumn.height + 16

                    ScrollBar.vertical: ScrollBar {
                        objectName: "queryResultsScrollBarV"
                        policy: ScrollBar.AsNeeded
                        readonly property bool asNeeded: policy === ScrollBar.AsNeeded
                        height: resultsScroll.height
                        size: resultsScroll.visibleArea.heightRatio
                        position: resultsScroll.visibleArea.yPosition
                    }

                    ScrollBar.horizontal: ScrollBar {
                        objectName: "queryResultsScrollBarH"
                        policy: ScrollBar.AsNeeded
                        readonly property bool asNeeded: policy === ScrollBar.AsNeeded
                        width: resultsScroll.width
                        size: resultsScroll.visibleArea.widthRatio
                        position: resultsScroll.visibleArea.xPosition
                    }

                    Column {
                        id: contentColumn
                        objectName: "queryResultContentColumn"
                        // Natural width (PT-04): the widest visible row; floored at
                        // the viewport minus the permanent 16px right gutter.
                        width: Math.max(resultsScroll.width - 16, rowsColumn.implicitWidth)
                        spacing: 6

                        Text {
                            visible: root.summaryText !== ""
                            width: parent.width
                            text: root.summaryText
                            color: "#8B7355"
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                        }

                        Column {
                            id: rowsColumn
                            objectName: "queryResultRowsColumn"
                            width: parent.width
                            spacing: 6

                            // LIST = TABLE (PT-01 v1.4): exactly one header row
                            // (localized column captions, CLI order, NO values) as
                            // the FIRST list row, then value-only data rows. Every
                            // cell is placed on the SAME shared fixed-width column
                            // tracks (track_w), so column j begins at the identical
                            // x in the header and in all rows. The header lives in
                            // this same content column inside resultsScroll, so it
                            // co-scrolls with the data on BOTH axes (identical
                            // contentX) and can never misalign.
                            Rectangle {
                                id: listHeaderRow
                                objectName: "queryListHeaderRow"
                                visible: root.listHeader.length > 0
                                implicitWidth: root.listRowNaturalWidth
                                width: Math.max(implicitWidth, resultsScroll.width - 16)
                                height: 28
                                color: "#F1E5C9"
                                border.color: "#B8C9A84C"
                                border.width: 1
                                radius: 6

                                property var headerCells: root.headerCellDescriptors()

                                Repeater {
                                    model: listHeaderRow.headerCells
                                    delegate: Item {
                                        objectName: "queryListHeaderCell_" + modelData.col_key
                                        x: modelData.x
                                        width: modelData.width
                                        height: 28

                                        Text {
                                            objectName: "queryListHeaderLabel_" + modelData.col_key
                                            anchors.left: parent.left
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: modelData.text
                                            color: "#8B2500"
                                            font.pixelSize: 12
                                            font.bold: true
                                            wrapMode: Text.NoWrap
                                        }
                                    }
                                }
                            }

                            // LIST data rows.
                            //  * TABULAR rows (figure_search): value-only cells on
                            //    the SHARED fixed-width column tracks (PT-01 v1.4).
                            //  * NON-TABULAR rows (the original non-figure lists +
                            //    scalars/help): no column schema -> legacy inline
                            //    `label  value` render. The table branch is scoped
                            //    ONLY to rows that actually HAVE columns, so the
                            //    original lists are never blanked (A6-V01 fix).
                            Repeater {
                                model: root.items
                                delegate: Rectangle {
                                    id: listRowDelegate
                                    objectName: "queryRow_" + modelData.record_id
                                    property string recId: modelData.record_id
                                    // A row is tabular iff its projected record
                                    // carries a (non-empty) column schema.
                                    property var cellDescriptors: root.rowCellDescriptors(modelData)
                                    property bool isTabular: listRowDelegate.cellDescriptors.length > 0
                                    // Natural width (floored at the viewport minus
                                    // the permanent 16px right gutter) so the widest
                                    // row drives the content width (PT-04).
                                    implicitWidth: isTabular
                                                   ? root.listRowNaturalWidth
                                                   : (legacyRow.implicitWidth
                                                      + 2 * root.listRowPadding)
                                    width: Math.max(implicitWidth, resultsScroll.width - 16)
                                    height: 28
                                    color: "#FFFDF5"
                                    border.color: "#6BC9A84C"
                                    border.width: 1
                                    radius: 6
                                    visible: !root.isDetail

                                    Repeater {
                                        model: listRowDelegate.cellDescriptors
                                        delegate: Item {
                                            objectName: "queryListCell_" + modelData.recId + "_" + modelData.col_key
                                            x: modelData.x
                                            width: modelData.width
                                            height: 28

                                            Text {
                                                objectName: "queryListValue_" + modelData.recId + "_" + modelData.col_key
                                                anchors.left: parent.left
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: modelData.text
                                                color: "#3A3530"
                                                font.pixelSize: 12
                                                wrapMode: Text.NoWrap
                                            }
                                        }
                                    }

                                    // LEGACY non-tabular row renderer (A6-V01):
                                    // localized label + resolved value, no column
                                    // schema. Visible only when the row has no
                                    // columns; the header row is likewise hidden
                                    // (listHeader is empty for non-tabular lists).
                                    RowLayout {
                                        id: legacyRow
                                        objectName: "queryLegacyRow_" + index
                                        visible: !listRowDelegate.isTabular
                                        anchors.left: parent.left
                                        anchors.leftMargin: root.listRowPadding
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: root.listCellSpacing

                                        Text {
                                            objectName: "queryRowLabel_" + index
                                            property string labelKey: modelData.label_key || ""
                                            text: root.legacyLabel(modelData)
                                            color: "#8B2500"
                                            font.pixelSize: 12
                                            font.bold: true
                                            wrapMode: Text.NoWrap
                                        }
                                        Text {
                                            objectName: "queryRowValue_" + index
                                            property string labelKey: modelData.label_key || ""
                                            text: GuiText.queryValue(modelData)
                                            color: "#3A3530"
                                            font.pixelSize: 12
                                            wrapMode: Text.NoWrap
                                        }
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        enabled: root.canDetail && modelData.record_id !== ""
                                                 && !root.guarded
                                        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                        onClicked: root.queryRequested(root.activeQueryId, "",
                                                                       modelData.record_id)
                                    }
                                }
                            }

                            // DETAIL rows (PT-02: label 160 | wrapping value)
                            Repeater {
                                model: (root.isDetail && root.dto.detail) ? root.dto.detail.fields : []
                                delegate: Rectangle {
                                    width: resultsScroll.width - 16
                                    implicitWidth: 0
                                    height: Math.max(28, detailRow.implicitHeight + 12)
                                    color: "#FFFDF5"
                                    border.color: "#6BC9A84C"
                                    border.width: 1
                                    radius: 6

                                    RowLayout {
                                        id: detailRow
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.margins: 10
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: 10

                                        Text {
                                            text: L10n.t(modelData.label_key) !== modelData.label_key
                                                  ? L10n.t(modelData.label_key) : modelData.label
                                            color: "#8B2500"
                                            font.pixelSize: 12
                                            font.bold: true
                                            Layout.preferredWidth: 160
                                            wrapMode: Text.Wrap
                                        }
                                        Text {
                                            text: GuiText.queryValue(modelData)
                                            color: "#3A3530"
                                            font.pixelSize: 12
                                            Layout.fillWidth: true
                                            Layout.preferredWidth: 0
                                            wrapMode: Text.Wrap
                                        }
                                    }
                                }
                            }
                        }

                        // Empty / denied body. The single DTO status sentence is
                        // the fixed h36 status frame's job ONLY (G16): a
                        // record-DENIED body line is suppressed (its value equals
                        // the status sentence) and the body hides whenever it
                        // would merely repeat the status, so the sentence is
                        // rendered exactly once in the whole dialog.
                        Text {
                            objectName: "queryResultBodyText"
                            visible: root.showResultBody
                            width: parent.width
                            text: root.resultBodyText
                            color: "#9B856B"
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                            topPadding: 8
                        }
                    }
                }

                // -- Action row (h28 ALWAYS reserved) ----------------------
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    color: "transparent"

                    // Back — LEFT (detail/record-denied only)
                    Rectangle {
                        objectName: "queryBackButton"
                        visible: root.isDetail || root.isDeniedRecord
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        width: 60
                        height: 22
                        color: "#DAB77F"
                        border.color: "#C9A84C"
                        border.width: 1
                        radius: 4

                        Text {
                            anchors.centerIn: parent
                            text: GuiText.queryActionBack
                            color: "#3A3530"
                            font.pixelSize: 10
                            font.bold: true
                        }
                        MouseArea {
                            anchors.fill: parent
                            enabled: !root.guarded
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.queryRequested(root.activeQueryId, "", "")
                        }
                    }

                    // Close — RIGHT (available in EVERY outcome)
                    Rectangle {
                        objectName: "queryCloseButton"
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        width: 60
                        height: 22
                        color: "#DAB77F"
                        border.color: "#C9A84C"
                        border.width: 1
                        radius: 4

                        Text {
                            anchors.centerIn: parent
                            text: GuiText.closeQueryResult
                            color: "#3A3530"
                            font.pixelSize: 10
                            font.bold: true
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: sessionStore.clearGlobalQuery()
                        }
                    }
                }
            }
        }
    }
}
