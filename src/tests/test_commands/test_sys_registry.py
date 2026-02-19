# src/tests/test_commands/test_sys_registry.py
"""
CommandRegistry 单元测试
使用 pytest 和 tmp_path 动态生成测试命令文件
"""

import pytest
import sys
import os
from pathlib import Path

# 确保 src 在路径中
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.ui.commands.sys_registry import CommandRegistry
from src.ui.commands.sys_base import Command


# ===== 辅助函数：创建临时命令文件 =====

def create_command_file(tmp_path, filename, content):
    """在临时目录中创建命令文件"""
    file_path = tmp_path / filename
    file_path.write_text(content, encoding='utf-8')
    return file_path


# ===== 测试用例 =====

def test_normal_scan(tmp_path):
    """正常扫描：应发现两个命令"""
    content1 = '''
from src.ui.commands.sys_base import Command

class CmdA(Command):
    name = "cmda"
    aliases = ["a"]
    description = "Command A"
    def execute(self, args): return True
'''
    content2 = '''
from src.ui.commands.sys_base import Command

class CmdB(Command):
    name = "cmdb"
    aliases = ["b"]
    description = "Command B"
    def execute(self, args): return True
'''
    create_command_file(tmp_path, "cmd_a.py", content1)
    create_command_file(tmp_path, "cmd_b.py", content2)

    registry = CommandRegistry(str(tmp_path))
    names = registry.get_command_names()
    assert "cmda" in names
    assert "a" in names
    assert "cmdb" in names
    assert "b" in names


def test_skip_private(tmp_path):
    """跳过私有文件（以下划线开头）"""
    content = '''
from src.ui.commands.sys_base import Command

class PrivateCmd(Command):
    name = "private"
    aliases = ["p"]
    description = "Should be ignored"
    def execute(self, args): return True
'''
    create_command_file(tmp_path, "_private.py", content)

    registry = CommandRegistry(str(tmp_path))
    names = registry.get_command_names()
    assert "private" not in names
    assert "p" not in names


def test_import_fail_skip(tmp_path, capsys):
    """导入失败的文件被跳过，打印警告"""
    bad_content = "this is not valid python"
    create_command_file(tmp_path, "bad_syntax.py", bad_content)

    # 正常文件
    good_content = '''
from src.ui.commands.sys_base import Command

class GoodCmd(Command):
    name = "good"
    aliases = ["g"]
    description = "Good"
    def execute(self, args): return True
'''
    create_command_file(tmp_path, "good.py", good_content)

    registry = CommandRegistry(str(tmp_path))
    captured = capsys.readouterr()
    assert "导入失败" in captured.out or "WARN" in captured.out

    names = registry.get_command_names()
    assert "good" in names
    assert "bad_syntax" not in names


def test_multiple_commands_one_file(tmp_path):
    """单个文件包含多个命令类，应全部注册"""
    content = '''
from src.ui.commands.sys_base import Command

class CmdOne(Command):
    name = "one"
    aliases = ["o"]
    description = "First"
    def execute(self, args): return True

class CmdTwo(Command):
    name = "two"
    aliases = ["t"]
    description = "Second"
    def execute(self, args): return True
'''
    create_command_file(tmp_path, "multi.py", content)

    registry = CommandRegistry(str(tmp_path))
    names = registry.get_command_names()
    assert "one" in names
    assert "o" in names
    assert "two" in names
    assert "t" in names


def test_name_conflict(tmp_path):
    """主名冲突应抛出 ValueError"""
    content1 = '''
from src.ui.commands.sys_base import Command

class CmdA(Command):
    name = "conflict"
    aliases = ["a"]
    def execute(self, args): return True
'''
    content2 = '''
from src.ui.commands.sys_base import Command

class CmdB(Command):
    name = "conflict"
    aliases = ["b"]
    def execute(self, args): return True
'''
    create_command_file(tmp_path, "file1.py", content1)
    create_command_file(tmp_path, "file2.py", content2)

    with pytest.raises(ValueError, match="命令名冲突.*conflict"):
        CommandRegistry(str(tmp_path))


def test_alias_conflict(tmp_path):
    """别名冲突应抛出 ValueError"""
    content1 = '''
from src.ui.commands.sys_base import Command

class CmdA(Command):
    name = "cmda"
    aliases = ["x"]
    def execute(self, args): return True
'''
    content2 = '''
from src.ui.commands.sys_base import Command

class CmdB(Command):
    name = "cmdb"
    aliases = ["x"]
    def execute(self, args): return True
'''
    create_command_file(tmp_path, "file1.py", content1)
    create_command_file(tmp_path, "file2.py", content2)

    with pytest.raises(ValueError, match="别名冲突.*x"):
        CommandRegistry(str(tmp_path))


def test_alias_name_conflict(tmp_path):
    """命令A的别名等于命令B的主名，应冲突（抛出命令名冲突）"""
    content1 = '''
from src.ui.commands.sys_base import Command

class CmdA(Command):
    name = "cmda"
    aliases = ["b"]
    def execute(self, args): return True
'''
    content2 = '''
from src.ui.commands.sys_base import Command

class CmdB(Command):
    name = "b"
    aliases = []
    def execute(self, args): return True
'''
    create_command_file(tmp_path, "file1.py", content1)
    create_command_file(tmp_path, "file2.py", content2)

    with pytest.raises(ValueError, match="命令名冲突.*b"):
        CommandRegistry(str(tmp_path))


def test_execute_exception(tmp_path, capsys):
    """命令执行抛出异常应被捕获并返回 False"""
    content = '''
from src.ui.commands.sys_base import Command

class ErrorCmd(Command):
    name = "error"
    aliases = ["e"]
    description = "Always throws"
    def execute(self, args):
        raise ValueError("simulated error")
'''
    create_command_file(tmp_path, "error.py", content)

    registry = CommandRegistry(str(tmp_path))

    # 执行命令，传入 state=None
    result = registry.execute("error", None, [])
    assert result is False

    captured = capsys.readouterr()
    assert "命令执行错误 (error)" in captured.out
    assert "simulated error" in captured.out


def test_get_command_names(tmp_path):
    """get_command_names 应返回所有键（主名+别名）"""
    content = '''
from src.ui.commands.sys_base import Command

class TestCmd(Command):
    name = "test"
    aliases = ["t", "ts"]
    description = "Test"
    def execute(self, args): return True
'''
    create_command_file(tmp_path, "test.py", content)

    registry = CommandRegistry(str(tmp_path))
    names = registry.get_command_names()
    assert set(names) == {"test", "t", "ts"}


def test_get_command_info(tmp_path):
    """get_command_info 应通过主名和别名都能获取信息"""
    content = '''
from src.ui.commands.sys_base import Command

class InfoCmd(Command):
    name = "info"
    aliases = ["i", "inf"]
    description = "Info command"
    def execute(self, args): return True
'''
    create_command_file(tmp_path, "info.py", content)

    registry = CommandRegistry(str(tmp_path))

    # 通过主名
    info = registry.get_command_info("info")
    assert info is not None
    assert info["name"] == "info"
    assert info["aliases"] == ["i", "inf"]
    assert info["description"] == "Info command"

    # 通过别名
    info_alias = registry.get_command_info("i")
    assert info_alias is not None
    assert info_alias["name"] == "info"

    info_alias2 = registry.get_command_info("inf")
    assert info_alias2 is not None
    assert info_alias2["name"] == "info"

    # 不存在的命令
    assert registry.get_command_info("nonexistent") is None