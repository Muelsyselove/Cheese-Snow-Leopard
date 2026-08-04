// TypingIndicator — 流动的打字指示器（三颗玻璃珠依次起伏）
import QtQuick
import "../theme"

Item {
    id: root

    property int dotSize: 8
    property color color: Theme.accentViolet

    implicitWidth: row.implicitWidth
    implicitHeight: row.implicitHeight + dotSize

    Row {
        id: row
        anchors.centerIn: parent
        spacing: Theme.spaceS

        Repeater {
            model: 3
            Rectangle {
                id: dot
                width: root.dotSize
                height: root.dotSize
                radius: width / 2
                color: root.color
                opacity: 0.85

                SequentialAnimation {
                    loops: Animation.Infinite
                    running: root.visible
                    PauseAnimation { duration: index * 160 }
                    NumberAnimation { target: dot; property: "y"; from: 0; to: -root.dotSize * 0.8
                                      duration: 300; easing.type: Easing.OutQuad }
                    NumberAnimation { target: dot; property: "y"; from: -root.dotSize * 0.8; to: 0
                                      duration: 300; easing.type: Easing.InQuad }
                    PauseAnimation { duration: (2 - index) * 160 + 240 }
                }
            }
        }
    }
}
