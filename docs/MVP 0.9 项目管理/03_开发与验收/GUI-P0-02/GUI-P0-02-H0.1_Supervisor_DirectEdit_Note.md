# H0.1 — Supervisor Direct Modification Note

**Date:** 2026-07-12  
**Context:** H0 Codex Review returned "有条件通过" with one blocker: PhaseRailIcon.qml gradient syntax error causing GUI startup failure (7 tests → 4 passed, 3 failed).

The supervisor directly edited 2 files before spawning a DA sub-agent for this fix. This note documents those changes so future DA sub-agents are aware.

---

## Change 1: PhaseRailIcon.qml — Gradient Syntax Error

**File:** `src/ui/gui/qml/components/PhaseRailIcon.qml`

**Before (QML syntax error):**
```qml
gradient: {
    if (root.state === "done") {
        return Gradient {
            GradientStop { position: 0.0; color: "#B34F8B57" }
            GradientStop { position: 1.0; color: "#B8375F3C" }
        }
    }
    if (root.state === "current") {
        return Gradient { ... }
    }
    return null
}
```

**After (correct):**
```qml
gradient: Gradient {
    orientation: Gradient.Vertical
    GradientStop { position: 0.0; color: root.state === "done" ? "#B34F8B57" : root.state === "current" ? "#EFD27D" : "transparent" }
    GradientStop { position: 1.0; color: root.state === "done" ? "#B8375F3C" : root.state === "current" ? "#D2A144" : "transparent" }
}
```

**Root cause:** QML does not support JavaScript `return` statements inside composite type property bindings (`gradient`, `font`, `border`, etc.). Must use inline ternary expressions within a single `Gradient` declaration.

**Knowledge file:** `agents/DA-Exec/knowledge/qml-gradient-composition.md`

---

## Change 2: GameShell.qml — stageAnnouncement objectName

**File:** `src/ui/gui/qml/shell/GameShell.qml`

**Change:** Added `objectName: "stageAnnouncement"` to the StageHeaderSlot container Rectangle.

**Why:** The H0 slot consolidation restructured the header section and lost this objectName. The GUI startup test `test_main_qml_exposes_core_gui_regions` uses `findChild(QObject, "stageAnnouncement")` for backward compatibility.

**After fix:** 7/7 GUI startup tests passed.
**Full regression:** 773 passed.
