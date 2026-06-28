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
from src.ui.gui.app import GuiApp


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    logger = logging.getLogger("EOR-GUI")
    logger.info("Starting Eagle of Rome GUI...")

    # 创建 GUI 原型会话
    result = session_api.create_gui_prototype_session()
    if not result.get("success"):
        logger.error(f"Failed to create session: {result.get('message')}")
        print(f"ERROR: {result.get('message')}", file=sys.stderr)
        return 1

    state = result["data"]["state"]
    human_players = result["data"]["human_players"]
    logger.info(f"Session created. Human players: {human_players}")

    # 启动 GUI
    app = GuiApp(state)
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
