# GUI LAYOUT CONTRACT — Phase 1 v3.25.1

**Date:** 2026-07-11  
**Version:** v1.0  
**Source:** EOR_GUI_Prototype_v3.25.1.html (Codex v4.0 visual refit + v3.25.1 HUD density override)  
**Reference design:** EOR_GUI_Design_Spec.md  
**Base viewport:** 1440 × 900  
**Allowable error:** Main region positions ±4px; colors must use tokens; no approximate self-selection.

---

## 1. Viewport & Global Background

| Property | Value |
|----------|-------|
| Viewport | 1440 × 900 |
| Body bg | Radial `circle at 12% 10%, rgba(217,175,99,.14), transparent 30%` + Radial `circle at 92% 6%, rgba(118,32,10,.28), transparent 34%` + Linear `135deg, #15110D 0%, #24180F 48%, #100D0A 100%` |
| Shell theme | **Deep-ink shell** (`#14110D`) surrounding **ivory desktop** (`#F2EEE4`) |
| Font | `Microsoft YaHei UI` / `Microsoft YaHei` / `Segoe UI` / sans-serif |
| min-width | 1180px |

---

## 2. Region A — TopStatusBar (Header Bar)

```
┌──────────────────────────────────────────────────────────────────────┐
│ Logo  ┃  国库  ┃  派系  ┃  影响力  ┃  稳定度  ┃  战争  ┃  回合信息  │
└──────────────────────────────────────────────────────────────────────┘
```

| Property | Value |
|----------|-------|
| **Position** | x=10, y=10, w=1420, h=62 |
| **Margin** | 10px top, 10px left, 10px right, **0** bottom |
| **Background** | `linear-gradient(180deg, #8B2A0D 0%, #5A1506 100%)` |
| **Border** | 1px solid `rgba(217,175,99,.58)`, border-radius: 10px |
| **Box Shadow** | `0 10px 28px rgba(0,0,0,.28)` |
| **Padding** | 6px 14px (flex, align-items: center) |

### 2.1 Logo Section

| Property | Value |
|----------|-------|
| Display | flex, align-items: center |
| Padding | 0 14px |
| Border-radius | 9px |
| Background | `rgba(255,255,255,.055)` |
| Border | 1px solid `rgba(242,213,144,.20)` |
| Text | "🏛️ EAGLE OF ROME · SPQR" |
| Main text color | `#F7D778` (`--v325-gold-soft`) |
| Em text color | `rgba(242,213,144,.78)` |
| Font size | 1.04rem (~16.6px) |

### 2.2 Stat Items (5 items in order: 国库, 派系, 影响力, 稳定度, 战争)

| Property | Value |
|----------|-------|
| Container | flex: 1; display: flex; align-items: stretch |
| Gap | 7px between items |
| Item layout | `flex: 1 1 0`, min-width: 88px, height: 100% |
| Item padding | 5px 10px |
| Item border | 1px solid `rgba(242,213,144,.18)`, border-radius: 9px |
| Item background | `rgba(255,255,255,.055)` |
| Item box-shadow | `inset 0 1px 0 rgba(255,255,255,.045)` |
| Stat value font | .94rem (~15px), bold, color: `#F7D778` |
| Stat label font | .62rem (~10px), color: `rgba(243,234,220,.62)` |
| Items order | 国库(💰) → 派系(👛) → 影响力(⚖️) → 稳定度(🏛️) → 战争(⚔️) |

### 2.3 Round Info

| Property | Value |
|----------|-------|
| Position | Rightmost, standalone |
| Min-width | 146px |
| Height | 100% |
| Padding | 0 15px |
| Border-radius | 9px |
| Background | `rgba(0,0,0,.20)` |
| Border | 1px solid `rgba(242,213,144,.24)` |
| Display | flex, align-items: center, justify-content: center |
| Text | "282 BC · 回合 1" |
| Color | `#F7D778` |
| Font | .86rem (~13.8px), bold |

---

## 3. Region B — PhaseRail (Left Nav)

