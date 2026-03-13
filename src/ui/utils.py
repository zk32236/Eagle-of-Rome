# src/ui/utils.py
def get_progress_bar(state, width=7):
    """生成进度条字符串，格式：[▓▓▓░░░░] 已执行/总数"""
    executed = len(state.executed_phases)
    total = 7
    filled = "▓" * executed
    empty = "░" * (total - executed)
    return f"[{filled}{empty}] {executed}/{total}"