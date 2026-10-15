#!/usr/bin/env python
"""
gui_main.py
Eagle of Rome GUI 启动入口。

启动命令:
    python gui_main.py

环境:
    Python 3.10, PySide6 6.8.3
"""
import sys
import os
import logging

# 将项目根目录加入 Python 路径
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.api import session_api
from src.core.scenario_validation import DEFAULT_SCENARIO_FILE
from src.ui.gui.app import GuiApp


def _extract_scenario(argv):
    """Parse the application-level ``--scenario`` option out of ``argv``.

    Returns ``(scenario_file_or_None, forwarded_argv)``. The selected scenario is a
    bare filename under ``data/scenarios`` (validated later by the session factory).
    The option is stripped before Qt sees the remaining arguments.
    """
    scenario = None
    forwarded = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--scenario":
            if i + 1 >= len(argv):
                raise ValueError("--scenario requires a value")
            value = argv[i + 1]
            if value == "":
                # 显式空值（分离式空参）≠ 未提供：拒绝，绝不替换为默认。
                raise ValueError("--scenario requires a non-empty value")
            scenario = value
            i += 2
            continue
        if arg.startswith("--scenario="):
            value = arg.split("=", 1)[1]
            if value == "":
                # 显式空值（`--scenario=`）≠ 未提供：拒绝，绝不替换为默认。
                raise ValueError("--scenario requires a non-empty value")
            scenario = value
            i += 1
            continue
        forwarded.append(arg)
        i += 1
    return scenario, forwarded


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    logger = logging.getLogger("EOR-GUI")
    logger.info("Starting Eagle of Rome GUI...")

    # 解析应用级场景选择参数（GR-F10）；Qt 参数原样转发
    try:
        scenario_file, qt_argv = _extract_scenario(sys.argv)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if scenario_file is None:
        # 仅「未提供 --scenario」时使用历史默认（1H/2AI）。显式空值在
        # _extract_scenario 已抛错（main 返回 2），这里绝不再把空串当作缺省。
        scenario_file = DEFAULT_SCENARIO_FILE

    # 创建 GUI 原型会话（受校验 loader；非法场景 → 失败，不回退）
    result = session_api.create_gui_prototype_session(
        config_path="data/config/game_config.json",
        scenario_file=scenario_file,
    )
    if not result.get("success"):
        logger.error(f"Failed to create session: {result.get('message')}")
        print(f"ERROR: {result.get('message')}", file=sys.stderr)
        return 1

    state = result["data"]["state"]
    human_players = result["data"]["human_players"]
    logger.info(f"Session created ({scenario_file}). Human players: {human_players}")

    # 启动 GUI（只转发剔除 --scenario 后的参数）
    app = GuiApp(state)
    return app.run(qt_argv)


if __name__ == "__main__":
    sys.exit(main())
