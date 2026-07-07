# src/ui/commands/sys_registry.py
"""
命令注册中心 - 自动扫描、注册、执行
"""

import sys
import os
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Type, Any, Set
from types import ModuleType

from src.ui.commands.sys_base import Command
from src.core.game_state import GameState

project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class CommandRegistry:
    """命令注册中心 - 自动扫描、注册、执行"""

    def __init__(self, commands_dir: str):
        self._commands: Dict[str, Type[Command]] = {}
        self._registered_classes: Set[int] = set()  # 记录已注册类的 id，防止重复
        self._scan_and_register(commands_dir)

    # ========== 核心步骤1: 扁平扫描 ==========

    def _scan_and_register(self, directory: str):
        dir_path = Path(directory).resolve()
        if not dir_path.exists():
            print(f"[WARN] 命令目录不存在: {directory}")
            return

        processed_paths = set()
        for file_path in dir_path.glob("*.py"):
            abs_path_lower = str(file_path.resolve()).lower()
            if abs_path_lower in processed_paths:
                continue
            processed_paths.add(abs_path_lower)

            if file_path.name.startswith("_"):
                continue

            module = self._load_module(file_path)
            if not module:
                continue

            for cmd_class in self._extract_commands(module):
                self._register(cmd_class)

    # ========== 核心步骤2: 动态导入（异常隔离）==========

    def _load_module(self, file_path: Path) -> Optional[ModuleType]:
        """
        动态导入模块，使用完整包路径作为模块名，避免与 sys.modules 中的冲突
        """
        try:
            module_name = f"src.ui.commands.{file_path.stem}"

            if module_name in sys.modules:
                return sys.modules[module_name]

            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                print(f"[WARN] 无法加载模块: {file_path.name}")
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            sys.modules[module_name] = module
            return module
        except Exception as e:
            print(f"[WARN] 命令文件导入失败 {file_path.name}: {e}")
            return None

    # ========== 核心步骤3: 类识别 ==========

    def _extract_commands(self, module: ModuleType) -> List[Type[Command]]:
        commands = []
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and
                issubclass(attr, Command) and
                attr is not Command and
                hasattr(attr, 'name')):
                commands.append(attr)
        return commands

    # ========== 核心步骤4: 注册与重复检测（Fail Fast）==========

    def _register(self, cmd_class: Type[Command]):
        # 类级别去重：避免同一个类被注册两次
        class_id = id(cmd_class)
        if class_id in self._registered_classes:
            return
        self._registered_classes.add(class_id)

        name = cmd_class.name
        if name in self._commands:
            existing_file = self._commands[name].__module__
            raise ValueError(
                f"命令名冲突: '{name}' 已存在于 {existing_file}\n"
                f"新命令: {cmd_class.__module__}"
            )

        self._commands[name] = cmd_class

        aliases = getattr(cmd_class, 'aliases', [])
        for alias in aliases:
            if alias in self._commands:
                existing_file = self._commands[alias].__module__
                raise ValueError(
                    f"别名冲突: '{alias}' 已被 {existing_file} 使用\n"
                    f"新别名: {cmd_class.__module__}.{name}"
                )
            self._commands[alias] = cmd_class

    # ========== 命令执行接口 ==========

    def execute(self, cmd_name: str, state: Optional[GameState], args: List[str]) -> bool:
        cmd_class = self._commands.get(cmd_name)
        if not cmd_class:
            print(f"未知命令: {cmd_name}，输入 'help' 查看可用命令")
            return False

        instance = cmd_class(state)

        try:
            return instance.execute(args)
        except Exception as e:
            print(f"命令执行错误 ({cmd_name}): {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_command_names(self) -> List[str]:
        return list(self._commands.keys())

    def get_command_info(self, cmd_name: str) -> Optional[Dict[str, Any]]:
        cmd_class = self._commands.get(cmd_name)
        if not cmd_class:
            return None
        return {
            'name': cmd_class.name,
            'aliases': getattr(cmd_class, 'aliases', []),
            'description': getattr(cmd_class, 'description', ''),
            'class': cmd_class
        }