```
┌──────────┐
│ 🎴 天命  │  ← done
│          │
│ 💰 收入  │  ← done
│          │
│ 🏛️ 广场  │  ← current (highlighted)
│          │
│ ⚖️ 人口  │  ← todo
│          │
│ 🏺 元老院│  ← todo
│          │
│ ⚔️ 战斗  │  ← todo
│          │
│ 📊 决算  │  ← todo
└──────────┘
```

| Property | Value |
|----------|-------|
| **Position** | x=10, y=82, w=92, h=736 |
| **Background** | `rgba(31,24,18,.92)` |
| **Border** | 1px solid `rgba(217,175,99,.34)` |
| **Border-radius** | 10px |
| **Box Shadow** | `0 16px 44px rgba(0,0,0,.34)` |
| **Padding** | 10px 8px |
| **Flex** | Column, gap: 8px, align-items: center |

### 3.1 Rail Step Icons (7 steps)

| Property | Value |
|----------|-------|
| Size | 74 × 54px |
| Shape | Border-radius: 10px (pill) |
| Border | 1px solid `rgba(217,175,99,.20)` |
| Flex | Column, align-items: center, gap: 2px |
| Icon font | 1rem (~16px) |

**Step states:**

| State | Background | Text Color | Border |
|-------|-----------|------------|--------|
| `done` | `linear-gradient(180deg, rgba(79,139,87,.70), rgba(55,95,60,.72))` | `#F5EAD2` | `rgba(120,180,120,.48)` |
| `current` | `linear-gradient(180deg, #EFD27D 0%, #D2A144 100%)` | `#2C1E12` | `#F2D590`, box-shadow: `0 0 0 3px rgba(217,175,99,.12), 0 8px 20px rgba(0,0,0,.26)` |
| `todo` | `rgba(255,255,255,.055)` | `#877663` | `rgba(217,175,99,.13)` |

**Label:** Always visible below icon (`.rl { display: block; position: static }`).  
**Label font:** .68rem (~10.9px), color inherits from parent state.  
**Hover effect:** `translateY(-1px)`.

### 3.2 Phase Labels (always visible, order from top)

| # | Icon | Label | Data |
|---|------|-------|------|
| 1 | 🎴 | 天命 | mortality |
| 2 | 💰 | 收入 | revenue |
| 3 | 🏛️ | 广场 | forum |
| 4 | ⚖️ | 人口 | population |
| 5 | 🏺 | 元老院 | senate |
| 6 | ⚔️ | 战斗 | war/combat |
| 7 | 📊 | 决算 | resolution |

---

## 4. Region C — StageDesktop (Center Panel)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  StageHeaderSlot (badge + title + description)                          │
├─────────────────────────────────────────────────────────────────────────┤
│  StageInstructionSlot (step bar / stage-steps)                          │
├─────────────────────────────────────────────────────────────────────────┤
│  StageContentSlot (phase-specific content: events, tables, cards, etc.) │
│                                                                          │
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│  StageActionSlot (main action button, centered at bottom)               │
└─────────────────────────────────────────────────────────────────────────┘
```

| Property | Value |
|----------|-------|
| **Position** | x=112, y=82, w=1022, h=736 |
| **Background** | `linear-gradient(180deg, rgba(255,255,255,.36), rgba(232,223,207,.28))` over `#F2EEE4` |
| **Border** | 1px solid `rgba(217,175,99,.46)` |
| **Border-radius** | 10px |
| **Box Shadow** | `0 16px 44px rgba(0,0,0,.34)` |
| **Padding** | 18px |
| **Flex** | Column, gap: 10px |

### 4.1 StageHeaderSlot

| Property | Value |
|----------|-------|
| Phase badge bg | `linear-gradient(180deg, #84250A, #671B07)` |
| Phase badge color | `#F7D778` |
| Phase badge border | 1px solid `rgba(217,175,99,.32)`, border-radius: 999px |
| Phase badge padding | 4px 12px |
| Phase badge font | .65rem (~10.4px) bold |
| Phase title | 1.22rem (~19.5px), bold, color: `#681B07`, letter-spacing: .02em |
| Phase description | .8rem (~12.8px), italic, color: `#766652`, max-width: 980px |

