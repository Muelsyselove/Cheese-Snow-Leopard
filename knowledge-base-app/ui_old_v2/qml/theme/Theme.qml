// Theme — 液态玻璃设计令牌单例
//
// 所有颜色 / 圆角 / 间距 / 字号 / 动效时长统一在此定义，
// 组件与页面禁止硬编码数值，一律引用 Theme.*。
pragma Singleton
import QtQuick

QtObject {
    // ---------------------------------------------------------- 基底
    // 深空午夜蓝基底，不透明（用户明确要求不透明背景）
    readonly property color bgTop: "#FF141B36"
    readonly property color bgMid: "#FF0B0F1E"
    readonly property color bgBottom: "#FF0F1531"

    // 背景环境光斑（流动的有机渐变光效，低透明度铺在深色底上）
    readonly property color blobCyan: "#22D3EE"
    readonly property color blobViolet: "#8B5CF6"
    readonly property color blobPink: "#EC4899"

    // ---------------------------------------------------------- 文字
    readonly property color textPrimary: "#F2F5FF"
    readonly property color textSecondary: "#B9C1DA"
    readonly property color textMuted: "#7D87A8"

    // ---------------------------------------------------------- 玻璃材质（中性三层）
    readonly property color glassFillTop: "#26FFFFFF"     // 层1：基色（上，更实以适配不透明底）
    readonly property color glassFillBottom: "#0DFFFFFF"  // 层1：基色（下）
    readonly property color glassBorderTop: "#66FFFFFF"   // 层3：折射描边（上，苹果式亮边）
    readonly property color glassBorderBottom: "#1AFFFFFF"// 层3：折射描边（下）
    readonly property color glassSpecular: "#4DFFFFFF"    // 层2：镜面高光
    readonly property color glassInnerShadow: "#33000000" // 内阴影，增强3D厚度

    // ---------------------------------------------------------- 强调色
    readonly property color accent: "#22D3EE"         // 主强调（青）
    readonly property color accentViolet: "#A78BFA"   // 次强调（紫）
    readonly property color accentSoft: "#3322D3EE"   // 主强调-弱填充
    readonly property color accentVioletSoft: "#33A78BFA"
    readonly property color danger: "#FB7185"
    readonly property color dangerSoft: "#33FB7185"
    readonly property color success: "#34D399"
    readonly property color successSoft: "#3334D399"
    readonly property color warning: "#FBBF24"
    readonly property color warningSoft: "#33FBBF24"

    // ---------------------------------------------------------- 聊天气泡（用户/AI 不同色调玻璃）
    readonly property color bubbleUserTop: "#3D22D3EE"
    readonly property color bubbleUserBottom: "#1A22D3EE"
    readonly property color bubbleUserBorder: "#6622D3EE"
    readonly property color bubbleAiTop: "#3DA78BFA"
    readonly property color bubbleAiBottom: "#1AA78BFA"
    readonly property color bubbleAiBorder: "#66A78BFA"

    // ---------------------------------------------------------- 圆角（流动的有机形态边缘，同心圆角）
    readonly property int radiusS: 8
    readonly property int radiusM: 12
    readonly property int radiusL: 18
    readonly property int radiusXL: 24
    readonly property int radiusWindow: 16

    // ---------------------------------------------------------- 间距
    readonly property int spaceXS: 4
    readonly property int spaceS: 8
    readonly property int spaceM: 12
    readonly property int spaceL: 16
    readonly property int spaceXL: 24
    readonly property int spaceXXL: 32

    // ---------------------------------------------------------- 字号
    readonly property int fontXS: 10
    readonly property int fontS: 12
    readonly property int fontM: 14
    readonly property int fontL: 17
    readonly property int fontXL: 22
    readonly property int fontTitle: 26

    // ---------------------------------------------------------- 动效时长（ms）
    readonly property int animFast: 120
    readonly property int animMed: 220
    readonly property int animSlow: 420

    // ---------------------------------------------------------- 结构尺寸
    readonly property int navWidth: 196
    readonly property int titleBarHeight: 46
    readonly property int statusBarHeight: 24
    readonly property int buttonHeight: 34
    readonly property int inputHeight: 36
    readonly property int avatarSize: 34
    readonly property int windowMargin: 10
}
