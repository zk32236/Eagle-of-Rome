# src/ui/debug_cli.py
"""
调试命令行界面 - 阶段1重构版（支持强制阶段顺序、进度条、i18n）
"""

import sys
import os
import traceback
import logging
import datetime
from typing import Optional

from src.core.i18n import i18n
from src.ui.commands.sys_registry import CommandRegistry
from src.core.game_state import GameState
from src.core.entities.player import PlayerType
from src.api import game_api

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 阶段顺序和显示名称
PHASE_SEQUENCE = ["mortality", "revenue", "forum", "population", "senate", "combat", "resolution"]
PHASE_DISPLAY_NAMES = {
    "mortality": "天命阶段",
    "revenue": "收入阶段",
    "forum": "广场阶段",
    "population": "人口阶段",
    "senate": "元老院阶段",
    "combat": "战斗阶段",
    "resolution": "决算阶段",
}

# 单字母别名映射
PHASE_ALIASES = {
    "m": "mortality",
    "r": "revenue",
    "f": "forum",
    "p": "population",
    "s": "senate",
    "c": "combat",
    "x": "resolution",
}


class Tee:
    """将输出同时写入文件和原始 stdout"""
    def __init__(self, filename, mode='a', encoding='utf-8'):
        self.file = open(filename, mode, encoding=encoding)
        self.stdout = sys.stdout

    def write(self, message):
        self.stdout.write(message)
        self.stdout.flush()   # 立即刷新终端
        self.file.write(message)
        self.file.flush()

    def flush(self):
        self.stdout.flush()
        self.file.flush()

    def close(self):
        self.file.close()
        sys.stdout = self.stdout


