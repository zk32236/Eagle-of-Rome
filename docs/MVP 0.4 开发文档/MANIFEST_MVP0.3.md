# Eagle of Rome MVP 0.3 - 打包清单

## 打包信息
- **版本**: MVP 0.3
- **打包日期**: 2024
- **文件总数**: 约25个文件
- **总大小**: < 500KB（纯代码）

---

## 必需文件清单

### 根目录
```
EagleOfRome_MVP0.3/
├── main.py                 [必需] 程序入口
├── README.md               [必需] 版本说明
└── .gitignore              [建议] Git忽略文件
```

### 源代码 (src/)
```
src/
├── core/
│   ├── __init__.py
│   ├── entities/
│   │   ├── __init__.py     [必需] 实体包导出
│   │   ├── entities.py     [必需] Senator, Faction, GameTurn
│   │   ├── war.py          [必需] War实体
│   │   └── legion.py       [必需] Legion实体
│   ├── phases/
│   │   ├── __init__.py     [必需] 阶段包导出
│   │   ├── mortality_phase.py   [必需]
│   │   ├── revenue_phase.py     [必需]
│   │   ├── forum_phase.py       [必需]
│   │   ├── population_phase.py  [必需]
│   │   ├── senate_phase.py      [必需]
│   │   ├── combat_phase.py      [必需]
│   │   └── resolution_phase.py  [必需]
│   ├── systems/
│   │   ├── __init__.py     [必需] 系统包导出
│   │   ├── war_system.py   [必需] 战争管理
│   │   └── military_system.py   [必需] 军团管理
│   ├── game_state.py       [必需] 游戏状态
│   ├── scenario_loader.py  [必需] 场景加载
│   └── localization.py     [必需] 术语服务
└── ui/
    ├── __init__.py         [必需] UI包导出
    └── debug_cli.py        [必需] 命令行界面
```

### 数据文件 (data/)
```
data/
├── scenarios/
│   └── mvp_test.json       [必需] 测试场景
├── cards/
│   └── wars.json           [必需] 战争卡配置
└── config.json             [必需] 游戏配置
```

---

## 可选文件

### 文档
```
docs/
├── architecture.md         [建议] 架构设计文档
├── changelog.md            [建议] 更新日志
├── api_reference.md        [可选] API参考
└── design_notes.md         [可选] 设计笔记
```

### 测试
```
tests/
├── __init__.py
├── test_entities.py        [建议] 实体单元测试
├── test_phases.py          [建议] 阶段测试
└── test_systems.py         [建议] 系统测试
```

### 工具脚本
```
tools/
├── generate_wars.py        [可选] 战争卡生成器
├── validate_json.py        [可选] JSON验证工具
└── term_checker.py         [可选] 术语检查工具
```

---

## 打包步骤

### 1. 文件检查
```bash
# 检查必需文件是否存在
python -c "import os; files=[...]; [print(f'✓ {f}') if os.path.exists(f) else print(f'✗ {f} MISSING') for f in files]"
```

### 2. 语法检查
```bash
# 检查所有Python文件语法
find src -name "*.py" -exec python -m py_compile {} \;
```

### 3. JSON验证
```bash
# 验证JSON文件
python -c "import json; [json.load(open(f)) for f in ['data/config.json', 'data/scenarios/mvp_test.json', 'data/cards/wars.json']]"
```

### 4. 功能测试
```bash
# 运行基础测试
python main.py
# 输入: load -> status -> help -> exit
```

### 5. 创建发布包
```bash
# 创建版本目录
mkdir EagleOfRome_MVP0.3
cp -r src data main.py README.md EagleOfRome_MVP0.3/

# 打包
zip -r EagleOfRome_MVP0.3.zip EagleOfRome_MVP0.3/
# 或
tar -czvf EagleOfRome_MVP0.3.tar.gz EagleOfRome_MVP0.3/
```

---

## 文件校验 (SHA256)

```
# 生成校验文件
find EagleOfRome_MVP0.3 -type f -exec sha256sum {} \; > checksums.txt
```

---

## 版本标记

在 `src/core/game_state.py` 中添加版本信息：

```python
VERSION = "MVP 0.3"
VERSION_NAME = "Seven Phases & War System"
VERSION_DATE = "2024"
```

---

## 发布检查清单

- [ ] 所有必需文件存在
- [ ] Python语法检查通过
- [ ] JSON文件验证通过
- [ ] 基础功能测试通过（load/status/help/exit）
- [ ] 完整游戏流程测试（7阶段+战斗）
- [ ] 术语切换测试
- [ ] README.md完整
- [ ] 版本号标记
- [ ] 打包文件创建
- [ ] 校验和生成

---

## 安装验证

用户收到包后，应能执行：

```bash
cd EagleOfRome_MVP0.3
python main.py
> load
> status
> terms historical_roman
> help
> exit
```

---

**打包完成！** 🦅
