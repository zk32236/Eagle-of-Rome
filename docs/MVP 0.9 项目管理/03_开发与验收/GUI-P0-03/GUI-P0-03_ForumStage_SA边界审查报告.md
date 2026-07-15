# GUI-P0-03 ForumStage SA边界审查报告

日期：2026-07-13
状态：PASS，可进入 DA 开发
审查对象：GUI-P0-03 ForumStage
目标版本：EOR GUI v3.25.1 Phase 3

---

## 1. 边界结论

GUI-P0-03 可以启动。任务边界是：在既有 GUI Shell、StageDesktop、GuiSessionStore、GuiApiAdapter 架构内接入广场阶段，不修改内核业务规则。

`forum_api.py` 已具备主要写操作：`retire_figure`、`recruit_figure`、`place_bid`、`buy_land`、`vote_triumph`、`resolve_forum`。本任务只允许补齐 GUI 所需的只读 DTO：`get_forum_view()`。

## 2. 允许修改文件

| 文件 | 允许改动 |
| --- | --- |
| `src/api/forum_api.py` | 新增 `get_forum_view()` 及 DTO 辅助函数 |
| `src/api/session_api.py` | 将 `forum` 加入已实现阶段、更新阶段描述与可用 action |
| `src/ui/gui/api_adapter.py` | 新增 forum 查询和操作封装 |
| `src/ui/gui/session_store.py` | 新增 forum 缓存属性、刷新方法、Slot |
| `src/ui/gui/qml/shell/GameShell.qml` | 注册 ForumStage、添加 Phase3 header/step/action 层 |
| `src/ui/gui/qml/stages/ForumStage.qml` | 新建 Phase 3 内容组件 |
| `src/ui/gui/localization.py` | 补充 forum 相关文案 key |
| `src/tests/test_gui/` | 新增/调整 GUI、Store、结构归位测试 |
| `src/tests/test_api/` | 新增 forum DTO 测试 |

## 3. 禁止修改文件

| 文件/目录 | 禁止原因 |
| --- | --- |
| `src/core/` | 内核规则已存在，本阶段不得修改 |
| `src/core/entities/` | 不新增或改变实体字段 |
| `src/core/systems/` | 不改变政治、战争、经济系统 |
| `src/core/service/` | 不改变服务层结算逻辑 |
| `src/ui/gui/qml/Main.qml` | 应用入口不属于本阶段 |
| 其他阶段 QML | 除必要注册外，不重构 Mortality/Revenue/Population/Senate |

## 4. 架构边界

| 层级 | 本阶段职责 | 禁止 |
| --- | --- | --- |
| QML | 展示 DTO、触发 Store Slot | 不直接调用 API/Core |
| GuiSessionStore | 缓存 forum DTO、暴露属性和 Slot | 不写业务规则 |
| GuiApiAdapter | 统一调用 forum_api 并映射反馈 | 不绕过 API response |
| forum_api | 既有写操作 + 新增只读 DTO | 不复制 core 规则 |
| Core/System/Service/Entity | 保持不动 | 不修改 |

## 5. A-F 不回退清单

| 类型 | 区域 | 要求 |
| --- | --- | --- |
| 保持项 | A TopStatusBar | 不改高度、分块、顺序、占位策略 |
| 保持项 | B PhaseRail | 保持 7 阶段顺序和 pill/nav 样式 |
| 允许项 | C StageDesktop | 只替换当前阶段的 header/instruction/content/action 内容 |
| 保持项 | D ContextPanel | 不重排右栏结构；只允许通过现有 summary/action/status 反映 forum 状态 |
| 保持项 | E BottomQueryBar | 不改 12 个查询入口顺序和样式 |
| 允许项 | F MainAction | 为 forum 增加底部主按钮，但必须保持底部居中操作槽语义 |

## 6. 结构归位要求

| 关键内容 | 应挂载容器 | 验证方式 |
| --- | --- | --- |
| `forumStage` | `stageContainer` | QML startup 结构测试 |
| `forumActionLayer` | `centerPanel` 底部动作层 | QML startup 结构测试 |
| `stageAnnouncement` | `stageHeaderSlot` | 既有结构测试不回退 |
| `stageContainer` | `stageContentSlot` | 既有结构测试不回退 |

## 7. DTO 要求

`forum_api.get_forum_view(state, viewer_player_id)` 必须返回统一 API response，data 至少包含：

```python
{
    "phase_id": "forum",
    "current_player_id": str,
    "viewer_player_id": str,
    "current_step": str,
    "my_figures": list,
    "available_figures": list,
    "pending_contracts": list,
    "land_sale_quota": int,
    "triumph_wars": list,
    "can_execute": bool,
    "can_advance": bool,
    "step1_complete": bool,
    "step2_complete": bool,
    "resolved": bool,
    "resolution_results": list,
}
```

## 8. 测试要求

| 类型 | 要求 |
| --- | --- |
| API | `get_forum_view()` 成功、权限/视角字段、列表字段完整 |
| Adapter/Store | adapter 能获取 forum view，store 能刷新并暴露属性 |
| QML startup | ForumStage 对象存在且结构归位 |
| 回归 | `src/tests` 全量通过 |

## 9. 审查结论

PASS。可进入 DA 开发，但必须严格遵守：不改 core、不重排 Shell、不让 QML 承担业务规则。
