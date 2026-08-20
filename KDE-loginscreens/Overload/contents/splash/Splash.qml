/*
    SPDX-FileCopyrightText: 2026 dgudim <dgudim@gmail.com>

    SPDX-License-Identifier: GPL-2.0-or-later
*/

import QtQuick
import org.kde.kirigami as Kirigami

Rectangle {
    id: root
    color: "#000"

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
            anchors.fill: parent

            asynchronous: true
            source: "images/splash.webp"
            paused: false
            fillMode: Image.PreserveAspectCrop
            smooth: false
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
