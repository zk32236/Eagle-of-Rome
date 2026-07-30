
import QtQuick 2.15
import QtQuick.Window 2.15

Window {
    visible: false
    width: 1440
    height: 400
    title: "Revenue_Settled"
    color: "#FFF9EC"

    Rectangle {
        anchors.fill: parent
        color: "#FFF9EC"
        
        Text {
            x: 10; y: 10
            text: "Revenue Settlement - Post-Settlement State"
            font.pixelSize: 14
            font.bold: true
            color: "#681B07"
        }
        
        Text {
            x: 10; y: 30
            text: "Starting Treasury: 500 Talents  ->  Ending: 307 Talents"
            font.pixelSize: 10
            font.bold: false
            color: "#2E251B"
        }
        
        Text {
            x: 10; y: 46
            text: "Treasury Delta: -193 Talents"
            font.pixelSize: 10
            font.bold: false
            color: "#2E251B"
        }
        
        Text {
            x: 10; y: 72
            text: "--- FACTION TREASURY (using display names, not raw IDs) ---"
            font.pixelSize: 12
            font.bold: true
            color: "#000000"
        }
        
        Text {
            x: 10; y: 94
            text: "  [DarkRed] Optimates  |  Stipend: +10  Tax: +1  Total: +11"
            font.pixelSize: 10
            font.bold: false
            color: "#2E251B"
        }
        
        Text {
            x: 10; y: 110
            text: "  [DarkGreen] Populares  |  Stipend: +10  Tax: +2  Total: +12"
            font.pixelSize: 10
            font.bold: false
            color: "#2E251B"
        }
        
        Text {
            x: 10; y: 126
            text: "  [DarkBlue] Equites  |  Stipend: +10  Tax: +2  Total: +12"
            font.pixelSize: 10
            font.bold: false
            color: "#2E251B"
        }
        
        Text {
            x: 10; y: 152
            text: "--- PRIVATE LAND INCOME ---"
            font.pixelSize: 12
            font.bold: true
            color: "#000000"
        }
        
        Text {
            x: 10; y: 174
            text: "  Gaius·Marius·Arpinas  |  +14 Talents"
            font.pixelSize: 10
            font.bold: false
            color: "#2E251B"
        }
        
        Text {
            x: 10; y: 190
            text: "  Lucius·Cornelius·Sulla·Felix  |  +11 Talents"
            font.pixelSize: 10
            font.bold: false
            color: "#2E251B"
        }
        
        Text {
            x: 10; y: 206
            text: "  Marcus·Licinius·Crassus·Dives  |  +18 Talents"
            font.pixelSize: 10
            font.bold: false
            color: "#2E251B"
        }
        
        Text {
            x: 10; y: 232
            text: "--- FACTION NAME MAPPING (Evidence for AC-04: display names vs raw IDs) ---"
            font.pixelSize: 12
            font.bold: true
            color: "#000000"
        }
        
        Text {
            x: 10; y: 254
            text: "  faction_id 'opt' -> display name 'Optimates'"
            font.pixelSize: 11
            font.bold: false
            color: "#2E251B"
        }
        
        Text {
            x: 10; y: 270
            text: "  faction_id 'pop' -> display name 'Populares'"
            font.pixelSize: 11
            font.bold: false
            color: "#2E251B"
        }
        
        Text {
            x: 10; y: 286
            text: "  faction_id 'equ' -> display name 'Equites'"
            font.pixelSize: 11
            font.bold: false
            color: "#2E251B"
        }
        
    }
}