### 4.2 StageInstructionSlot (Step Bar)

| Property | Value |
|----------|-------|
| Background | `rgba(255,249,236,.82)` |
| Border | 1px solid `rgba(168,117,59,.52)` |
| Border-radius | 10px (inherited radius from stage-steps) |
| Padding | 9px 12px |
| Gap | 7px |
| Box shadow | `inset 0 1px 0 rgba(255,255,255,.72)` |

**Step numbers:** width/height 20px, border-radius 50%, font .6rem bold  
- done: bg `#228B22`, color `#fff`  
- current: bg `#E8B84B`, color `#2C1E12`  
- todo: bg `#E8D5C4`, color `#999`  

**Arrow color:** `rgba(147,133,107,...)` ~ `#B8A080`

### 4.3 StageContentSlot

Fills remaining space. Background transparent (inherits from parent panel).  
Contains phase-specific content (events, info-boxes, cards, tables, etc.).

### 4.4 StageActionSlot

| Property | Value |
|----------|-------|
| Height | ~46px |
| Alignment | Center, bottom of panel |
| Button | `180 × 34px`, bg `linear-gradient(180deg, #84250A, #671B07)`, border-radius 4px |
| Button text | Color `#F7D778`, 13px bold |

---

## 5. Region D — RightStatusPanel (Context Panel)

```
┌──────────────────────────────────────┐
│  CurrentPhaseSection                  │
│    🎯 当前阶段                        │
│    [phase name/goal]                 │
├──────────────────────────────────────┤
│  OperationSection                     │
│    ⚡ 操作                            │
│    [action buttons]                  │
├──────────────────────────────────────┤
│  ProgressSection                      │
│    📋 进度                            │
│    [step / status]                    │
├──────────────────────────────────────┤
│  PlayerSection                        │
│    👤 玩家                            │
│    [faction / members]               │
├──────────────────────────────────────┤
│  EventLogSection                      │
│    📢 事件日志                        │
│    [log entries]                      │
└──────────────────────────────────────┘
```

| Property | Value |
|----------|-------|
| **Position** | x=1144, y=82, w=286, h=736 |
| **Background** | `rgba(31,24,18,.92)` |
| **Border** | 1px solid `rgba(217,175,99,.34)` |
| **Border-radius** | 10px |
| **Box Shadow** | `0 16px 44px rgba(0,0,0,.34)` |
| **Color** | `#F3EADC` (text-light) |
| **Flex** | Column layout |

### 5.1 ctx-top (Sections 1-4)

| Property | Value |
|----------|-------|
| Padding | 14px 14px 10px |
| Gap | 8px (column) |
| Flex-shrink | 0 |

**Section headers (h4):**
- Color: `#F7D778` (gold-soft)
- Font: .74rem, letter-spacing: 1px
- Border-bottom: 1px solid `rgba(217,175,99,.24)`
- Padding-bottom: 5px
- Margin-bottom: 4px

**Stat tiles:**
- Font: .73rem
- Color: `rgba(243,234,220,.??)` → `#B9A58C` (muted-light)
- Border-bottom: 1px solid `rgba(217,175,99,.18)`
- Padding: 4px 0
- Value color: `#F7D778`

### 5.2 Context action buttons

| Property | Value |
|----------|-------|
| Button bg | `rgba(255,255,255,.055)` |
| Button text | `#F3EADC` |
| Button border | 1px solid `rgba(217,175,99,.20)`, radius 7px |
| Button padding | 7px 10px |
| Button margin-bottom | 5px |
| Button font | .73rem, bold |
| Button hover | bg `rgba(217,175,99,.18)`, color `#F7D778`, border `rgba(217,175,99,.52)` |

### 5.3 EventLogSection (ctx-log)

| Property | Value |
|----------|-------|
| Flex | 1 (fills remaining space) |
| Min-height | 60px |
| Padding | 10px 14px |
| Border-top | 1px solid `rgba(217,175,99,.24)` |
| Font | .7rem, line-height: 1.55 |

