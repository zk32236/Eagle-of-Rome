# MVP0.5-18-sys — 状态查询命令扩展（技术映射）

## 1. 代码目录
```
src/ui/commands/func_status.py    # 6个查询命令
src/api/game_api.py, figure_api.py, faction_api.py, province_api.py, contract_api.py
src/api/session_api.py, gui_query_api.py
```

## 2. 命令列表
- status/sts — 全局概要
- status_public_land/spl — 公地信息
- status_private_land/spr — 私地信息
- status_figure/sf — 人物查询
- factions/fs — 派系查询
- province/prov — 行省查询

## 3. 版本日志 | v1.0 | 2026-07-17 | 初版 |
