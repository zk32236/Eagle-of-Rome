# MVP0.4-06-sys — Config 配置管理系统 Technical Mapping

## 1. 代码目录
```
src/core/config.py              # Config 类 (核心)
src/ui/commands/sys_config.py   # ReloadCommand / TermsCommand
```

## 2. 关键类
- `Config` — get(), reload(), to_dict(), _deep_merge()

## 3. 核心算法
点号路径解析: "section.key.subkey" → 逐级访问
加载顺序: DEFAULTS → JSON 配置文件

## 4. 版本日志
| v1.0 | 2026-07-12 | 初版 |
