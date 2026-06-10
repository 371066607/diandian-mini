import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts

ApplicationWindow {
    id: root
    visible: true
    width: 1440
    height: 900
    minimumWidth: 1100
    minimumHeight: 720
    title: appTitle.replace("Google Play", platformLabel)
    color: "#F5F7FB"

    required property var bridge
    required property string appTitle
    readonly property bool isAppStore: bridge.platform === "app_store"
    readonly property string platformLabel: isAppStore ? "App Store" : "Google Play"
    property string currentPage: "dashboard"
    property var navItems: [
        { key: "dashboard", label: "首页", subtitle: "本地监控总览、趋势和提醒" },
        { key: "app_search", label: "应用搜索", subtitle: "按关键词搜索 Google Play 应用" },
        { key: "app_detail", label: "应用详情", subtitle: "应用详情、快照和基础指标" },
        { key: "reviews", label: "评论", subtitle: "评论抓取、筛选和保存" },
        { key: "charts", label: "榜单", subtitle: "Top Free / Paid / Grossing 榜单抓取" },
        { key: "keywords", label: "关键词", subtitle: "关键词排名查询与历史保存" },
        { key: "tracking", label: "监控", subtitle: "管理本地监控任务，同步应用和关键词" },
        { key: "history", label: "历史", subtitle: "本地快照和排名历史" },
        { key: "alerts", label: "提醒", subtitle: "全部监控告警与筛选" },
        { key: "settings", label: "设置", subtitle: "默认国家、语言、数据库路径和调度配置" }
    ]

    function pageIndex(key) {
        for (var i = 0; i < navItems.length; i++) {
            if (navItems[i].key === key) return i
        }
        return 0
    }

    function pageTitle() {
        return navItems[pageIndex(currentPage)].label
    }

    function pageSubtitle() {
        return navItems[pageIndex(currentPage)].subtitle.replace("Google Play", platformLabel)
    }

    function rows(source, key) {
        if (!source || !source[key]) return []
        return source[key]
    }

    function textOr(value, fallback) {
        if (value === undefined || value === null || value === "") return fallback
        return value
    }

    function history(key) {
        var all = bridge.inputHistory || {}
        return all[(isAppStore ? "app_store:" : "google_play:") + key] || []
    }

    function showToast(message, isError) {
        toast.text = message
        toast.color = isError ? "#991B1B" : "#0F172A"
        toast.opacity = 1
        toast.visible = true
        toastTimer.restart()
    }

    Connections {
        target: root.bridge
        function onStatusMessage(message) { root.showToast(message, false) }
        function onErrorMessage(message) { root.showToast(message, true) }
        function onPageRequested(page) { root.currentPage = page }
        function onUpdatePrompt(title, message) {
            updateDialog.heading = title
            updateDialog.body = message
            updateDialog.open()
        }
        function onUpdateApplied(message) {
            restartDialog.body = message
            restartDialog.open()
        }
    }

    // --- design tokens ---
    readonly property color cInk: "#0F172A"
    readonly property color cBody: "#1E293B"
    readonly property color cSlate: "#475569"
    readonly property color cMuted: "#64748B"
    readonly property color cFaint: "#94A3B8"
    readonly property color cLine: "#E2E8F0"
    readonly property color cChipBg: "#F8FAFC"
    readonly property color cBlue: "#2563EB"
    readonly property color cBlueSoft: "#EFF6FF"
    readonly property color cAmber: "#F59E0B"
    readonly property color cGreen: "#16A34A"
    readonly property color cRed: "#DC2626"

    component Card: Rectangle {
        id: card
        default property alias content: body.data
        property string title: ""
        property string subtitle: ""
        property int pad: 20
        Layout.fillWidth: true
        implicitHeight: shell.implicitHeight + pad * 2
        color: "white"
        radius: 10
        border.color: cardHover.hovered ? "#CBD5E1" : "#E2E8F0"
        border.width: 1

        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: "#140F172A"
            shadowBlur: 0.45
            shadowVerticalOffset: 2
            shadowHorizontalOffset: 0
        }

        HoverHandler { id: cardHover }
        Behavior on border.color { ColorAnimation { duration: 130 } }

        ColumnLayout {
            id: shell
            anchors.fill: parent
            anchors.margins: card.pad
            spacing: 14

            ColumnLayout {
                spacing: 2
                visible: card.title.length > 0
                Layout.fillWidth: true
                Label {
                    text: card.title
                    color: "#1E293B"
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                }
                Label {
                    text: card.subtitle
                    visible: card.subtitle.length > 0
                    color: root.cFaint
                    font.pixelSize: 12
                    Layout.fillWidth: true
                }
            }

            ColumnLayout {
                id: body
                spacing: 12
                Layout.fillWidth: true
            }
        }
    }

    component Badge: Rectangle {
        id: badge
        property string text: ""
        property color tint: root.cBlue
        property bool subtle: false
        visible: text.length > 0
        radius: height / 2
        color: subtle ? Qt.alpha(tint, 0.12) : tint
        implicitWidth: badgeText.implicitWidth + 16
        implicitHeight: 22
        Label {
            id: badgeText
            anchors.centerIn: parent
            text: badge.text
            color: badge.subtle ? badge.tint : "white"
            font.pixelSize: 11
            font.weight: Font.DemiBold
        }
    }

    component StatChip: Rectangle {
        id: chip
        property string label: ""
        property string value: "-"
        property string accent: ""
        Layout.fillWidth: true
        implicitHeight: 64
        radius: 10
        color: accent === "blue" ? root.cBlueSoft : root.cChipBg
        border.color: accent === "blue" ? "#BFDBFE" : root.cLine
        ColumnLayout {
            anchors.fill: parent
            anchors.leftMargin: 14
            anchors.rightMargin: 14
            anchors.topMargin: 10
            anchors.bottomMargin: 10
            spacing: 3
            Label { text: chip.label; color: root.cMuted; font.pixelSize: 11 }
            Label {
                text: chip.value
                color: chip.accent === "blue" ? "#1D4ED8" : root.cInk
                font.pixelSize: 15
                font.weight: Font.Bold
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
        }
    }

    component RoundedImage: Item {
        id: rimg
        property alias source: rimgImage.source
        property real cornerRadius: 10
        property string fallbackText: ""
        Rectangle {
            anchors.fill: parent
            radius: rimg.cornerRadius
            color: "#F1F5F9"
            border.color: root.cLine
            visible: rimgImage.status !== Image.Ready
            Label {
                anchors.centerIn: parent
                text: rimg.fallbackText.length > 0 ? rimg.fallbackText.charAt(0).toUpperCase() : "·"
                color: root.cFaint
                font.pixelSize: Math.max(12, rimg.height / 3)
                font.weight: Font.Bold
            }
        }
        Image {
            id: rimgImage
            anchors.fill: parent
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            visible: status === Image.Ready
            layer.enabled: true
            layer.effect: MultiEffect {
                maskEnabled: true
                maskSource: rimgMask
                maskThresholdMin: 0.5
                maskSpreadAtMin: 1.0
            }
        }
        Rectangle {
            id: rimgMask
            anchors.fill: parent
            radius: rimg.cornerRadius
            color: "black"
            visible: false
            layer.enabled: true
        }
    }

    component LinkText: Label {
        property string label: ""
        property string urlText: ""
        property string url: ""
        text: urlText.length > 0 && url.length > 0
              ? label + "：<a href=\"" + url + "\">" + urlText + "</a>"
              : label + "：-"
        textFormat: Text.RichText
        linkColor: root.cBlue
        color: root.cBody
        font.pixelSize: 13
        wrapMode: Text.WrapAnywhere
        Layout.fillWidth: true
        onLinkActivated: function(link) { Qt.openUrlExternally(link) }
        HoverHandler { cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor }
    }

    component Field: TextField {
        height: 38
        implicitWidth: 180
        selectByMouse: true
        color: "#0F172A"
        selectedTextColor: "#0F172A"
        selectionColor: "#DBEAFE"
        background: Rectangle {
            radius: 8
            color: "white"
            border.color: parent.activeFocus ? "#2563EB" : "#CBD5E1"
            Behavior on border.color { ColorAnimation { duration: 120 } }
        }
        leftPadding: 12
        rightPadding: 12
        font.pixelSize: 13
    }

    // Text field with a per-platform input-history dropdown. Built on a plain TextField
    // (NOT ComboBox) so the typed text survives a model change — submitting a search
    // appends to history, which would otherwise reset a ComboBox's editText to blank.
    component HistoryField: FocusScope {
        id: hf
        property string historyKey: ""
        property string placeholderText: ""
        property alias text: hfInput.text
        signal accepted()
        height: 38
        implicitWidth: 180
        implicitHeight: 38

        Rectangle {
            anchors.fill: parent
            radius: 8
            color: "white"
            border.color: hfInput.activeFocus ? "#2563EB" : "#CBD5E1"
            Behavior on border.color { ColorAnimation { duration: 120 } }
        }

        TextField {
            id: hfInput
            anchors.fill: parent
            leftPadding: 12
            rightPadding: 30
            selectByMouse: true
            color: "#0F172A"
            selectedTextColor: "#0F172A"
            selectionColor: "#DBEAFE"
            placeholderText: hf.placeholderText
            placeholderTextColor: "#94A3B8"
            font.pixelSize: 13
            verticalAlignment: Text.AlignVCenter
            background: null
            onAccepted: hf.accepted()
        }

        // history dropdown toggle (only when this field has remembered values)
        Label {
            anchors.right: parent.right
            anchors.rightMargin: 11
            anchors.verticalCenter: parent.verticalCenter
            text: "▾"
            color: hpopup.visible ? "#2563EB" : "#94A3B8"
            font.pixelSize: 11
            visible: root.history(hf.historyKey).length > 0
            TapHandler {
                cursorShape: Qt.PointingHandCursor
                onTapped: hpopup.visible ? hpopup.close() : hpopup.open()
            }
        }

        Popup {
            id: hpopup
            y: hf.height + 4
            width: hf.width
            padding: 6
            implicitHeight: Math.min(hlist.contentHeight + 12, 240)
            background: Rectangle {
                radius: 8
                color: "white"
                border.color: "#E2E8F0"
            }
            contentItem: ListView {
                id: hlist
                clip: true
                implicitHeight: contentHeight
                model: root.history(hf.historyKey)
                boundsBehavior: Flickable.StopAtBounds
                ScrollIndicator.vertical: ScrollIndicator {}
                delegate: ItemDelegate {
                    width: ListView.view ? ListView.view.width : hf.width
                    height: 32
                    contentItem: Label {
                        text: modelData
                        color: "#1E293B"
                        font.pixelSize: 12
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 6
                    }
                    background: Rectangle {
                        radius: 6
                        color: hovered ? "#EFF6FF" : "transparent"
                    }
                    onClicked: {
                        hf.text = modelData
                        hpopup.close()
                        hfInput.forceActiveFocus()
                    }
                }
            }
        }
    }

    component QuietCombo: ComboBox {
        height: 38
        implicitWidth: 120
        font.pixelSize: 13
        background: Rectangle {
            radius: 8
            color: "white"
            border.color: parent.activeFocus ? "#2563EB" : "#CBD5E1"
            Behavior on border.color { ColorAnimation { duration: 120 } }
        }
        contentItem: Text {
            text: parent.displayText
            color: "#0F172A"
            verticalAlignment: Text.AlignVCenter
            leftPadding: 12
            rightPadding: 28
            elide: Text.ElideRight
        }
    }

    component PrimaryButton: Button {
        height: 38
        font.pixelSize: 13
        font.weight: Font.DemiBold
        palette.buttonText: "white"
        scale: down ? 0.985 : (hovered ? 1.01 : 1.0)
        Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
        background: Rectangle {
            radius: 8
            color: parent.down ? "#1E40AF" : (parent.hovered ? "#1D4ED8" : "#2563EB")
            border.color: color
            Behavior on color { ColorAnimation { duration: 120 } }
        }
    }

    component SecondaryButton: Button {
        height: 38
        font.pixelSize: 13
        font.weight: Font.DemiBold
        palette.buttonText: "#1E293B"
        scale: down ? 0.985 : (hovered ? 1.01 : 1.0)
        Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
        background: Rectangle {
            radius: 8
            color: parent.down ? "#EEF2FF" : (parent.hovered ? "#F8FAFC" : "white")
            border.color: parent.hovered ? "#94A3B8" : "#CBD5E1"
            Behavior on color { ColorAnimation { duration: 120 } }
            Behavior on border.color { ColorAnimation { duration: 120 } }
        }
    }

    component ToolbarFlow: Flow {
        Layout.fillWidth: true
        spacing: 10
    }

    component SparkLine: Canvas {
        id: spark
        property var values: []
        property real reveal: 1
        Layout.fillWidth: true
        Layout.preferredHeight: 116
        antialiasing: true
        onValuesChanged: {
            reveal = 0
            revealAnim.restart()
            requestPaint()
        }
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onRevealChanged: requestPaint()

        NumberAnimation {
            id: revealAnim
            target: spark
            property: "reveal"
            from: 0
            to: 1
            duration: 520
            easing.type: Easing.OutCubic
        }

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.clearRect(0, 0, width, height)
            ctx.strokeStyle = "#E2E8F0"
            ctx.lineWidth = 1
            for (var g = 1; g < 4; g++) {
                var y = height * g / 4
                ctx.beginPath()
                ctx.moveTo(0, y)
                ctx.lineTo(width, y)
                ctx.stroke()
            }
            if (!values || values.length === 0) {
                ctx.fillStyle = "#94A3B8"
                ctx.font = "13px sans-serif"
                ctx.textAlign = "center"
                ctx.fillText("暂无历史数据", width / 2, height / 2)
                return
            }
            var min = values[0]
            var max = values[0]
            for (var i = 0; i < values.length; i++) {
                min = Math.min(min, Number(values[i]))
                max = Math.max(max, Number(values[i]))
            }
            if (min === max) max = min + 1
            var visibleCount = Math.max(1, Math.ceil(values.length * Math.max(0.02, reveal)))
            var xs = []
            var ys = []
            for (var j = 0; j < visibleCount; j++) {
                xs.push(values.length === 1 ? width / 2 : j * width / (values.length - 1))
                ys.push(height - ((Number(values[j]) - min) / (max - min)) * (height - 20) - 10)
            }
            // soft area fill under the line
            if (xs.length > 1) {
                var grad = ctx.createLinearGradient(0, 0, 0, height)
                grad.addColorStop(0, "rgba(37, 99, 235, 0.16)")
                grad.addColorStop(1, "rgba(37, 99, 235, 0.01)")
                ctx.fillStyle = grad
                ctx.beginPath()
                ctx.moveTo(xs[0], height)
                for (var f = 0; f < xs.length; f++) ctx.lineTo(xs[f], ys[f])
                ctx.lineTo(xs[xs.length - 1], height)
                ctx.closePath()
                ctx.fill()
            }
            ctx.strokeStyle = "#2563EB"
            ctx.lineWidth = 2
            ctx.beginPath()
            for (var k = 0; k < xs.length; k++) {
                if (k === 0) ctx.moveTo(xs[k], ys[k])
                else ctx.lineTo(xs[k], ys[k])
            }
            ctx.stroke()
            // emphasize the latest point
            if (xs.length > 0 && reveal === 1) {
                ctx.fillStyle = "#2563EB"
                ctx.beginPath()
                ctx.arc(xs[xs.length - 1], ys[ys.length - 1], 3, 0, Math.PI * 2)
                ctx.fill()
            }
        }
    }

    component DataTable: Card {
        id: tableCard
        property var rows: []
        property var columns: []
        property string emptyText: "暂无数据"
        property int tableHeight: 260
        property int rowHeight: 44
        property int selectedIndex: -1
        // row[emphasizeKey] truthy -> bold text; row[highlightKey] truthy -> tinted row + accent bar
        property string emphasizeKey: ""
        property string highlightKey: ""
        signal activated(int rowIndex, var rowData)
        signal selectionChanged(int rowIndex, var rowData)
        onRowsChanged: selectedIndex = -1

        RowLayout {
            Layout.fillWidth: true
            spacing: 0
            Repeater {
                model: tableCard.columns
                Label {
                    text: modelData.label
                    color: "#334155"
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                    Layout.preferredWidth: modelData.width || 120
                    Layout.fillWidth: modelData.fill === true
                    leftPadding: 8
                    rightPadding: 8
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: "#E2E8F0"
        }

        ListView {
            id: tableList
            model: tableCard.rows || []
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            Layout.fillWidth: true
            Layout.preferredHeight: tableCard.tableHeight

            delegate: Rectangle {
                id: rowDelegate
                property var rowData: modelData
                property int rowNumber: index
                property bool emphasized: tableCard.emphasizeKey.length > 0 && rowData[tableCard.emphasizeKey] === true
                property bool highlighted: tableCard.highlightKey.length > 0 && rowData[tableCard.highlightKey] === true
                width: ListView.view.width
                height: tableCard.rowHeight
                color: tableCard.selectedIndex === rowNumber
                       ? "#DBEAFE"
                       : (rowHover.hovered ? "#EEF6FF"
                          : (highlighted ? "#EFF6FF" : (rowNumber % 2 === 0 ? "white" : "#F8FAFC")))

                Behavior on color { ColorAnimation { duration: 120 } }
                HoverHandler { id: rowHover }
                TapHandler {
                    acceptedButtons: Qt.LeftButton
                    onTapped: {
                        tableCard.selectedIndex = rowDelegate.rowNumber
                        tableCard.selectionChanged(rowDelegate.rowNumber, rowDelegate.rowData)
                    }
                    onDoubleTapped: {
                        tableCard.selectedIndex = rowDelegate.rowNumber
                        tableCard.activated(rowDelegate.rowNumber, rowDelegate.rowData)
                    }
                }

                Rectangle {
                    visible: rowDelegate.highlighted
                    width: 3
                    height: parent.height
                    color: root.cBlue
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 0
                    anchors.rightMargin: 0
                    spacing: 0
                    Repeater {
                        model: tableCard.columns
                        Item {
                            id: cell
                            property var cellValue: rowDelegate.rowData[modelData.key]
                            property string cellType: modelData.type || "text"
                            Layout.preferredWidth: modelData.width || 120
                            Layout.fillWidth: modelData.fill === true
                            Layout.fillHeight: true

                            // plain text (default)
                            Label {
                                visible: cell.cellType === "text"
                                anchors.fill: parent
                                text: cell.cellValue === undefined || cell.cellValue === null ? "" : cell.cellValue
                                color: modelData.color || "#1E293B"
                                font.pixelSize: 12
                                font.weight: rowDelegate.emphasized ? Font.DemiBold : Font.Normal
                                elide: Text.ElideRight
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: 8
                                rightPadding: 8
                            }

                            // app icon loaded from URL
                            RoundedImage {
                                visible: cell.cellType === "icon"
                                anchors.verticalCenter: parent.verticalCenter
                                x: 8
                                width: Math.min(parent.height - 12, 36)
                                height: width
                                cornerRadius: 8
                                source: cell.cellType === "icon" && cell.cellValue ? cell.cellValue : ""
                                fallbackText: String(rowDelegate.rowData.title || "·")
                            }

                            // colored pill; color comes from row[colorKey]
                            Badge {
                                visible: cell.cellType === "badge" && String(cell.cellValue || "").length > 0
                                anchors.verticalCenter: parent.verticalCenter
                                x: 8
                                text: cell.cellValue === undefined || cell.cellValue === null ? "" : String(cell.cellValue)
                                tint: modelData.colorKey && rowDelegate.rowData[modelData.colorKey]
                                      ? rowDelegate.rowData[modelData.colorKey] : root.cBlue
                                subtle: true
                            }

                            // 1-5 star rating
                            Row {
                                visible: cell.cellType === "stars"
                                anchors.verticalCenter: parent.verticalCenter
                                x: 8
                                spacing: 0
                                Repeater {
                                    model: 5
                                    Label {
                                        text: "★"
                                        font.pixelSize: 12
                                        color: index < Number(cell.cellValue || 0) ? root.cAmber : "#D8DEE9"
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Label {
                anchors.centerIn: parent
                visible: tableList.count === 0
                text: tableCard.emptyText
                color: "#94A3B8"
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.preferredWidth: 220
            Layout.fillHeight: true
            color: "#111827"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 8

                Label {
                    text: "点点数据 Mini"
                    color: "white"
                    font.pixelSize: 18
                    font.weight: Font.Bold
                    Layout.topMargin: 8
                    Layout.bottomMargin: 10
                }

                // Platform switcher: Google Play <-> App Store
                Rectangle {
                    Layout.fillWidth: true
                    Layout.bottomMargin: 12
                    implicitHeight: 36
                    radius: 9
                    color: "#1F2937"
                    border.color: "#374151"

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 3
                        spacing: 3
                        Repeater {
                            model: [
                                { key: "google_play", label: "Google Play" },
                                { key: "app_store", label: "App Store" }
                            ]
                            Rectangle {
                                id: platformSegment
                                property bool active: root.bridge.platform === modelData.key
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                radius: 7
                                color: active ? "#3B82F6"
                                              : (segmentHover.hovered ? "#374151" : "transparent")
                                Behavior on color { ColorAnimation { duration: 140 } }
                                HoverHandler { id: segmentHover; cursorShape: Qt.PointingHandCursor }
                                TapHandler { onTapped: root.bridge.setPlatform(modelData.key) }
                                Label {
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    color: platformSegment.active ? "white" : "#94A3B8"
                                    font.pixelSize: 11
                                    font.weight: Font.DemiBold
                                }
                            }
                        }
                    }
                }

                Repeater {
                    model: root.navItems
                    Button {
                        id: navButton
                        text: modelData.label
                        checkable: true
                        checked: root.currentPage === modelData.key
                        Layout.fillWidth: true
                        height: 38
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        palette.buttonText: checked ? "white" : "#CBD5E1"
                        onClicked: root.currentPage = modelData.key
                        scale: down ? 0.985 : (hovered ? 1.01 : 1.0)
                        Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
                        background: Rectangle {
                            radius: 8
                            color: navButton.checked ? "#3B82F6" : (navButton.hovered ? "#1F2937" : "transparent")
                            border.color: navButton.hovered && !navButton.checked ? "#334155" : "transparent"
                            Behavior on color { ColorAnimation { duration: 140 } }
                            Behavior on border.color { ColorAnimation { duration: 140 } }
                        }

                        Rectangle {
                            visible: modelData.key === "alerts" && (root.bridge.alerts.unread || 0) > 0
                            anchors.right: parent.right
                            anchors.rightMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                            radius: height / 2
                            color: "#EF4444"
                            width: Math.max(20, unreadBadgeText.implicitWidth + 10)
                            height: 18
                            Label {
                                id: unreadBadgeText
                                anchors.centerIn: parent
                                text: Math.min(root.bridge.alerts.unread || 0, 99)
                                color: "white"
                                font.pixelSize: 10
                                font.weight: Font.Bold
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Label {
                    text: root.platformLabel + " / 本地 SQLite"
                    color: "#94A3B8"
                    font.pixelSize: 12
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#F5F7FB"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 28
                spacing: 18

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    ColumnLayout {
                        spacing: 6
                        Layout.fillWidth: true
                        Label {
                            text: root.pageTitle()
                            color: "#0F172A"
                            font.pixelSize: 24
                            font.weight: Font.Bold
                        }
                        Label {
                            text: root.pageSubtitle()
                            color: "#64748B"
                            font.pixelSize: 13
                        }
                    }
                    BusyIndicator {
                        running: root.bridge.busy
                        visible: root.bridge.busy
                    }
                }

                StackLayout {
                    id: pageStack
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: root.pageIndex(root.currentPage)
                    onCurrentIndexChanged: {
                        opacity = 0
                        pageFade.restart()
                    }

                    NumberAnimation {
                        id: pageFade
                        target: pageStack
                        property: "opacity"
                        from: 0
                        to: 1
                        duration: 170
                        easing.type: Easing.OutCubic
                    }

                    DashboardPage {}
                    SearchPage {}
                    DetailPage {}
                    ReviewsPage {}
                    ChartsPage {}
                    KeywordsPage {}
                    TrackingPage {}
                    HistoryPage {}
                    AlertsPage {}
                    SettingsPage {}
                }
            }
        }
    }

    Rectangle {
        id: toast
        visible: false
        opacity: 0
        z: 30
        radius: 8
        color: "#0F172A"
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 28
        width: Math.min(toastText.implicitWidth + 36, root.width - 80)
        height: toastText.implicitHeight + 20
        property alias text: toastText.text
        property real slideOffset: opacity === 0 ? 12 : 0

        Label {
            id: toastText
            anchors.centerIn: parent
            width: parent.width - 28
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            color: "white"
            font.pixelSize: 13
            font.weight: Font.DemiBold
        }

        Behavior on opacity { NumberAnimation { duration: 180 } }
        transform: Translate { y: toast.slideOffset }
        Behavior on slideOffset { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
    }

    Timer {
        id: toastTimer
        interval: 2600
        onTriggered: toast.opacity = 0
    }

    // --- update confirm dialog (Yes/No) ---
    Dialog {
        id: updateDialog
        property string heading: "检查更新"
        property string body: ""
        anchors.centerIn: parent
        modal: true
        padding: 22
        width: Math.min(460, root.width - 80)
        header: null
        Overlay.modal: Rectangle { color: "#660F172A" }
        background: Rectangle { radius: 12; color: "white"; border.color: "#E2E8F0" }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: updateDialog.heading
                color: "#0F172A"
                font.pixelSize: 16
                font.weight: Font.Bold
            }
            Label {
                text: updateDialog.body
                color: "#475569"
                font.pixelSize: 13
                lineHeight: 1.35
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                Layout.topMargin: 4
                spacing: 10
                SecondaryButton {
                    text: "暂不更新"
                    implicitWidth: 96
                    onClicked: { root.bridge.dismissUpdate(); updateDialog.close() }
                }
                PrimaryButton {
                    text: "立即更新"
                    implicitWidth: 96
                    onClicked: { updateDialog.close(); root.bridge.confirmUpdate() }
                }
            }
        }
    }

    // --- post-update restart dialog ---
    Dialog {
        id: restartDialog
        property string body: ""
        anchors.centerIn: parent
        modal: true
        padding: 22
        width: Math.min(420, root.width - 80)
        header: null
        closePolicy: Popup.NoAutoClose
        Overlay.modal: Rectangle { color: "#660F172A" }
        background: Rectangle { radius: 12; color: "white"; border.color: "#E2E8F0" }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: "更新完成"
                color: "#0F172A"
                font.pixelSize: 16
                font.weight: Font.Bold
            }
            Label {
                text: restartDialog.body
                color: "#475569"
                font.pixelSize: 13
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            PrimaryButton {
                text: "立即重启"
                Layout.alignment: Qt.AlignRight
                implicitWidth: 110
                onClicked: { restartDialog.close(); root.bridge.restartApp() }
            }
        }
    }

    Rectangle {
        id: busyOverlay
        visible: root.bridge.busy || opacity > 0
        opacity: root.bridge.busy ? 1 : 0
        z: 20
        anchors.fill: parent
        color: "#660F172A"
        Behavior on opacity { NumberAnimation { duration: 140 } }

        Rectangle {
            id: pulse
            anchors.centerIn: parent
            width: 88
            height: 88
            radius: 44
            color: "#263B82F6"
            border.color: "#66FFFFFF"
            SequentialAnimation on scale {
                running: root.bridge.busy
                loops: Animation.Infinite
                NumberAnimation { to: 1.18; duration: 720; easing.type: Easing.InOutQuad }
                NumberAnimation { to: 0.96; duration: 720; easing.type: Easing.InOutQuad }
            }
            SequentialAnimation on opacity {
                running: root.bridge.busy
                loops: Animation.Infinite
                NumberAnimation { to: 0.45; duration: 720; easing.type: Easing.InOutQuad }
                NumberAnimation { to: 0.9; duration: 720; easing.type: Easing.InOutQuad }
            }
        }

        Label {
            anchors.centerIn: parent
            text: "处理中..."
            color: "white"
            font.pixelSize: 18
            font.weight: Font.DemiBold
        }
    }

    component DashboardPage: ScrollView {
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            spacing: 18

            GridLayout {
                Layout.fillWidth: true
                columns: width < 900 ? 2 : 5
                columnSpacing: 16
                rowSpacing: 16
                Repeater {
                    model: root.rows(root.bridge.dashboard, "stats")
                    Card {
                        Layout.fillWidth: true
                        title: modelData.label
                        Label {
                            text: modelData.value
                            color: "#0F172A"
                            font.pixelSize: 22
                            font.weight: Font.Bold
                        }
                        Label { text: modelData.meta; color: "#64748B"; font.pixelSize: 12 }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 18
                Card {
                    title: "评分 / 评论趋势"
                    SparkLine { values: root.rows(root.bridge.dashboard, "ratingValues") }
                }
                Card {
                    title: root.bridge.dashboard.keywordName ? "关键词「" + root.bridge.dashboard.keywordName + "」排名" : "关键词排名变化"
                    SparkLine { values: root.rows(root.bridge.dashboard, "keywordValues") }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 18
                DataTable {
                    title: "最近提醒"
                    rows: root.rows(root.bridge.dashboard, "alerts")
                    tableHeight: 220
                    emphasizeKey: "unread"
                    columns: [
                        { label: "时间", key: "time", width: 86 },
                        { label: "级别", key: "severity", width: 64, type: "badge", colorKey: "severityColor" },
                        { label: "类型", key: "type", width: 112 },
                        { label: "App", key: "appId", width: 130 },
                        { label: "内容", key: "message", fill: true }
                    ]
                }
                Card {
                    title: "监控健康"
                    Layout.preferredWidth: 420
                    Layout.alignment: Qt.AlignTop
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 1
                        rowSpacing: 10
                        Repeater {
                            model: root.rows(root.bridge.dashboard, "health")
                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: 86
                                radius: 8
                                color: "#F8FAFC"
                                border.color: "#E2E8F0"
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    Rectangle {
                                        width: 10
                                        height: 10
                                        radius: 5
                                        color: modelData.statusColor
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 4
                                        Label { text: modelData.title; color: "#0F172A"; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                                        Label { text: "评分 " + modelData.rating + " · 安装 " + modelData.installs; color: "#475569"; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
                                        Label { text: "上次同步 " + modelData.lastSynced; color: "#64748B"; font.pixelSize: 12 }
                                    }
                                }
                            }
                        }
                        Label {
                            text: "暂无监控 App"
                            visible: root.rows(root.bridge.dashboard, "health").length === 0
                            color: "#94A3B8"
                        }
                    }
                }
            }
        }
    }

    component TrackingPage: ScrollView {
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            spacing: 18

            Card {
                ToolbarFlow {
                    HistoryField { id: trackAppId; historyKey: "app_id"; placeholderText: "com.whatsapp"; width: 240 }
                    Field { id: trackCountry; text: textOr(root.bridge.tracking.defaults ? root.bridge.tracking.defaults.country : "", "us"); width: 90 }
                    Field { id: trackLang; text: textOr(root.bridge.tracking.defaults ? root.bridge.tracking.defaults.lang : "", "en"); width: 90 }
                    QuietCombo {
                        id: trackFreq
                        width: 100
                        textRole: "label"
                        valueRole: "value"
                        model: [
                            { label: "每日", value: "daily" },
                            { label: "每周", value: "weekly" },
                            { label: "手动", value: "manual" }
                        ]
                    }
                    PrimaryButton { text: "添加 App 监控"; onClicked: root.bridge.addApp(trackAppId.text, trackCountry.text, trackLang.text, trackFreq.currentValue) }
                    SecondaryButton { text: "同步全部"; onClicked: root.bridge.syncAll() }
                    SecondaryButton { text: "同步到期项"; onClicked: root.bridge.syncDue() }
                }
                ToolbarFlow {
                    HistoryField { id: chartAppId; historyKey: "app_id"; placeholderText: "com.whatsapp"; width: 220 }
                    QuietCombo { id: chartCollection; width: 130; model: ["top_free", "top_paid", "top_grossing"] }
                    Field { id: chartCategory; text: "APPLICATION"; width: 140 }
                    SecondaryButton { text: "添加榜单监控"; onClicked: root.bridge.addChartApp(chartAppId.text, chartCollection.currentText, chartCategory.text, trackCountry.text, trackLang.text) }
                    SecondaryButton { text: "刷新"; onClicked: root.bridge.refreshTracking() }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 18
                ColumnLayout {
                    spacing: 18
                    Layout.fillWidth: true
                    DataTable {
                        title: "App 监控"
                        rows: root.rows(root.bridge.tracking, "apps")
                        tableHeight: 210
                        columns: [
                            { label: "App", key: "title", fill: true },
                            { label: "包名", key: "appId", width: 180 },
                            { label: "国家", key: "country", width: 52 },
                            { label: "频率", key: "frequency", width: 58 },
                            { label: "上次同步", key: "lastSynced", width: 98 },
                            { label: "下次同步", key: "nextSync", width: 98 },
                            { label: "状态", key: "enabled", width: 54 }
                        ]
                    }
                    DataTable {
                        title: "关键词监控"
                        rows: root.rows(root.bridge.tracking, "keywords")
                        tableHeight: 190
                        columns: [
                            { label: "关键词", key: "keyword", fill: true },
                            { label: "App", key: "appId", width: 180 },
                            { label: "排名", key: "rank", width: 68 },
                            { label: "国家", key: "country", width: 52 },
                            { label: "频率", key: "frequency", width: 58 },
                            { label: "上次同步", key: "lastSynced", width: 98 },
                            { label: "状态", key: "enabled", width: 54 }
                        ]
                    }
                    DataTable {
                        title: "榜单监控"
                        rows: root.rows(root.bridge.tracking, "charts")
                        tableHeight: 170
                        columns: [
                            { label: "App", key: "appId", fill: true },
                            { label: "榜单", key: "collection", width: 110 },
                            { label: "分类", key: "category", width: 118 },
                            { label: "国家", key: "country", width: 52 },
                            { label: "排名", key: "rank", width: 70 },
                            { label: "状态", key: "enabled", width: 54 }
                        ]
                    }
                }
            }
        }
    }

    component SettingsPage: ScrollView {
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            spacing: 18
            Card {
                title: "全局配置"
                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 16
                    rowSpacing: 12
                    Label { text: "默认国家"; color: "#334155" }
                    Field { id: setCountry; text: textOr(root.bridge.settings.default_country, "us"); Layout.fillWidth: true }
                    Label { text: "默认语言"; color: "#334155" }
                    Field { id: setLang; text: textOr(root.bridge.settings.default_lang, "en"); Layout.fillWidth: true }
                    Label { text: "默认 limit"; color: "#334155" }
                    Field { id: setLimit; text: textOr(root.bridge.settings.default_limit, "50"); Layout.fillWidth: true }
                    Label { text: "数据库路径"; color: "#334155" }
                    Field { id: setDbPath; text: textOr(root.bridge.settings.database_path, "./data/diandian_mini.sqlite3"); Layout.fillWidth: true }
                    Label { text: "每日同步时间"; color: "#334155" }
                    Field { id: setSyncTime; text: textOr(root.bridge.settings.daily_sync_time, "09:00"); Layout.fillWidth: true }
                    Label { text: "请求延迟秒数"; color: "#334155" }
                    Field { id: setDelay; text: textOr(root.bridge.settings.request_delay_seconds, "1"); Layout.fillWidth: true }
                    Label { text: "代理"; color: "#334155" }
                    Field { id: setProxy; text: textOr(root.bridge.settings.proxy, ""); Layout.fillWidth: true }
                    Label { text: "定时任务"; color: "#334155" }
                    CheckBox { id: setScheduler; text: "启用"; checked: textOr(root.bridge.settings.scheduler_enabled, "true") === "true" }
                }
                PrimaryButton {
                    text: "保存设置"
                    onClicked: root.bridge.saveSettings({
                        default_country: setCountry.text,
                        default_lang: setLang.text,
                        default_limit: setLimit.text,
                        database_path: setDbPath.text,
                        daily_sync_time: setSyncTime.text,
                        request_delay_seconds: setDelay.text,
                        proxy: setProxy.text,
                        scheduler_enabled: setScheduler.checked ? "true" : "false"
                    })
                }
            }
            Card {
                title: "关于 / 更新"
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    Label {
                        text: "当前版本　" + root.bridge.appVersion
                        color: "#0F172A"
                        font.weight: Font.DemiBold
                        Layout.fillWidth: true
                    }
                    SecondaryButton { text: "刷新设置"; onClicked: root.bridge.refreshSettings() }
                    PrimaryButton { text: "检查更新"; onClicked: root.bridge.checkUpdates() }
                }
                Label {
                    visible: root.bridge.updateStatus.length > 0
                    text: root.bridge.updateStatus
                    color: "#64748B"
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }
        }
    }

    component SearchPage: ScrollView {
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            spacing: 18
            Card {
                ToolbarFlow {
                    HistoryField { id: searchKeyword; historyKey: "search_keyword"; placeholderText: "photo editor"; width: 260; onAccepted: root.bridge.searchApps(text, searchCountry.text, searchLang.text, searchLimit.text) }
                    Field { id: searchCountry; text: textOr(root.bridge.tracking.defaults ? root.bridge.tracking.defaults.country : "", "us"); width: 100 }
                    Field { id: searchLang; text: textOr(root.bridge.tracking.defaults ? root.bridge.tracking.defaults.lang : "", "en"); width: 100 }
                    Field { id: searchLimit; text: textOr(root.bridge.tracking.defaults ? root.bridge.tracking.defaults.limit : "", "50"); width: 100 }
                    PrimaryButton { text: "搜索"; onClicked: root.bridge.searchApps(searchKeyword.text, searchCountry.text, searchLang.text, searchLimit.text) }
                    SecondaryButton { text: "打开详情"; onClicked: root.bridge.openSearchResult(searchTable.selectedIndex, searchCountry.text, searchLang.text) }
                    SecondaryButton { text: "加入监控"; visible: !root.isAppStore; onClicked: root.bridge.addSearchResultTracking(searchTable.selectedIndex, searchCountry.text, searchLang.text) }
                }
            }
            DataTable {
                id: searchTable
                title: "搜索结果 · " + root.bridge.search.summary
                subtitle: "双击打开详情"
                rows: root.rows(root.bridge.search, "rows")
                tableHeight: 520
                rowHeight: 52
                onActivated: function(rowIndex, rowData) { root.bridge.openSearchResult(rowIndex, searchCountry.text, searchLang.text) }
                columns: root.isAppStore ? [
                    { label: "", key: "iconUrl", width: 52, type: "icon" },
                    { label: "应用名", key: "title", fill: true },
                    { label: "App ID", key: "appId", width: 110 },
                    { label: "开发者", key: "developer", width: 170 },
                    { label: "评分", key: "rating", width: 56 },
                    { label: "评分数", key: "ratings", width: 92 },
                    { label: "价格", key: "price", width: 90 },
                    { label: "类别", key: "category", width: 110 },
                    { label: "", key: "hasIap", width: 60, type: "badge", colorKey: "" }
                ] : [
                    { label: "", key: "iconUrl", width: 52, type: "icon" },
                    { label: "应用名", key: "title", fill: true },
                    { label: "包名", key: "appId", width: 210 },
                    { label: "开发者", key: "developer", width: 150 },
                    { label: "评分", key: "rating", width: 56 },
                    { label: "评分数", key: "ratings", width: 92 },
                    { label: "安装量", key: "installs", width: 104 },
                    { label: "价格", key: "price", width: 64 },
                    { label: "", key: "hasIap", width: 60, type: "badge", colorKey: "" }
                ]
            }
        }
    }

    component DetailPage: ScrollView {
        id: detailPage
        clip: true
        contentWidth: availableWidth
        property var d: root.bridge.detail
        ColumnLayout {
            width: parent.width
            spacing: 18

            Card {
                ToolbarFlow {
                    HistoryField { id: detailAppId; historyKey: "app_id"; placeholderText: root.isAppStore ? "App ID（如 310633997）/ Bundle ID" : "com.whatsapp"; width: 260; onAccepted: root.bridge.fetchAppDetail(text, detailCountry.text, detailLang.text) }
                    Field { id: detailCountry; text: textOr(root.bridge.tracking.defaults ? root.bridge.tracking.defaults.country : "", "us"); width: 90 }
                    Field { id: detailLang; text: textOr(root.bridge.tracking.defaults ? root.bridge.tracking.defaults.lang : "", "en"); width: 90 }
                    PrimaryButton { text: "获取详情"; onClicked: root.bridge.fetchAppDetail(detailAppId.text, detailCountry.text, detailLang.text) }
                    SecondaryButton { text: "保存快照"; visible: !root.isAppStore; onClicked: root.bridge.saveDetailSnapshot(detailCountry.text, detailLang.text) }
                    SecondaryButton { text: "加入监控"; visible: !root.isAppStore; onClicked: root.bridge.addDetailTracking(detailCountry.text, detailLang.text) }
                    SecondaryButton { text: "获取权限"; visible: !root.isAppStore; onClicked: root.bridge.fetchDetailPermissions() }
                    SecondaryButton { text: "查看历史"; visible: !root.isAppStore; onClicked: root.bridge.openDetailHistory(detailCountry.text, detailLang.text) }
                    SecondaryButton { text: "打开商店"; onClicked: root.bridge.openStore(detailAppId.text || detailPage.d.appId || "", detailCountry.text, detailLang.text) }
                }
            }

            // --- hero: icon + identity + category chips + full metric grid ---
            Card {
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 18
                    RoundedImage {
                        Layout.preferredWidth: 84
                        Layout.preferredHeight: 84
                        Layout.alignment: Qt.AlignTop
                        cornerRadius: 18
                        source: detailPage.d.iconUrl || ""
                        fallbackText: detailPage.d.title || "·"
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Label {
                            text: detailPage.d.loaded ? detailPage.d.title : "等待加载应用详情"
                            color: root.cInk
                            font.pixelSize: 21
                            font.weight: Font.Bold
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Label {
                            text: detailPage.d.loaded
                                  ? (detailPage.d.appId + " · " + detailPage.d.developer)
                                  : (root.isAppStore ? "输入 App ID / Bundle ID 后点击「获取详情」" : "输入包名后点击「获取详情」")
                            color: root.cMuted
                            font.pixelSize: 13
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Flow {
                            Layout.fillWidth: true
                            spacing: 6
                            visible: detailPage.d.loaded === true
                            Repeater {
                                model: detailPage.d.categories || []
                                Badge { text: modelData; tint: root.cBlue; subtle: true }
                            }
                            Badge { text: detailPage.d.priceLabel || ""; tint: root.cGreen; subtle: true }
                            Badge {
                                text: detailPage.d.available === false ? "已下架" : ""
                                tint: root.cRed
                                subtle: true
                            }
                        }
                        Label {
                            visible: (detailPage.d.summary || "").length > 0
                            text: detailPage.d.summary || ""
                            color: root.cSlate
                            font.pixelSize: 13
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }
                }

                GridLayout {
                    visible: detailPage.d.loaded === true
                    Layout.fillWidth: true
                    columns: width < 760 ? 2 : (width < 1080 ? 4 : 6)
                    columnSpacing: 12
                    rowSpacing: 12
                    Repeater {
                        model: detailPage.d.metrics || []
                        StatChip { label: modelData.label; value: modelData.value; accent: modelData.accent || "" }
                    }
                }
            }

            // --- histogram + developer info ---
            RowLayout {
                Layout.fillWidth: true
                spacing: 18
                visible: detailPage.d.loaded === true
                Card {
                    title: "评分分布"
                    visible: !root.isAppStore
                    Layout.preferredWidth: 5
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: detailPage.d.histogram || []
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10
                                Label { text: modelData.star + "★"; color: root.cMuted; font.pixelSize: 12; Layout.preferredWidth: 26 }
                                Rectangle {
                                    Layout.fillWidth: true
                                    height: 14
                                    radius: 7
                                    color: "#F1F5F9"
                                    Rectangle {
                                        width: parent.width * modelData.ratio
                                        height: parent.height
                                        radius: 7
                                        color: modelData.star >= 4 ? root.cGreen : (modelData.star === 3 ? root.cAmber : root.cRed)
                                        Behavior on width { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
                                    }
                                }
                                Label { text: modelData.text; color: root.cSlate; font.pixelSize: 12; Layout.preferredWidth: 120; horizontalAlignment: Text.AlignRight }
                            }
                        }
                        Label {
                            visible: (detailPage.d.histogram || []).length === 0
                            text: "暂无评分分布数据"
                            color: root.cFaint
                            font.pixelSize: 13
                        }
                    }
                }
                Card {
                    title: "开发者信息"
                    Layout.preferredWidth: 4
                    Layout.alignment: Qt.AlignTop
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: detailPage.d.devLinks || []
                            LinkText { label: modelData.label; urlText: modelData.text; url: modelData.url }
                        }
                        Repeater {
                            model: detailPage.d.devPlain || []
                            Label {
                                text: modelData.label + "：" + modelData.value
                                color: root.cBody
                                font.pixelSize: 13
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                }
            }

            // --- monetization + trend sparklines (GP only: built on install counts + local snapshots) ---
            RowLayout {
                Layout.fillWidth: true
                spacing: 18
                visible: detailPage.d.loaded === true && !root.isAppStore
                Card {
                    title: "商业化强度"
                    Layout.preferredWidth: 2
                    Layout.alignment: Qt.AlignTop
                    Label {
                        text: (detailPage.d.monetizationScore || 0) + " / 100"
                        color: root.cInk
                        font.pixelSize: 28
                        font.weight: Font.Bold
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        height: 8
                        radius: 4
                        color: "#F1F5F9"
                        Rectangle {
                            width: parent.width * Math.min(1, (detailPage.d.monetizationScore || 0) / 100)
                            height: parent.height
                            radius: 4
                            color: root.cBlue
                            Behavior on width { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
                        }
                    }
                    Label {
                        text: detailPage.d.monetizationNote || "基于公开数据推断，不代表真实收入。"
                        color: root.cMuted
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
                Card {
                    title: "评分趋势"
                    Layout.preferredWidth: 3
                    SparkLine { values: detailPage.d.ratingValues || [] }
                }
                Card {
                    title: "评论数趋势"
                    Layout.preferredWidth: 3
                    SparkLine { values: detailPage.d.reviewsValues || [] }
                }
            }

            Card {
                title: "安装量趋势（真实安装数）"
                visible: detailPage.d.loaded === true && !root.isAppStore
                SparkLine { values: detailPage.d.installsValues || []; Layout.preferredHeight: 150 }
            }

            // --- screenshots ---
            Card {
                title: "应用截图"
                visible: detailPage.d.loaded === true && (detailPage.d.screenshots || []).length > 0
                ListView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 236
                    orientation: ListView.Horizontal
                    spacing: 12
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    model: (detailPage.d.screenshots || []).slice(0, 12)
                    delegate: RoundedImage {
                        width: 124
                        height: 224
                        cornerRadius: 12
                        source: modelData
                        fallbackText: "图"
                    }
                }
            }

            // --- description / changelog ---
            Card {
                title: "应用描述"
                visible: detailPage.d.loaded === true && ((detailPage.d.description || "").length > 0 || (detailPage.d.changelog || "").length > 0)
                property bool expanded: false
                id: descCard
                Label {
                    text: detailPage.d.description || "暂无描述"
                    color: root.cSlate
                    font.pixelSize: 13
                    lineHeight: 1.4
                    wrapMode: Text.WordWrap
                    maximumLineCount: descCard.expanded ? 9999 : 8
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                SecondaryButton {
                    text: descCard.expanded ? "收起" : "展开全文"
                    visible: (detailPage.d.description || "").length > 400
                    onClicked: descCard.expanded = !descCard.expanded
                }
                Label {
                    visible: (detailPage.d.changelog || "").length > 0
                    text: "更新日志"
                    color: root.cBody
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
                Label {
                    visible: (detailPage.d.changelog || "").length > 0
                    text: detailPage.d.changelog || ""
                    color: root.cSlate
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            // --- more info ---
            Card {
                title: "更多信息"
                visible: detailPage.d.loaded === true
                GridLayout {
                    Layout.fillWidth: true
                    columns: width < 860 ? 1 : 2
                    columnSpacing: 24
                    rowSpacing: 8
                    Repeater {
                        model: detailPage.d.moreInfo || []
                        LinkText {
                            label: modelData.label
                            urlText: modelData.url ? modelData.value : ""
                            url: modelData.url || ""
                            text: modelData.url
                                  ? modelData.label + "：<a href=\"" + modelData.url + "\">" + modelData.value + "</a>"
                                  : modelData.label + "：" + modelData.value
                        }
                    }
                }
                Label {
                    visible: (detailPage.d.contentRatingDescription || "").length > 0
                    text: "内容分级说明：" + (detailPage.d.contentRatingDescription || "")
                    color: root.cSlate
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Label {
                    text: "数据安全：" + (detailPage.d.dataSafety || "-")
                    color: root.cSlate
                    font.pixelSize: 13
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            // --- permissions (GP only) ---
            Card {
                title: "权限"
                visible: detailPage.d.loaded === true && !root.isAppStore
                Label {
                    visible: detailPage.d.permissionsLoaded !== true
                    text: "点击工具栏「获取权限」按钮加载"
                    color: root.cFaint
                    font.pixelSize: 13
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: 16
                    visible: detailPage.d.permissionsLoaded === true
                    Repeater {
                        model: detailPage.d.permissions || []
                        Column {
                            width: 300
                            spacing: 4
                            Label {
                                text: modelData.group + "（" + modelData.count + "）"
                                color: root.cBody
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                            Repeater {
                                model: modelData.items
                                Label { text: "· " + modelData; color: root.cSlate; font.pixelSize: 12; width: 290; wrapMode: Text.WordWrap }
                            }
                        }
                    }
                    Label {
                        visible: detailPage.d.permissionsLoaded === true && (detailPage.d.permissions || []).length === 0
                        text: "未找到权限信息"
                        color: root.cFaint
                        font.pixelSize: 13
                    }
                }
            }

            // --- similar apps + recent alerts (GP only: iTunes has no similar API, AS apps aren't tracked) ---
            RowLayout {
                Layout.fillWidth: true
                spacing: 18
                visible: detailPage.d.loaded === true && !root.isAppStore
                DataTable {
                    id: similarTable
                    title: "相似 App"
                    subtitle: detailPage.d.similarLoading === true ? "加载中..." : "双击打开详情"
                    Layout.preferredWidth: 5
                    rows: detailPage.d.similar || []
                    tableHeight: 250
                    rowHeight: 52
                    emptyText: detailPage.d.similarLoading === true ? "正在获取相似应用..." : "暂无相似应用"
                    onActivated: function(rowIndex, rowData) { root.bridge.openSimilarResult(rowIndex, detailCountry.text, detailLang.text) }
                    columns: [
                        { label: "", key: "iconUrl", width: 52, type: "icon" },
                        { label: "应用", key: "title", fill: true },
                        { label: "包名", key: "appId", width: 170 },
                        { label: "评分", key: "rating", width: 52 },
                        { label: "安装量", key: "installs", width: 96 }
                    ]
                }
                DataTable {
                    title: "最近告警"
                    Layout.preferredWidth: 4
                    rows: detailPage.d.recentAlerts || []
                    tableHeight: 250
                    emptyText: "暂无告警"
                    columns: [
                        { label: "时间", key: "time", width: 86 },
                        { label: "级别", key: "severity", width: 56, type: "badge", colorKey: "severityColor" },
                        { label: "类型", key: "type", width: 100 },
                        { label: "内容", key: "message", fill: true }
                    ]
                }
            }

            // --- recent cached reviews (GP only) ---
            DataTable {
                title: "最近评论（监控落库）"
                visible: detailPage.d.loaded === true && !root.isAppStore
                rows: detailPage.d.recentReviews || []
                tableHeight: 230
                emptyText: "暂无落库评论，可在监控同步后查看"
                columns: [
                    { label: "时间", key: "time", width: 100 },
                    { label: "评分", key: "rating", width: 96, type: "stars" },
                    { label: "内容", key: "content", fill: true }
                ]
            }
        }
    }

    component ChartsPage: ScrollView {
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            spacing: 18
            Card {
                ToolbarFlow {
                    Field { id: chartType; text: "top_free"; width: 160 }
                    HistoryField { id: chartCat; historyKey: "chart_category"; placeholderText: root.isAppStore ? "genre（如 6014 = 游戏）" : "category"; width: 160 }
                    Field { id: chartCountry; text: textOr(root.bridge.tracking.defaults ? root.bridge.tracking.defaults.country : "", "us"); width: 100 }
                    Field { id: chartLang; text: textOr(root.bridge.tracking.defaults ? root.bridge.tracking.defaults.lang : "", "en"); width: 100 }
                    Field { id: chartLimit; text: "100"; width: 100 }
                    PrimaryButton { text: "获取榜单"; onClicked: root.bridge.fetchChart(chartType.text, chartCat.text, chartCountry.text, chartLang.text, chartLimit.text) }
                    SecondaryButton { text: "保存榜单快照"; onClicked: root.bridge.saveChartSnapshot() }
                    SecondaryButton { text: "打开详情"; onClicked: root.bridge.openChartResult(chartTable.selectedIndex, chartCountry.text, chartLang.text) }
                }
            }
            DataTable {
                id: chartTable
                title: "榜单结果 · " + root.bridge.charts.summary
                subtitle: "双击打开详情"
                rows: root.rows(root.bridge.charts, "rows")
                tableHeight: 540
                rowHeight: 52
                onActivated: function(rowIndex, rowData) { root.bridge.openChartResult(rowIndex, chartCountry.text, chartLang.text) }
                columns: root.isAppStore ? [
                    { label: "排名", key: "rank", width: 56 },
                    { label: "", key: "iconUrl", width: 52, type: "icon" },
                    { label: "应用名", key: "title", fill: true },
                    { label: "App ID", key: "appId", width: 120 },
                    { label: "开发者", key: "developer", width: 180 },
                    { label: "价格", key: "price", width: 90 },
                    { label: "类别", key: "category", width: 120 }
                ] : [
                    { label: "排名", key: "rank", width: 56 },
                    { label: "", key: "iconUrl", width: 52, type: "icon" },
                    { label: "应用名", key: "title", fill: true },
                    { label: "包名", key: "appId", width: 220 },
                    { label: "开发者", key: "developer", width: 160 },
                    { label: "评分", key: "rating", width: 56 },
                    { label: "安装量", key: "installs", width: 110 }
                ]
            }
        }
    }

    component KeywordsPage: ScrollView {
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            spacing: 18
            Card {
                ToolbarFlow {
                    HistoryField { id: kwText; historyKey: "keyword"; placeholderText: "messenger"; width: 220 }
                    HistoryField { id: kwApp; historyKey: "app_id"; placeholderText: root.isAppStore ? "App ID（如 310633997）" : "com.whatsapp"; width: 240 }
                    Field { id: kwCountry; text: textOr(root.bridge.tracking.defaults ? root.bridge.tracking.defaults.country : "", "us"); width: 100 }
                    Field { id: kwLang; text: textOr(root.bridge.tracking.defaults ? root.bridge.tracking.defaults.lang : "", "en"); width: 100 }
                    Field { id: kwLimit; text: "100"; width: 100 }
                    PrimaryButton { text: "查询排名"; onClicked: root.bridge.fetchKeywordRank(kwText.text, kwApp.text, kwCountry.text, kwLang.text, kwLimit.text) }
                    SecondaryButton { text: "保存排名"; onClicked: root.bridge.saveKeywordRank() }
                    SecondaryButton { text: "加入监控"; visible: !root.isAppStore; onClicked: root.bridge.addKeywordTracking(kwText.text, kwApp.text, kwCountry.text, kwLang.text) }
                }
            }
            DataTable {
                title: "搜索结果 · " + root.bridge.keywords.summary
                subtitle: "蓝色行 = 目标应用命中位置"
                rows: root.rows(root.bridge.keywords, "rows")
                tableHeight: 520
                rowHeight: 52
                highlightKey: "hit"
                columns: root.isAppStore ? [
                    { label: "排名", key: "rank", width: 56 },
                    { label: "", key: "iconUrl", width: 52, type: "icon" },
                    { label: "应用名", key: "title", fill: true },
                    { label: "App ID", key: "appId", width: 130 },
                    { label: "开发者", key: "developer", width: 190 },
                    { label: "评分", key: "rating", width: 60 }
                ] : [
                    { label: "排名", key: "rank", width: 56 },
                    { label: "", key: "iconUrl", width: 52, type: "icon" },
                    { label: "应用名", key: "title", fill: true },
                    { label: "包名", key: "appId", width: 230 },
                    { label: "开发者", key: "developer", width: 150 },
                    { label: "评分", key: "rating", width: 60 },
                    { label: "安装量", key: "installs", width: 110 }
                ]
            }
        }
    }

    component ReviewsPage: ScrollView {
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            spacing: 18
            Card {
                ToolbarFlow {
                    HistoryField { id: reviewApp; historyKey: "app_id"; placeholderText: root.isAppStore ? "App ID（如 310633997）" : "com.whatsapp"; width: 260 }
                    Field { id: reviewCountry; text: textOr(root.bridge.tracking.defaults ? root.bridge.tracking.defaults.country : "", "us"); width: 100 }
                    Field { id: reviewLang; text: textOr(root.bridge.tracking.defaults ? root.bridge.tracking.defaults.lang : "", "en"); width: 100 }
                    // App Store RSS only supports most-recent ordering
                    Field { id: reviewSort; text: "newest"; width: 140; enabled: !root.isAppStore }
                    PrimaryButton { text: "获取评论"; onClicked: root.bridge.fetchReviews(reviewApp.text, reviewCountry.text, reviewLang.text, reviewSort.text) }
                    SecondaryButton {
                        text: "加载更多"
                        enabled: root.bridge.reviews.hasMore === true
                        onClicked: root.bridge.loadMoreReviews()
                    }
                    SecondaryButton { text: "保存评论"; onClicked: root.bridge.saveReviews(reviewApp.text, reviewCountry.text, reviewLang.text) }
                }
            }
            DataTable {
                title: "评论列表 · " + root.bridge.reviews.summary
                rows: root.rows(root.bridge.reviews, "rows")
                tableHeight: 540
                rowHeight: 48
                columns: [
                    { label: "用户", key: "user", width: 120 },
                    { label: "星级", key: "rating", width: 92, type: "stars" },
                    { label: "版本", key: "version", width: 84 },
                    { label: "时间", key: "time", width: 118 },
                    { label: "内容", key: "content", fill: true },
                    { label: "有用", key: "helpful", width: 56 }
                ]
            }
        }
    }

    component AlertsPage: ScrollView {
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            spacing: 18
            Card {
                ToolbarFlow {
                    PrimaryButton { text: "刷新"; onClicked: root.bridge.refreshAlerts() }
                    SecondaryButton { text: "标记选中已读"; onClicked: root.bridge.markAlertRead(alertsTable.selectedIndex >= 0 ? alertsTable.rows[alertsTable.selectedIndex].id : -1) }
                    SecondaryButton { text: "标记全部已读"; onClicked: root.bridge.markAllAlertsRead() }
                }
            }
            DataTable {
                id: alertsTable
                title: "告警列表"
                subtitle: (root.bridge.alerts.unread || 0) > 0 ? "未读 " + root.bridge.alerts.unread + " 条（加粗显示）" : "全部已读"
                rows: root.rows(root.bridge.alerts, "rows")
                tableHeight: 560
                emphasizeKey: "unread"
                columns: [
                    { label: "时间", key: "time", width: 86 },
                    { label: "级别", key: "severity", width: 64, type: "badge", colorKey: "severityColor" },
                    { label: "类型", key: "type", width: 128 },
                    { label: "App", key: "appId", width: 170 },
                    { label: "内容", key: "message", fill: true },
                    { label: "状态", key: "isRead", width: 60 }
                ]
            }
        }
    }

    component HistoryPage: ScrollView {
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            spacing: 18
            Card {
                ToolbarFlow {
                    QuietCombo {
                        id: historyAppSelector
                        width: 320
                        textRole: "label"
                        model: root.rows(root.bridge.history, "apps")
                        onActivated: root.bridge.loadHistoryIndex(currentIndex)
                    }
                    SecondaryButton { text: "刷新历史"; onClicked: root.bridge.refreshHistory() }
                    Label {
                        text: root.bridge.history.selected ? "当前：" + root.bridge.history.selected : "暂无监控 App"
                        color: "#475569"
                        height: 38
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
            DataTable {
                title: "快照明细"
                rows: root.rows(root.bridge.history, "snapshots")
                tableHeight: 360
                columns: [
                    { label: "时间", key: "time", width: 86 },
                    { label: "标题", key: "title", fill: true },
                    { label: "评分", key: "rating", width: 60 },
                    { label: "评分数", key: "ratings", width: 90 },
                    { label: "评论", key: "reviews", width: 80 },
                    { label: "安装量", key: "installs", width: 110 },
                    { label: "版本", key: "version", width: 100 }
                ]
            }
            DataTable {
                title: "关键词排名历史"
                rows: root.rows(root.bridge.history, "keywords")
                tableHeight: 220
                columns: [
                    { label: "时间", key: "time", width: 86 },
                    { label: "关键词", key: "keyword", fill: true },
                    { label: "排名", key: "rank", width: 70 },
                    { label: "检查范围", key: "limit", width: 90 }
                ]
            }
        }
    }
}
