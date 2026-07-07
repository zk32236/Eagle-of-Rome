import QtQuick 2.15

// ============================================================
// EOR GUI 主题配色 — 罗马暖色风（羊皮纸 + 深红 + 古铜）
// 参考：EOR_GUI_Design_Spec.md V2.0 §5 配色方案
// ============================================================

QtObject {
    // ── 背景 ──
    readonly property color bgApp: "#F5F0E8"           // 全局背景（羊皮纸色）
    readonly property color bgSurface1: "#FAF5EE"      // 面板背景（浅羊皮纸）
    readonly property color bgSurface2: "#FFFDF5"      // 数据行/卡片背景（奶油白）
    readonly property color bgSurface3: "#EDE5D8"      // 表头/分隔区背景（淡褐）

    // ── 边界 ──
    readonly property color borderNormal: "#D4A574"    // 面板边框（古铜色）
    readonly property color borderStrong: "#C9A84C"    // 强调边框（金色古铜）

    // ── 强调色 ──
    readonly property color accentPrimary: "#8B2500"   // 罗马深红（标题栏/主按钮/阶段标记）
    readonly property color accentPrimaryDark: "#6B1C00" // 暗红（底部操作栏/深色按钮）
    readonly property color accentBronze: "#C9A84C"    // 古铜色（边框/高亮指示器）
    readonly property color accentBronzeHighlight: "#D0B170" // 古铜高亮

    // ── 文字 ──
    readonly property color textPrimary: "#3A3530"     // 主文字（深棕）
    readonly property color textSecondary: "#8B7355"   // 次要文字（棕灰）
    readonly property color textMuted: "#B8A080"       // 弱化文字（浅棕）

    // ── 状态色 ──
    readonly property color statusSuccess: "#228B22"   // 成功（通过/胜利）
    readonly property color statusWarning: "#FF8C00"   // 警告（风险/提醒）
    readonly property color statusError: "#C45151"     // 错误（失败/危机）
    readonly property color statusInfo: "#6C8FA1"      // 信息（通知）

    // ── 派系色 ──
    readonly property color factionOptimates: "#8B0000"  // 贵族（深红）
    readonly property color factionPopulares: "#006400"  // 平民（深绿）
    readonly property color factionEquites: "#00008B"    // 骑士（深蓝）

    // ── 字体 ──
    readonly property string fontFamily: "Microsoft YaHei UI"
    readonly property string fontTitle: "SimSun"

    // ── 尺寸 ──
    readonly property int titleSize: 22
    readonly property int panelTitleSize: 13
    readonly property int bodySize: 12
    readonly property int smallSize: 11
    readonly property int radius: 6                       // 全局圆角（来自 CSS --radius: 6px）

    // ── 阶段颜色映射 ──
    function phaseColor(phaseId) {
        if (phaseId === "mortality") return accentPrimary
        if (phaseId === "revenue") return accentPrimary
        if (phaseId === "forum") return accentPrimary
        if (phaseId === "population") return accentPrimary  // 人口=深红
        if (phaseId === "senate") return accentBronze       // 元老院=古铜
        if (phaseId === "combat") return statusError
        if (phaseId === "resolution") return textMuted
        return textMuted
    }
}
