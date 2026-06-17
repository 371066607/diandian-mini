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
    color: root.cBg

    required property var bridge
    required property string appTitle
    readonly property bool isAppStore: bridge.platform === "app_store"
    readonly property string platformLabel: isAppStore ? "App Store" : "Google Play"
    property string currentPage: "dashboard"
    property string coverageProgressText: ""
    property real coverageProgressValue: 0
    property var navItems: [
        { key: "dashboard", label: "首页", subtitle: "本地监控总览、趋势和提醒" },
        { key: "app_search", label: "应用搜索", subtitle: "按关键词搜索 Google Play 应用" },
        { key: "app_detail", label: "应用详情", subtitle: "应用详情、快照和基础指标" },
        { key: "reviews", label: "评论", subtitle: "评论抓取、筛选和保存" },
        { key: "charts", label: "榜单", subtitle: "Top Free / Paid / Grossing 榜单抓取" },
        { key: "keywords", label: "关键词", subtitle: "关键词排名查询与历史保存" },
        { key: "coverage", label: "覆盖词", subtitle: "发现哪些关键词能搜到你的 App（覆盖关键词）" },
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
        toast.color = isError ? "#5A1A18" : "#1F2937"
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
        function onCoverageProgress(message, fraction) {
            root.coverageProgressText = message
            root.coverageProgressValue = fraction
        }
    }

    // --- design tokens ---
    // Each theme is a FULL palette — switching recolors the WHOLE app (background,
    // surfaces, borders, text and accent), not just the accent. Switchable live in 设置.
    property string themeName: textOr(bridge.settings.theme, "slate")
    readonly property var themePresets: ({
        "light": {
            bg: "#F3F5F9", surface: "#FFFFFF", sidebar: "#F8FAFC", chip: "#EDF0F5", line: "#DBE1EA",
            ink: "#1B2230", body: "#404B5C", slate: "#5E6A7B", muted: "#7E8898", faint: "#A4AEBC",
            accent: "#2F6FED", accentSoft: "#E5EEFC", onAccent: "#FFFFFF",
            amber: "#C2780A", green: "#1A8A4E", red: "#D33A3A"
        },
        "sand": {
            bg: "#F6F2EB", surface: "#FFFEFA", sidebar: "#FBF8F1", chip: "#F0EADF", line: "#E6DFCF",
            ink: "#2A2419", body: "#4E4636", slate: "#6E6451", muted: "#8D8470", faint: "#B2A993",
            accent: "#DD6B20", accentSoft: "#F8E7D7", onAccent: "#FFFFFF",
            amber: "#B7791F", green: "#2F855A", red: "#C53030"
        },
        "slate": {
            bg: "#1B212B", surface: "#242C38", sidebar: "#171D26", chip: "#2C3543", line: "#39434F",
            ink: "#E7ECF2", body: "#C1C9D4", slate: "#98A2AF", muted: "#7A8492", faint: "#5F6975",
            accent: "#38BDF8", accentSoft: "#103142", onAccent: "#06222E",
            amber: "#F0A93B", green: "#46BE84", red: "#F06D6D"
        },
        "violet": {
            bg: "#1B1726", surface: "#241F33", sidebar: "#181426", chip: "#2C2640", line: "#3A3350",
            ink: "#E9E6F1", body: "#C5BED5", slate: "#A199B6", muted: "#837A97", faint: "#675E7B",
            accent: "#A78BFA", accentSoft: "#2A1F45", onAccent: "#1B1334",
            amber: "#F0A93B", green: "#4FB98A", red: "#F06D6D"
        },
        "teal": {
            bg: "#14201D", surface: "#1C2A27", sidebar: "#102019", chip: "#233631", line: "#314841",
            ink: "#E2EAE7", body: "#B8C7C1", slate: "#92A39C", muted: "#75857E", faint: "#5C6B64",
            accent: "#2DD4BF", accentSoft: "#0E3A31", onAccent: "#06302A",
            amber: "#F0A93B", green: "#3FBE85", red: "#F06D6D"
        }
    })
    readonly property var pal: themePresets[themeName] || themePresets.slate
    readonly property color cBg: pal.bg
    readonly property color cSurface: pal.surface
    readonly property color cSidebar: pal.sidebar
    readonly property color cChipBg: pal.chip
    readonly property color cLine: pal.line
    readonly property color cInk: pal.ink
    readonly property color cBody: pal.body
    readonly property color cSlate: pal.slate
    readonly property color cMuted: pal.muted
    readonly property color cFaint: pal.faint
    readonly property color cBlue: pal.accent
    readonly property color cBlueSoft: pal.accentSoft
    readonly property color cOnAccent: pal.onAccent
    readonly property color cAmber: pal.amber
    readonly property color cGreen: pal.green
    readonly property color cRed: pal.red

    component Card: Rectangle {
        id: card
        default property alias content: body.data
        property string title: ""
        property string subtitle: ""
        property int pad: 20
        Layout.fillWidth: true
        implicitHeight: shell.implicitHeight + pad * 2
        color: root.cSurface
        radius: 10
        border.color: cardHover.hovered ? root.cLine : root.cLine
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
                    color: root.cBody
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
            color: badge.subtle ? badge.tint : root.cOnAccent
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
        border.color: accent === "blue" ? root.cBlueSoft : root.cLine
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
                color: chip.accent === "blue" ? root.cBlue : root.cInk
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
            color: root.cChipBg
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
        color: root.cInk
        selectedTextColor: root.cInk
        selectionColor: root.cBlueSoft
        background: Rectangle {
            radius: 8
            color: root.cSurface
            border.color: parent.activeFocus ? root.cBlue : root.cLine
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
            color: root.cSurface
            border.color: hfInput.activeFocus ? root.cBlue : root.cLine
            Behavior on border.color { ColorAnimation { duration: 120 } }
        }

        TextField {
            id: hfInput
            anchors.fill: parent
            leftPadding: 12
            rightPadding: 30
            selectByMouse: true
            color: root.cInk
            selectedTextColor: root.cInk
            selectionColor: root.cBlueSoft
            placeholderText: hf.placeholderText
            placeholderTextColor: root.cFaint
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
            color: hpopup.visible ? root.cBlue : root.cFaint
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
                color: root.cSurface
                border.color: root.cLine
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
                        color: root.cBody
                        font.pixelSize: 12
                        elide: Text.ElideRight
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: 6
                    }
                    background: Rectangle {
                        radius: 6
                        color: hovered ? root.cBlueSoft : "transparent"
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
            color: root.cSurface
            border.color: parent.activeFocus ? root.cBlue : root.cLine
            Behavior on border.color { ColorAnimation { duration: 120 } }
        }
        contentItem: Text {
            text: parent.displayText
            color: root.cInk
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
        palette.buttonText: root.cOnAccent
        scale: down ? 0.985 : (hovered ? 1.01 : 1.0)
        Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
        background: Rectangle {
            radius: 8
            color: parent.down ? root.cBlue : (parent.hovered ? root.cBlue : root.cBlue)
            border.color: color
            Behavior on color { ColorAnimation { duration: 120 } }
        }
    }

    component SecondaryButton: Button {
        height: 38
        font.pixelSize: 13
        font.weight: Font.DemiBold
        palette.buttonText: root.cBody
        scale: down ? 0.985 : (hovered ? 1.01 : 1.0)
        Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
        background: Rectangle {
            radius: 8
            color: parent.down ? root.cBlueSoft : (parent.hovered ? root.cChipBg : root.cSurface)
            border.color: parent.hovered ? root.cFaint : root.cLine
            Behavior on color { ColorAnimation { duration: 120 } }
            Behavior on border.color { ColorAnimation { duration: 120 } }
        }
    }

    // Themed checkbox. The raw Fusion CheckBox renders as an unstyled dark square
    // with a hard-to-see label that clashes with Field/Button — give it the same
    // rounded, blue-accent look: a visible box + checkmark + readable text label.
    component AppCheck: CheckBox {
        id: ck
        height: 38
        spacing: 8
        font.pixelSize: 13
        indicator: Rectangle {
            implicitWidth: 18
            implicitHeight: 18
            x: ck.leftPadding
            y: ck.height / 2 - height / 2
            radius: 5
            color: ck.checked ? root.cBlue : root.cSurface
            border.color: ck.checked ? root.cBlue : (ck.hovered ? root.cFaint : root.cLine)
            Behavior on color { ColorAnimation { duration: 120 } }
            Behavior on border.color { ColorAnimation { duration: 120 } }
            Text {
                anchors.centerIn: parent
                text: "✓"
                color: root.cOnAccent
                font.pixelSize: 13
                font.bold: true
                visible: ck.checked
            }
        }
        contentItem: Text {
            text: ck.text
            color: ck.enabled ? root.cBody : root.cFaint
            font: ck.font
            verticalAlignment: Text.AlignVCenter
            leftPadding: ck.indicator.width + ck.spacing
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
            ctx.strokeStyle = root.cLine
            ctx.lineWidth = 1
            for (var g = 1; g < 4; g++) {
                var y = height * g / 4
                ctx.beginPath()
                ctx.moveTo(0, y)
                ctx.lineTo(width, y)
                ctx.stroke()
            }
            if (!values || values.length === 0) {
                ctx.fillStyle = root.cFaint
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
            ctx.strokeStyle = root.cBlue
            ctx.lineWidth = 2
            ctx.beginPath()
            for (var k = 0; k < xs.length; k++) {
                if (k === 0) ctx.moveTo(xs[k], ys[k])
                else ctx.lineTo(xs[k], ys[k])
            }
            ctx.stroke()
            // emphasize the latest point
            if (xs.length > 0 && reveal === 1) {
                ctx.fillStyle = root.cBlue
                ctx.beginPath()
                ctx.arc(xs[xs.length - 1], ys[ys.length - 1], 3, 0, Math.PI * 2)
                ctx.fill()
            }
        }
    }

    // Themed trend chart: date x-axis + a dot at each point. Inverts for rank series
    // (smaller rank = better = drawn near the top). Pure Canvas, themed via tokens.
    component TrendChart: Rectangle {
        id: tc
        property string name: ""
        property string current: ""
        property var values: []
        property var labels: []
        property bool invert: false
        Layout.fillWidth: true
        implicitHeight: 168
        radius: 8
        color: root.cChipBg
        border.color: root.cLine
        onValuesChanged: cv.requestPaint()
        onLabelsChanged: cv.requestPaint()
        onInvertChanged: cv.requestPaint()
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 4
            RowLayout {
                Layout.fillWidth: true
                Label { text: tc.name; color: root.cBody; font.pixelSize: 13; Layout.fillWidth: true }
                Label { text: tc.current; color: root.cInk; font.pixelSize: 16; font.weight: Font.DemiBold }
            }
            Canvas {
                id: cv
                Layout.fillWidth: true
                Layout.fillHeight: true
                onPaint: {
                    var ctx = getContext("2d"); ctx.reset(); ctx.clearRect(0, 0, width, height)
                    var vals = tc.values || []
                    var lbls = tc.labels || []
                    var n = vals.length
                    var padL = 42, padR = 8, padT = 10, padB = 20
                    var w = width - padL - padR, h = height - padT - padB
                    var lineC = "" + root.cBlue, gridC = "" + root.cLine, txtC = "" + root.cFaint
                    var fmt = function (v) {
                        if (tc.invert) return "#" + Math.round(v)
                        var a = Math.abs(v)
                        if (a >= 1000000) return (v / 1000000).toFixed(a >= 10000000 ? 0 : 1) + "M"
                        if (a >= 1000) return (v / 1000).toFixed(a >= 10000 ? 0 : 1) + "k"
                        if (a > 0 && a < 10 && Math.round(v) !== v) return v.toFixed(1)
                        return "" + Math.round(v)
                    }
                    var mn = n ? vals[0] : 0, mx = n ? vals[0] : 1
                    for (var i = 0; i < n; i++) { mn = Math.min(mn, vals[i]); mx = Math.max(mx, vals[i]) }
                    if (mn === mx) { mx = mn + 1 }
                    // 横向网格线 + Y 轴量级刻度（上下幅度区间）
                    ctx.strokeStyle = gridC; ctx.lineWidth = 1
                    ctx.fillStyle = txtC; ctx.font = "10px sans-serif"; ctx.textAlign = "right"; ctx.textBaseline = "middle"
                    for (var g = 0; g <= 3; g++) {
                        var gy = padT + h * g / 3
                        ctx.beginPath(); ctx.moveTo(padL, gy); ctx.lineTo(padL + w, gy); ctx.stroke()
                        var gv = tc.invert ? (mn + (mx - mn) * g / 3) : (mx - (mx - mn) * g / 3)
                        ctx.fillText(fmt(gv), padL - 6, gy)
                    }
                    ctx.textBaseline = "alphabetic"
                    if (n === 0) {
                        ctx.fillStyle = txtC; ctx.font = "12px sans-serif"; ctx.textAlign = "center"
                        ctx.fillText("暂无历史数据（同步后逐日累积）", padL + w / 2, padT + h / 2)
                        return
                    }
                    var xat = function (idx) { return padL + (n === 1 ? w / 2 : idx * w / (n - 1)) }
                    var yat = function (v) { var t = (v - mn) / (mx - mn); return tc.invert ? padT + t * h : padT + (1 - t) * h }
                    ctx.strokeStyle = lineC; ctx.lineWidth = 2; ctx.beginPath()
                    for (var k = 0; k < n; k++) { var x = xat(k), y = yat(vals[k]); if (k === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y) }
                    ctx.stroke()
                    ctx.fillStyle = lineC
                    for (var p = 0; p < n; p++) { ctx.beginPath(); ctx.arc(xat(p), yat(vals[p]), 3, 0, Math.PI * 2); ctx.fill() }
                    ctx.fillStyle = txtC; ctx.font = "10px sans-serif"
                    var dl = function (idx) {
                        if (idx < 0 || idx >= lbls.length) return
                        ctx.textAlign = idx === 0 ? "left" : (idx === n - 1 ? "right" : "center")
                        ctx.fillText(lbls[idx], xat(idx), height - 6)
                    }
                    // 每个数据点尽量都标日期；点太多则按可容纳数等距抽稀（每标至少留 ~56px 不重叠），首尾必标
                    var maxLabels = Math.max(2, Math.floor(w / 56))
                    var step = Math.max(1, Math.ceil((n - 1) / Math.max(1, maxLabels - 1)))
                    for (var li = 0; li < n; li += step) dl(li)
                    if ((n - 1) % step !== 0) dl(n - 1)
                }
                Component.onCompleted: requestPaint()
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
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
                    color: root.cBody
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
            color: root.cLine
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
                       ? root.cBlueSoft
                       : (rowHover.hovered ? root.cBlueSoft
                          : (highlighted ? root.cBlueSoft : (rowNumber % 2 === 0 ? root.cSurface : root.cChipBg)))

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
                                color: modelData.color || root.cBody
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
                                        color: index < Number(cell.cellValue || 0) ? root.cAmber : root.cLine
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
                color: root.cFaint
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.preferredWidth: 220
            Layout.fillHeight: true
            color: root.cSidebar

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 8

                Label {
                    text: "点点数据 Mini"
                    color: root.cInk
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
                    color: root.cChipBg
                    border.color: root.cLine

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
                                color: active ? root.cBlue
                                              : (segmentHover.hovered ? root.cLine : "transparent")
                                Behavior on color { ColorAnimation { duration: 140 } }
                                HoverHandler { id: segmentHover; cursorShape: Qt.PointingHandCursor }
                                TapHandler { onTapped: root.bridge.setPlatform(modelData.key) }
                                Label {
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    color: platformSegment.active ? root.cOnAccent : root.cFaint
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
                        palette.buttonText: checked ? root.cOnAccent : root.cMuted
                        onClicked: root.currentPage = modelData.key
                        scale: down ? 0.985 : (hovered ? 1.01 : 1.0)
                        Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
                        background: Rectangle {
                            radius: 8
                            color: navButton.checked ? root.cBlue : (navButton.hovered ? root.cChipBg : "transparent")
                            border.color: navButton.hovered && !navButton.checked ? root.cBody : "transparent"
                            Behavior on color { ColorAnimation { duration: 140 } }
                            Behavior on border.color { ColorAnimation { duration: 140 } }
                        }

                        Rectangle {
                            visible: modelData.key === "alerts" && (root.bridge.alerts.unread || 0) > 0
                            anchors.right: parent.right
                            anchors.rightMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                            radius: height / 2
                            color: root.cRed
                            width: Math.max(20, unreadBadgeText.implicitWidth + 10)
                            height: 18
                            Label {
                                id: unreadBadgeText
                                anchors.centerIn: parent
                                text: Math.min(root.bridge.alerts.unread || 0, 99)
                                color: "#FFFFFF"
                                font.pixelSize: 10
                                font.weight: Font.Bold
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Label {
                    text: root.platformLabel + " / 本地 SQLite"
                    color: root.cFaint
                    font.pixelSize: 12
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: root.cBg

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
                            color: root.cInk
                            font.pixelSize: 24
                            font.weight: Font.Bold
                        }
                        Label {
                            text: root.pageSubtitle()
                            color: root.cMuted
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
                        // Opening 提醒 marks alerts as read so the unread badge clears —
                        // standard notification-tray behaviour. markAllAlertsRead refreshes
                        // the list + badge afterwards; guarded so it only runs when needed.
                        if (currentIndex === root.pageIndex("alerts")
                                && (root.bridge.alerts.unread || 0) > 0)
                            root.bridge.markAllAlertsRead()
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
                    CoveragePage {}
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
        color: "#1F2937"
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
            color: "#EFF3F8"
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
        background: Rectangle { radius: 12; color: root.cSurface; border.color: root.cLine }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: updateDialog.heading
                color: root.cInk
                font.pixelSize: 16
                font.weight: Font.Bold
            }
            Label {
                text: updateDialog.body
                color: root.cSlate
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
        background: Rectangle { radius: 12; color: root.cSurface; border.color: root.cLine }
        contentItem: ColumnLayout {
            spacing: 14
            Label {
                text: "更新完成"
                color: root.cInk
                font.pixelSize: 16
                font.weight: Font.Bold
            }
            Label {
                text: restartDialog.body
                color: root.cSlate
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
            color: root.cSurface
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
                            color: root.cInk
                            font.pixelSize: 22
                            font.weight: Font.Bold
                        }
                        Label { text: modelData.meta; color: root.cMuted; font.pixelSize: 12 }
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
                                color: root.cChipBg
                                border.color: root.cLine
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
                                        Label { text: modelData.title; color: root.cInk; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                                        Label { text: "评分 " + modelData.rating + " · 安装 " + modelData.installs; color: root.cSlate; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
                                        Label { text: "上次同步 " + modelData.lastSynced; color: root.cMuted; font.pixelSize: 12 }
                                    }
                                }
                            }
                        }
                        Label {
                            text: "暂无监控 App"
                            visible: root.rows(root.bridge.dashboard, "health").length === 0
                            color: root.cFaint
                        }
                    }
                }
            }
        }
    }

    component TrackingPage: ScrollView {
        id: monPage
        clip: true
        contentWidth: availableWidth
        property var monTree: ({ apps: [] })
        property var monDetail: ({ title: "", subtitle: "", charts: [] })
        property string selKey: ""
        property string monRange: "30"   // 日期区间：7 / 30 / 90 天，或 all 全部
        property var cur: ({ kind: "", appId: "", ctry: "", lang: "", key: "" })
        function selectMon(kind, appId, ctry, lng, key) {
            monPage.cur = { kind: kind, appId: appId, ctry: ctry, lang: lng, key: key }
            monPage.selKey = kind + ":" + appId + ":" + key
            monPage.loadSeries()
        }
        function loadSeries() {
            if (!monPage.cur.kind) return
            var d = monPage.monRange === "all" ? 0 : parseInt(monPage.monRange)
            monPage.monDetail = root.bridge.monitorSeries(monPage.cur.kind, monPage.cur.appId,
                                                          monPage.cur.ctry, monPage.cur.lang, monPage.cur.key, d)
        }
        Component.onCompleted: monPage.monTree = root.bridge.monitorTree()
        Connections {
            target: root.bridge
            function onTrackingChanged() { monPage.monTree = root.bridge.monitorTree() }
        }
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
                spacing: 14

                Card {
                    Layout.fillWidth: false
                    Layout.preferredWidth: 256
                    Layout.maximumWidth: 256
                    Layout.alignment: Qt.AlignTop
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Label { text: "监控对象（按 App）"; color: root.cFaint; font.pixelSize: 12; Layout.bottomMargin: 4 }
                        Repeater {
                            model: root.rows(monPage.monTree, "apps")
                            ColumnLayout {
                                id: appRow
                                Layout.fillWidth: true
                                spacing: 2
                                property var appNode: modelData
                                property bool expanded: false
                                property bool hasChildren: appNode.keywords.length > 0 || appNode.charts.length > 0
                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitHeight: 34
                                    radius: 7
                                    property string myKey: "app:" + appNode.appId + ":"
                                    color: monPage.selKey === myKey ? root.cBlueSoft : (appHover.hovered ? root.cChipBg : "transparent")
                                    HoverHandler { id: appHover; cursorShape: Qt.PointingHandCursor }
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 8
                                        anchors.rightMargin: 8
                                        spacing: 6
                                        Label {
                                            text: appRow.expanded ? "▾" : "▸"
                                            color: root.cFaint
                                            font.pixelSize: 10
                                            opacity: appRow.hasChildren ? 1 : 0
                                            Layout.preferredWidth: 10
                                        }
                                        Label { text: appNode.title; color: monPage.selKey === parent.parent.myKey ? root.cBlue : root.cInk; font.weight: Font.DemiBold; font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
                                    }
                                    TapHandler {
                                        onTapped: {
                                            if (appRow.hasChildren) appRow.expanded = !appRow.expanded
                                            monPage.selectMon("app", appNode.appId, appNode.country, appNode.lang, "")
                                        }
                                    }
                                }
                                Label {
                                    visible: appRow.expanded && appNode.keywords.length > 0
                                    text: "关键词 · " + appNode.keywords.length
                                    color: root.cFaint
                                    font.pixelSize: 11
                                    Layout.leftMargin: 24
                                    Layout.topMargin: 3
                                }
                                Repeater {
                                    model: appRow.expanded ? appNode.keywords : []
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.leftMargin: 24
                                        implicitHeight: 28
                                        radius: 7
                                        property string myKey: "keyword:" + appNode.appId + ":" + modelData.keyword
                                        color: monPage.selKey === myKey ? root.cBlueSoft : (kwHover.hovered ? root.cChipBg : "transparent")
                                        HoverHandler { id: kwHover; cursorShape: Qt.PointingHandCursor }
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.leftMargin: 8
                                            anchors.rightMargin: 8
                                            spacing: 6
                                            Label { text: modelData.keyword; color: monPage.selKey === parent.parent.myKey ? root.cBlue : root.cBody; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
                                            Label { text: modelData.rank; color: root.cFaint; font.pixelSize: 11 }
                                        }
                                        TapHandler { onTapped: monPage.selectMon("keyword", appNode.appId, modelData.country, modelData.lang, modelData.keyword) }
                                    }
                                }
                                Label {
                                    visible: appRow.expanded && appNode.charts.length > 0
                                    text: "榜单 · " + appNode.charts.length
                                    color: root.cFaint
                                    font.pixelSize: 11
                                    Layout.leftMargin: 24
                                    Layout.topMargin: 3
                                }
                                Repeater {
                                    model: appRow.expanded ? appNode.charts : []
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.leftMargin: 24
                                        implicitHeight: 28
                                        radius: 7
                                        property string ck: modelData.collection + "|" + modelData.category
                                        property string myKey: "chart:" + appNode.appId + ":" + ck
                                        color: monPage.selKey === myKey ? root.cBlueSoft : (chHover.hovered ? root.cChipBg : "transparent")
                                        HoverHandler { id: chHover; cursorShape: Qt.PointingHandCursor }
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.leftMargin: 8
                                            anchors.rightMargin: 8
                                            spacing: 6
                                            Label { text: modelData.collection; color: monPage.selKey === parent.parent.myKey ? root.cBlue : root.cBody; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
                                            Label { text: modelData.rank; color: root.cFaint; font.pixelSize: 11 }
                                        }
                                        TapHandler { onTapped: monPage.selectMon("chart", appNode.appId, modelData.country, modelData.lang, parent.ck) }
                                    }
                                }
                            }
                        }
                        Label {
                            text: "暂无监控对象，先在上方添加 App / 榜单监控"
                            visible: root.rows(monPage.monTree, "apps").length === 0
                            color: root.cFaint
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                }

                Card {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Label {
                            text: textOr(monPage.monDetail.title, "← 选择左侧某个 App / 关键词 / 榜单查看趋势")
                            color: root.cInk
                            font.pixelSize: 16
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Label {
                            text: textOr(monPage.monDetail.subtitle, "")
                            visible: text.length > 0
                            color: root.cFaint
                            font.pixelSize: 12
                            Layout.fillWidth: true
                        }
                        RowLayout {
                            visible: monPage.cur.kind !== ""
                            spacing: 6
                            Layout.topMargin: 2
                            Repeater {
                                model: [{ k: "7", l: "7 天" }, { k: "30", l: "30 天" }, { k: "90", l: "90 天" }, { k: "all", l: "全部" }]
                                Rectangle {
                                    id: rangeTab
                                    property bool on: monPage.monRange === modelData.k
                                    radius: 7
                                    implicitHeight: 28
                                    implicitWidth: tabLbl.implicitWidth + 22
                                    color: rangeTab.on ? root.cBlueSoft : (tabHover.hovered ? root.cChipBg : "transparent")
                                    border.width: 1
                                    border.color: rangeTab.on ? root.cBlue : root.cLine
                                    Label {
                                        id: tabLbl
                                        anchors.centerIn: parent
                                        text: modelData.l
                                        color: rangeTab.on ? root.cBlue : root.cMuted
                                        font.pixelSize: 12
                                        font.weight: rangeTab.on ? Font.DemiBold : Font.Normal
                                    }
                                    HoverHandler { id: tabHover; cursorShape: Qt.PointingHandCursor }
                                    TapHandler { onTapped: { monPage.monRange = modelData.k; monPage.loadSeries() } }
                                }
                            }
                        }
                        Repeater {
                            model: root.rows(monPage.monDetail, "charts")
                            TrendChart {
                                name: modelData.name
                                current: modelData.current
                                values: modelData.values
                                labels: modelData.labels
                                invert: modelData.invert === true
                            }
                        }
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
                    Label { text: "默认国家"; color: root.cBody }
                    Field { id: setCountry; text: textOr(root.bridge.settings.default_country, "us"); Layout.fillWidth: true }
                    Label { text: "默认语言"; color: root.cBody }
                    Field { id: setLang; text: textOr(root.bridge.settings.default_lang, "en"); Layout.fillWidth: true }
                    Label { text: "默认 limit"; color: root.cBody }
                    Field { id: setLimit; text: textOr(root.bridge.settings.default_limit, "50"); Layout.fillWidth: true }
                    Label { text: "数据库路径"; color: root.cBody }
                    Field { id: setDbPath; text: textOr(root.bridge.settings.database_path, "./data/diandian_mini.sqlite3"); Layout.fillWidth: true }
                    Label { text: "每日同步时间"; color: root.cBody }
                    Field { id: setSyncTime; text: textOr(root.bridge.settings.daily_sync_time, "09:00"); Layout.fillWidth: true }
                    Label { text: "请求延迟秒数"; color: root.cBody }
                    Field { id: setDelay; text: textOr(root.bridge.settings.request_delay_seconds, "1"); Layout.fillWidth: true }
                    Label { text: "代理"; color: root.cBody }
                    Field { id: setProxy; text: textOr(root.bridge.settings.proxy, ""); Layout.fillWidth: true }
                    Label { text: "定时任务"; color: root.cBody }
                    AppCheck { id: setScheduler; text: "启用"; checked: textOr(root.bridge.settings.scheduler_enabled, "true") === "true" }
                    Label { text: "主题色"; color: root.cBody }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10
                        Repeater {
                            model: [
                                { k: "light", c: "#2F6FED" },
                                { k: "sand", c: "#DD6B20" },
                                { k: "slate", c: "#38BDF8" },
                                { k: "violet", c: "#A78BFA" },
                                { k: "teal", c: "#2DD4BF" }
                            ]
                            delegate: Rectangle {
                                width: 26
                                height: 26
                                radius: 13
                                color: modelData.c
                                border.width: root.themeName === modelData.k ? 3 : 0
                                border.color: root.cInk
                                TapHandler { onTapped: root.bridge.setTheme(modelData.k) }
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }
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
                        color: root.cInk
                        font.weight: Font.DemiBold
                        Layout.fillWidth: true
                    }
                    SecondaryButton { text: "刷新设置"; onClicked: root.bridge.refreshSettings() }
                    PrimaryButton { text: "检查更新"; onClicked: root.bridge.checkUpdates() }
                }
                Label {
                    visible: root.bridge.updateStatus.length > 0
                    text: root.bridge.updateStatus
                    color: root.cMuted
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
                                    color: root.cChipBg
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
                        color: root.cChipBg
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
                    SecondaryButton { text: "加入监控"; onClicked: root.bridge.addKeywordTracking(kwText.text, kwApp.text, kwCountry.text, kwLang.text) }
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

    component CoveragePage: ScrollView {
        id: coveragePage
        clip: true
        contentWidth: availableWidth
        property var cov: root.bridge.coverage
        ColumnLayout {
            width: parent.width
            spacing: 18

            Card {
                ToolbarFlow {
                    HistoryField {
                        id: covApp
                        historyKey: "app_id"
                        placeholderText: root.isAppStore ? "App ID（如 587366035）/ Bundle ID" : "com.whatsapp"
                        width: 300
                        // Same gate as the button — Enter must not start a second concurrent scan
                        onAccepted: if (!coveragePage.cov.running) root.bridge.discoverCoverage(text, covCountry.text, covLang.text, covDeep.checked)
                    }
                    Field { id: covCountry; text: textOr(root.bridge.tracking.defaults ? root.bridge.tracking.defaults.country : "", "us"); width: 90 }
                    Field { id: covLang; text: textOr(root.bridge.tracking.defaults ? root.bridge.tracking.defaults.lang : "", "en"); width: 90 }
                    AppCheck {
                        id: covDeep
                        text: "深度挖掘"
                        enabled: !coveragePage.cov.running
                        ToolTip.text: "对每个补全词再展开一层（suggest_nested），候选词更多更深，但请求更多、更慢。"
                        ToolTip.visible: hovered
                        ToolTip.delay: 400
                    }
                    PrimaryButton {
                        text: coveragePage.cov.running ? "分析中..." : "发现覆盖关键词"
                        enabled: !coveragePage.cov.running
                        onClicked: root.bridge.discoverCoverage(covApp.text, covCountry.text, covLang.text, covDeep.checked)
                    }
                    SecondaryButton {
                        text: "加入监控（选中词）"
                        enabled: covTable.selectedIndex >= 0 && !coveragePage.cov.running
                        onClicked: {
                            // Track against the SCAN's app/locale (cov.*), not the live input
                            // fields — those may have been edited since the results rendered.
                            var row = coveragePage.cov.rows[covTable.selectedIndex]
                            if (row) root.bridge.addKeywordTracking(row.keyword, coveragePage.cov.appId, coveragePage.cov.country, coveragePage.cov.lang)
                        }
                    }
                }
                Label {
                    text: "原理：从该 App 的标题 / 描述 / 分类自动提词 → 经 " + root.platformLabel + " 自动补全扩展成真实搜索短语 → 逐词检索看你的 App 排第几。只发现「与你 App 文案相关」的词，不是全网穷举。"
                    color: root.cFaint
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            Card {
                visible: coveragePage.cov.running
                Label {
                    text: root.coverageProgressText || "正在生成候选关键词..."
                    color: root.cBody
                    font.pixelSize: 13
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                ProgressBar {
                    Layout.fillWidth: true
                    from: 0
                    to: 1
                    value: root.coverageProgressValue
                }
            }

            DataTable {
                id: covTable
                title: "覆盖关键词 · " + coveragePage.cov.summary
                subtitle: root.platformLabel
                          + " · 按排名升序，选中某行可「加入监控」长期追踪覆盖变化"
                rows: root.rows(coveragePage.cov, "rows")
                tableHeight: 520
                emptyText: coveragePage.cov.running ? "正在分析覆盖关键词..." : "暂无数据，输入 App 后点「发现覆盖关键词」"
                columns: [
                    { label: "排名", key: "rank", width: 90 },
                    { label: "关键词（能搜到你 App 的词）", key: "keyword", fill: true }
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
                        color: root.cSlate
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
