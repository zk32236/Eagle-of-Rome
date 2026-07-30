
import QtQuick 2.15
import QtQuick.Window 2.15
Window {
    visible: false; width: 1440; height: 328
    title: "Revenue Evidence"; color: "#FFF9EC"
    Rectangle { anchors.fill: parent; color: "#FFF9EC"
        Text { x:10; y:10; text:"Revenue Settlement - Post-Settlement State"; font.pixelSize:16; font.bold:true; color:"#681B07" }
Text { x:10; y:42; text:"Treasury: 500 -> 307 (-193)"; font.pixelSize:13; font.bold:false; color:"#2E251B" }
Text { x:10; y:71; text:"=== FACTION TREASURY ==="; font.pixelSize:12; font.bold:true; color:"#000000" }
Text { x:10; y:89; text:"  Optimates  |  Stipend: +10  Tax: +1  Total: +11"; font.pixelSize:11; font.bold:false; color:"#2E251B" }
Text { x:10; y:106; text:"  Populares  |  Stipend: +10  Tax: +2  Total: +12"; font.pixelSize:11; font.bold:false; color:"#2E251B" }
Text { x:10; y:123; text:"  Equites  |  Stipend: +10  Tax: +2  Total: +12"; font.pixelSize:11; font.bold:false; color:"#2E251B" }
Text { x:10; y:150; text:"=== FACTION NAME MAPPING ==="; font.pixelSize:12; font.bold:true; color:"#000000" }
Text { x:10; y:168; text:"  'opt' -> 'Optimates'  (not raw id)"; font.pixelSize:11; font.bold:false; color:"#2E251B" }
Text { x:10; y:185; text:"  'pop' -> 'Populares'  (not raw id)"; font.pixelSize:11; font.bold:false; color:"#2E251B" }
Text { x:10; y:202; text:"  'equ' -> 'Equites'  (not raw id)"; font.pixelSize:11; font.bold:false; color:"#2E251B" }
Text { x:10; y:229; text:"=== PRIVATE LAND ==="; font.pixelSize:12; font.bold:true; color:"#000000" }
Text { x:10; y:247; text:"  Gaius·Marius·Arpinas : +14 Talents"; font.pixelSize:11; font.bold:false; color:"#2E251B" }
Text { x:10; y:264; text:"  Lucius·Cornelius·Sulla·Felix : +11 Talents"; font.pixelSize:11; font.bold:false; color:"#2E251B" }
Text { x:10; y:281; text:"  Marcus·Licinius·Crassus·Dives : +18 Talents"; font.pixelSize:11; font.bold:false; color:"#2E251B" }

    }
}