**Log entries:**
- padding: 2px 0, border-bottom: `rgba(217,175,99,.16)`
- Timestamp color: `#89745C`
- Success: `#228B22`
- Warning: `#FF8C00`
- Error: `#C45151`
- Info: `#B9A58C`

---

## 6. Region E — BottomQueryBar (Operation Bar)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 📊游戏状态  📋派系信息  👤人物查询  💰派系金库  🌾公地信息  🏡私地信息  ... │
└─────────────────────────────────────────────────────────────────────────┘
```

| Property | Value |
|----------|-------|
| **Position** | x=10, y=828, w=1420, h=62 |
| **Margin** | 0 10px 10px |
| **Background** | `linear-gradient(180deg, rgba(105,30,8,.98), rgba(47,24,13,.98))` |
| **Border** | 1px solid `rgba(217,175,99,.32)` |
| **Border-radius** | 10px |
| **Box Shadow** | `0 10px 28px rgba(0,0,0,.26)` |
| **Padding** | 6px 8px |
| **Gap** | 6px |
| **Flex** | Row, align-items: stretch |

### 6.1 Query Buttons

| Property | Value |
|----------|-------|
| Height | 100% |
| flex | `1 1 0` |
| Min-width | 76px |
| Padding | 0 8px |
| Border-radius | 8px |
| Background | `rgba(255,255,255,.06)` |
| Border | 1px solid `rgba(217,175,99,.20)` |
| Box-shadow | `inset 0 1px 0 rgba(255,255,255,.04)` |
| Text | `rgba(243,234,220,.86)`, .7rem, flex with gap 5px |
| Icon | .82rem |
| Hover | bg `rgba(217,175,99,.18)`, border `rgba(217,175,99,.78)`, translateY(-1px) |

**12 buttons in order:**
1. 📊 游戏状态 (game_status)
2. 📋 派系信息 (faction_info)
3. ⚔️ 战争列表 (war_list)
4. 🗡️ 军团状态 (legion_status)
5. 👤 人物查询 (figure_search)
6. 💰 派系金库 (faction_treasury)
7. 🌾 公地信息 (public_land)
8. 🏡 私地信息 (private_land)
9. 📦 合同状态 (contract_status)
10. 🏛️ 行省信息 (province_info)
11. ⚓ 舰队状态 (fleet_status)
12. ❓ 帮助 (help)

---

## 7. Region F — MainAction

| Property | Value |
|----------|-------|
| **Region** | Belongs to C (StageDesktop) |
| **Slot** | StageActionSlot |
| **Position** | Bottom of StageDesktop, horizontalCenter = StageDesktop.center |
| **Offset** | bottom=14px (from StageDesktop padding bottom) |
| **Size** | 180 × 34px |
| **Background** | `linear-gradient(180deg, #84250A, #671B07)` |
| **Border-radius** | 4px |
| **Text** | e.g. "⚡ 执行天命", color `#F7D778`, 13px bold |

---

## 8. Color Token Table

### 8.1 Shell Theme (Deep-Ink)

| Token | Hex/RGBA | Usage |
|-------|----------|-------|
| `ink-bg` | `#14110D` | App background |
| `ink-bg-2` | `#211812` | Secondary bg |
| `ink-panel` | `#1F1812` (rgba(31,24,18,.92)) | Panel surfaces |
| `roman-red` | `#76200A` | Base Roman red |
| `roman-red-2` | `#9A3417` | Lighter red accent |
| `deep-red` | `#561405` | Button bg |
| `gold` | `#D9AF63` | Border/accent gold |
| `gold-soft` | `#F2D590` → `#F7D778` | Highlight text |
| `bronze` | `#A8753B` | Bronze accents |
| `bronze-soft` | `rgba(217,175,99,.34)` | Subtle border |

### 8.2 Ivory Desktop (Panel Center)

| Token | Hex/RGBA | Usage |
|-------|----------|-------|
| `ivory-desk` | `#F2EEE4` | Center panel main bg |
| `ivory-desk-2` | `#E8DFCF` | Desk edge |
| `parchment` | `#FBF1DC` | Card/item bg |
| `parchment-2` | `#F4E2BA` | Parchment edge |
| `paper` | `#FFF9EC` | Hover/active item |
| `text-dark` | `#2E251B` | Dark text |
| `text-soft` | `#756550` | Secondary text |

### 8.3 Status Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `success` | `#228B22` | Done, passed |
| `warning` | `#FF8C00` | Risk, pending |
| `error` | `#C45151` | Failure, crisis |
| `info` | `#6C8FA1` | Blue info |
| `muted-light` | `#B9A58C` | Muted text |

### 8.4 Faction Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `opt` | `#8B0000` | Optimates (aristocrats) |
| `pop` | `#006400` | Populares (populists) |
| `equ` | `#00008B` | Equites (knights) |

---

## 9. Font Token Table

| Token | Size | Weight | Usage |
|-------|------|--------|-------|
| `brand` | 1.04rem (~16.6px) | Bold | Logo |
| `title` | 1.22rem (~19.5px) | Bold | Phase title |
| `body` | .76-.8rem (~12-12.8px) | Normal | Body text, list items |
| `small` | .62-.7rem (~10-11.2px) | Normal | Labels, badges |
| `stat-value` | .94rem (~15px) | Bold | Status values |
| `stat-label` | .62rem (~10px) | Normal | Status labels |
| `button` | .72-.74rem (~11.5-11.8px) | Bold | All buttons |
| `modal-title` | 1rem (~16px) | Bold | Modal headers |
| `log` | .7rem (~11.2px) | Normal | Event log |

---

## 10. Forbidden Offsets

The following must NOT be changed by DA:

1. **A-F region order and relative positions** — TopStatusBar must be at top, PhaseRail left, StageDesktop center, ContextPanel right, BottomQueryBar bottom.
2. **TopStatusBar stat item order** — 国库 → 派系 → 影响力 → 稳定度 → 战争, in that exact sequence.
3. **PhaseRail width** — Fixed 92px, not less, not more.
4. **ContextPanel width** — Fixed 286px, not less.
5. **Region background colors** — Deep-ink shell for TopStatusBar, PhaseRail, ContextPanel, BottomQueryBar. Ivory desktop for StageDesktop.
6. **StageDesktop must use transparent backgrounds inside** — Phase stage components must not re-apply panel background colors.
7. **No structural re-parenting** — GameShell component tree hierarchy must be preserved.
8. **No changes to font token sizes** without SA approval.
9. **No round-info pill removal** — Round info is a standalone element, not merged into stat items.
10. **StepBar colors** — done `#228B22`, current `#E8B84B`, todo `#E8D5C4`.

---

## 11. Pixel-Level Acceptance Table

| Region | Contract Value | Actual Value | Δ | Pass |
|--------|---------------|-------------|---|---|
| A x/y/w/h | 10 / 10 / 1420 / 62 | | | |
| B x/y/w/h | 10 / 82 / 92 / 736 | | | |
| C x/y/w/h | 112 / 82 / 1022 / 736 | | | |
| D x/y/w/h | 1144 / 82 / 286 / 736 | | | |
| E x/y/w/h | 10 / 828 / 1420 / 62 | | | |
| F w/h | 180 / 34 | | | |
| A border-radius | 10 | | | |
| B border-radius | 10 | | | |
| C border-radius | 10 | | | |
| D border-radius | 10 | | | |
| E border-radius | 10 | | | |
| A height | 62 | | | |
| B width | 92 | | | |
| D width | 286 | | | |
| E height | 62 | | | |
| main-wrapper padding | 10 | | | |
| B-C gap | 10 | | | |
| C-D gap | 10 | | | |
| C padding | 18 | | | |

---

## 12. Source References

- HTML prototype: `EOR_GUI_Prototype_v3.25.1.html`
- Design guidelines: `EOR_GUI_Design_Guidelines_Codex_v4.0.md`
- QML shell files: `src/ui/gui/qml/shell/`
- Task template: `EOR_GUI_SA-DA_开发任务书规范模板_v1.1.md`