class DebugCLI:
    """调试命令行界面"""

    def __init__(self):
        """初始化CLI"""
        self.state = GameState("data/config/game_config.json")
        # 从配置读取语言
        lang = self.state.config.get("language", "zh-CN")
        i18n.load(lang)

        self.running = True

        # 初始化命令注册器
        commands_dir = os.path.join(os.path.dirname(__file__), "commands")
        self.registry = CommandRegistry(commands_dir)

        # 为特殊命令设置回调
        self._setup_special_commands()

    def _get_prompt_prefix(self) -> str:
        """返回提示符前缀，如 [Player1] """
        self._ensure_interactive_player()
        player = self.state.get_current_player()
        if player:
            faction = self.state.get_faction(player.faction_id)
            faction_name = faction.name if faction else "无派系"
            return f"[{player.player_id} {faction_name}] "
        return "> "

    def _ensure_interactive_player(self) -> None:
        """交互式 CLI 中避免 AI 玩家长期占据顶层 current player。"""
        player = self.state.get_current_player()
        if not player or player.player_type != PlayerType.AI:
            return
        human_player = next(
            (p for p in self.state.get_all_players() if p.player_type == PlayerType.HUMAN),
            None
        )
        if not human_player:
            return
        old_id = player.player_id
        self.state.set_current_player(human_player.player_id)
        self.state.log_event(
            "CLI current player restored to human player",
            level=logging.DEBUG,
            extra={
                "from_player": old_id,
                "to_player": human_player.player_id,
                "reason": "interactive_prompt_ai_player"
            }
        )

    def _get_next_phase(self) -> Optional[str]:
        """返回下一个未执行的阶段名，若全部执行则返回None"""
        for phase in PHASE_SEQUENCE:
            if not self.state.is_phase_executed(phase):
                return phase
        return None

    # src/ui/debug_cli.py
    def _execute_phase_with_ui(self, phase_name: str) -> bool:
        self._ensure_interactive_player()
        player = self.state.get_current_player()
        if not player:
            print("当前没有玩家")
            return False
        year_display = self.state.turn.get_year_display() if self.state.turn else "未知"
        phase_display = PHASE_DISPLAY_NAMES.get(phase_name, phase_name)
        executed_before = len(self.state.executed_phases)
        total = len(PHASE_SEQUENCE)

        # 广场阶段不打印标题和预览（避免与 UI_03-0 重复）
        if not (phase_name == "forum"):
            print("\n" + "#" * 60)
            print(
                f" 回合 {self.state.turn.turn_number} ({year_display}) - {phase_display} [{executed_before + 1}/{total}]")
            print("#" * 60 + "\n")

            preview_key = f"phase_{phase_name}_preview"
            preview = i18n.get(preview_key, default="")
            if preview and preview != preview_key:
                print(preview)
                print()

        sys.stdout.flush()
        result = game_api.execute_phase(self.state, phase_name, player.player_id)

        if not result["success"]:
            print(i18n.get("error_phase_exec_failed", msg=result["message"]))
            return False

        executed_after = len(self.state.executed_phases)
        filled = "▓" * executed_after
        empty = "░" * (total - executed_after)
        progress = i18n.get("progress_bar", filled=filled, empty=empty, executed=executed_after, total=total)
        print(f"\nProgress: {progress}")
        return True

    def _do_turn(self):
        if not self.state:
            print(i18n.get("error_no_state"))
            return
        # 循环执行所有未执行阶段（不使用 game_api.execute_turn，因为我们需要每个阶段的 UI）
        while True:
            next_phase = self._get_next_phase()
            if not next_phase:
                break
            success = self._execute_phase_with_ui(next_phase)
            if not success:
                break

    def _do_step(self):
        if not self.state:
            print(i18n.get("error_no_state"))
            return
        next_phase = self._get_next_phase()
        if not next_phase:
            print(i18n.get("error_phase_already_done"))
            return
        self._execute_phase_with_ui(next_phase)

    def _do_next(self):
        if not self.state:
            print(i18n.get("error_no_state"))
            return
        if len(self.state.executed_phases) < len(PHASE_SEQUENCE):
            print(i18n.get("error_phase_not_complete"))
            return
        player = self.state.get_current_player()
        if not player:
            print("当前没有玩家")
            return
        result = game_api.advance_year(self.state, player.player_id)
        if result["success"]:
            print(result["message"])
        else:
            print(result["message"])
        year_display = self.state.turn.get_year_display() if self.state.turn else "未知"
        print(f"\n📅 Year {year_display}:")
        print(f"   Completed: 0/{len(PHASE_SEQUENCE)} phases")

    def _setup_special_commands(self):
        """设置特殊命令的回调"""
        help_info = self.registry.get_command_info("help")
        if help_info:
            self._help_class = help_info['class']
        exit_info = self.registry.get_command_info("exit")
        if exit_info:
            self._exit_class = exit_info['class']

    def _create_command_instance(self, cmd_name: str):
        """
        创建命令实例并设置必要的回调
        """
        cmd_info = self.registry.get_command_info(cmd_name)
        if not cmd_info:
            return None
        cmd_class = cmd_info['class']
        instance = cmd_class(self.state)
        if cmd_class.name == "help":
            instance.set_registry(self.registry)
        elif cmd_class.name == "exit":
            instance.set_exit_callback(self._stop)
        return instance

    def _stop(self):
        self.running = False

    def run(self):
        """运行CLI主循环，同时将输出保存到日志文件"""
        # 设置 CLI 输出日志
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = os.path.join(project_root, "logs")
        os.makedirs(log_dir, exist_ok=True)
        cli_log_path = os.path.join(log_dir, f"cli_{timestamp}.log")
        tee = Tee(cli_log_path)
        sys.stdout = tee

        try:
            # 自动加载默认场景
            print(i18n.get("auto_load_scenario", default="🔄 自动加载默认场景..."))
            self.registry.execute("load", self.state, [])

            print(i18n.get("help_prompt"))
            print()

            while self.running:
                try:
                    cmd_input = input(self._get_prompt_prefix()).strip()
                    if not cmd_input:
                        continue

                    parts = cmd_input.split()
                    raw_cmd = parts[0].lower()
                    args = parts[1:] if len(parts) > 1 else []

                    # 将别名转换为阶段名
                    cmd_name = PHASE_ALIASES.get(raw_cmd, raw_cmd)

                    sys.stdout.flush()

                    # 处理内置命令
                    if cmd_name == "turn":
                        self._do_turn()
                    elif cmd_name == "step":
                        self._do_step()
                    elif cmd_name == "next":
                        self._do_next()
                    elif cmd_name in PHASE_SEQUENCE:
                        # 直接执行阶段，使用 UI 包装

                        sys.stdout.flush()
                        self._execute_phase_with_ui(cmd_name)

                        sys.stdout.flush()
                    else:
                        cmd_instance = self._create_command_instance(cmd_name)
                        if cmd_instance:
                            result = cmd_instance.execute(args)
                            if cmd_name in ["exit", "quit"] and not result:
                                self._stop()
                        else:
                            print(i18n.get("unknown_command", cmd=raw_cmd))
                            print(i18n.get("help_prompt"))

                except EOFError:
                    print("\n输入流已关闭，退出。")
                    break
                except KeyboardInterrupt:
                    print("\n使用 'exit' 命令退出游戏")
                    continue
                except Exception as e:
                    state_info = ""
                    if self.state and hasattr(self.state, 'turn') and self.state.turn:
                        turn_info = f"回合 {self.state.turn.turn_number}"
                        year_info = f"年份 {abs(self.state.turn.year)} BC"
                        state_info = f"{turn_info} {year_info}"
                    if self.state and hasattr(self.state, 'log_event'):
                        tb_str = traceback.format_exc()
                        self.state.log_event(
                            f"未捕获异常: 命令 '{cmd_input}' - {str(e)}",
                            level=logging.ERROR,
                            extra={
                                "context": state_info,
                                "cmd": cmd_input,
                                "exception": str(e),
                                "traceback": tb_str
                            }
                        )
                    print(f"发生未预期错误: {e}")
                    traceback.print_exc()
        finally:
            sys.stdout = tee.stdout
            tee.close()
            print(i18n.get("cli_shutdown", default="CLI已关闭"))
            print("CLI 输出日志已保存至:", cli_log_path)

    def shutdown(self):
        self.running = False
        print(i18n.get("cli_shutdown", default="CLI已关闭"))


def main():
    cli = DebugCLI()
    try:
        cli.run()
    finally:
        cli.shutdown()


if __name__ == "__main__":
    main()
