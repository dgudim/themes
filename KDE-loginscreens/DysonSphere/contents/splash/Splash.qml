/*
    SPDX-FileCopyrightText: 2026 dgudim <dgudim@gmail.com>

    SPDX-License-Identifier: GPL-2.0-or-later
*/

import QtQuick
import org.kde.kirigami as Kirigami

Rectangle {
    id: root
    color: "#1d2838"

    property int stage

    onStageChanged: {
        if (stage == 2) {
            introAnimation.running = true;
        }
    }

    Item {
        id: content
        anchors.fill: parent
        opacity: 0

        AnimatedImage {
            id: logo
            readonly property real size: 550

            anchors.centerIn: parent

            asynchronous: true
            source: "images/splash.webp"
            paused: false
            width: size
            height: size
            fillMode: Image.PreserveAspectFit
            smooth: true
        }

        Row {
            id: footer
            spacing: Kirigami.Units.largeSpacing
            anchors {
                bottom: parent.bottom
                horizontalCenter: parent.horizontalCenter
                margins: Kirigami.Units.gridUnit
            }
            Text {
                color: "#f18578"
                anchors.verticalCenter: parent.verticalCenter
                text: "We are cookin'"
                Accessible.name: text
                Accessible.role: Accessible.StaticText
                textFormat: Text.PlainText
            }
            Image {
                asynchronous: true
                source: "images/kde.svgz"
                sourceSize.height: Kirigami.Units.gridUnit * 2
                sourceSize.width: Kirigami.Units.gridUnit * 2
            }
        }
    }

    OpacityAnimator {
        id: introAnimation
        running: false
        target: content
        from: 0
        to: 1
        duration: Kirigami.Units.veryLongDuration * 2
        easing.type: Easing.InOutQuad
    }
}
