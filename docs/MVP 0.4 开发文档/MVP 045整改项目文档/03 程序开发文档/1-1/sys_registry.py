# src/ui/commands/sys_registry.py
"""
命令注册中心 - 自动扫描、注册、执行

核心功能:
1. 扁平扫描 commands 目录下的所有 .py 文件
2. 动态导入模块，提取继承 Command 的子类
3. 注册命令（主名和别名），检测冲突（Fail Fast）
4. 提供命令执行接口，异常内部消化
"""

import os
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Type, Any
from types import ModuleType

from src.ui.commands.sys_base import Command
from core.game_state import GameState


class CommandRegistry:
    """命令注册中心 - 自动扫描、注册、执行"""

    def __init__(self, commands_dir: str):
        """
        初始化注册中心，自动扫描并注册命令

        Args:
            commands_dir: 命令文件所在目录路径（相对或绝对）

        Raises:
            ValueError: 命令名或别名冲突时抛出
        """
        self._commands: Dict[str, Type[Command]] = {}  # name -> CommandClass
        self._scan_and_register(commands_dir)

    # ========== 核心步骤1: 扁平扫描 ==========

    def _scan_and_register(self, directory: str):
        """
        扫描目录下所有命令文件并注册

        Args:
            directory: 要扫描的目录路径
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            print(f"[WARN] 命令目录不存在: {directory}")
            return

        # 关键注释: 使用Path.glob仅扫描当前目录，不递归子目录（扁平化要求）
        for file_path in dir_path.glob("*.py"):
            # 关键注释: 跳过私有文件（下划线开头），如__init__.py, _base.py
            if file_path.name.startswith("_"):
                continue

            # 关键注释: 步骤2 - 动态导入，失败隔离（单文件失败不影响其他）
            module = self._load_module(file_path)
            if not module:
                continue  # 导入失败则跳过，继续扫描其他文件

            # 关键注释: 步骤3 - 提取Command子类（单文件单命令约定）
            for cmd_class in self._extract_commands(module):
                # 关键注释: 步骤4 - 注册并检测重复（冲突抛异常，阻止启动）
                self._register(cmd_class)

    # ========== 核心步骤2: 动态导入（规避循环导入） ==========

    def _load_module(self, file_path: Path) -> Optional[ModuleType]:
        """
        动态导入模块，异常隔离

        Args:
            file_path: 要导入的 .py 文件路径

        Returns:
            导入的模块对象，失败返回 None
        """
        try:
            # 关键注释: 使用importlib.util动态导入，避免sys.modules污染
            module_name = file_path.stem  # 文件名作为模块名，如"phase_mortality"

            # 重要: 添加项目根目录到路径，确保绝对导入正常工作
            project_root = str(Path(__file__).parent.parent.parent.parent)
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                print(f"[WARN] 无法加载模块: {file_path.name}")
                return None

            module = importlib.util.module_from_spec(spec)

            # 设置模块的__package__属性，使绝对导入正常工作
            module.__package__ = 'src.ui.commands'

            spec.loader.exec_module(module)  # 执行模块代码
            return module
        except Exception as e:
            # 关键注释: 打印警告但不阻断，确保其他命令正常加载
            print(f"[WARN] 命令文件导入失败 {file_path.name}: {e}")
            return None

    # ========== 核心步骤3: 类识别（过滤非命令类） ==========

    def _extract_commands(self, module: ModuleType) -> List[Type[Command]]:
        """
        从模块中提取Command子类

        Args:
            module: 要检查的模块对象

        Returns:
            继承自Command的类列表
        """
        commands = []
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            # 关键注释: 严格筛选条件：是类、继承Command、不是Command本身、有name属性
            if (isinstance(attr, type) and
                    issubclass(attr, Command) and
                    attr is not Command and
                    hasattr(attr, 'name')):  # 验证必选属性存在
                commands.append(attr)
        return commands

    # ========== 核心步骤4: 注册与重复检测（Fail Fast） ==========

    def _register(self, cmd_class: Type[Command]):
        """
        注册命令，严格检测重复

        Args:
            cmd_class: 要注册的命令类

        Raises:
            ValueError: 主名或别名冲突时抛出
        """
        name = cmd_class.name

        # 关键注释: 主名冲突检测 - 已存在则抛异常，阻止启动（Fail Fast）
        if name in self._commands:
            existing_file = self._commands[name].__module__
            raise ValueError(
                f"命令名冲突: '{name}' 已存在于 {existing_file}\n"
                f"新命令: {cmd_class.__module__}"
            )

        # 关键注释: 注册主名（存储类，非实例 - 延迟实例化）
        self._commands[name] = cmd_class

        # 关键注释: 别名冲突检测 - 与主名同等严格
        aliases = getattr(cmd_class, 'aliases', [])
        for alias in aliases:
            if alias in self._commands:
                existing_file = self._commands[alias].__module__
                raise ValueError(
                    f"别名冲突: '{alias}' 已被 {existing_file} 使用\n"
                    f"新别名: {cmd_class.__module__}.{name}"
                )
            # 关键注释: 别名指向同一类，不创建副本
            self._commands[alias] = cmd_class

    # ========== 命令执行接口 ==========

    def execute(self, cmd_name: str, state: Optional[GameState], args: List[str]) -> bool:
        """
        执行指定命令

        Args:
            cmd_name: 命令名或别名
            state: 游戏状态实例（可能为None）
            args: 命令参数字符串列表

        Returns:
            bool: 命令执行是否成功（业务逻辑层面）
                  命令不存在或执行异常返回 False
        """
        cmd_class = self._commands.get(cmd_name)
        if not cmd_class:
            print(f"未知命令: {cmd_name}，输入 'help' 查看可用命令")
            return False

        # 关键注释: 延迟实例化 - 每次执行创建新实例，确保命令无状态残留
        instance = cmd_class(state)

        try:
            # 关键注释: 执行命令，异常内部消化（不向上抛）
            return instance.execute(args)
        except Exception as e:
            print(f"命令执行错误 ({cmd_name}): {e}")
            import traceback
            traceback.print_exc()  # 调试时打印堆栈，正式版可移除
            return False

    def get_command_names(self) -> List[str]:
        """
        获取所有已注册命令名（去重，主名+别名）

        Returns:
            所有可用的命令名和别名列表
        """
        return list(self._commands.keys())

    def get_command_info(self, cmd_name: str) -> Optional[Dict[str, Any]]:
        """
        获取命令的详细信息

        Args:
            cmd_name: 命令名或别名

        Returns:
            包含命令信息的字典，命令不存在返回 None
        """
        cmd_class = self._commands.get(cmd_name)
        if not cmd_class:
            return None

        return {
            'name': cmd_class.name,
            'aliases': getattr(cmd_class, 'aliases', []),
            'description': getattr(cmd_class, 'description', ''),
            'class': cmd_class
        }


# 需要在文件开头添加sys导入
import sys