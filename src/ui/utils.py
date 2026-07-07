import os
import platform

def get_progress_bar(state, width=7):
    """生成进度条字符串，格式：[▓▓▓░░░░] 已执行/总数"""
    executed = len(state.executed_phases)
    total = 7
    filled = "▓" * executed
    empty = "░" * (total - executed)
    return f"[{filled}{empty}] {executed}/{total}"

def clear_screen():
    """清空终端屏幕（跨平台）"""
    if platform.system() == "Windows":
        os.system('cls')
    else:
        os.system('clear')