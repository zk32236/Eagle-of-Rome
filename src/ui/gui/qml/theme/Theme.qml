import QtQuick 2.15

QtObject {
    // 背景
    readonly property color bgApp: "#121512"
    readonly property color bgSurface1: "#181B18"
    readonly property color bgSurface2: "#20241F"
    readonly property color bgSurface3: "#282D27"

    // 边界
    readonly property color borderNormal: "#3C443C"
    readonly property color borderStrong: "#5A6558"

    // 强调
    readonly property color accentPrimary: "#8F3438"
    readonly property color accentPrimaryDark: "#68272B"
    readonly property color accentBronze: "#B69355"
    readonly property color accentBronzeHighlight: "#D0B170"

    // 文字
    readonly property color textPrimary: "#EEEAE1"
    readonly property color textSecondary: "#A9AEA5"
    readonly property color textMuted: "#757C74"

    // 状态
    readonly property color statusSuccess: "#70A17C"
    readonly property color statusWarning: "#C4933D"
    readonly property color statusError: "#C45151"
    readonly property color statusInfo: "#6C8FA1"

    // 字体
    readonly property string fontFamily: "Microsoft YaHei UI"
    readonly property string fontTitle: "SimSun"

    // 尺寸
    readonly property int titleSize: 22
    readonly property int panelTitleSize: 13
    readonly property int bodySize: 12
    readonly property int smallSize: 11
    readonly property int radius: 4

    // 阶段颜色
    function phaseColor(phaseId) {
        if (phaseId === "population") return accentPrimary
        if (phaseId === "senate") return accentBronze
        return textMuted
    }
}
