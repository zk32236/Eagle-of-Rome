# main.py
"""
Eagle of Rome 游戏主入口
Eagle of Rome 游戏主入口
MVP 0.4.5 整改后版本
"""

import sys
import os


def main():
    """
    游戏主入口函数
    功能:
    1. 添加src到Python路径（确保导入正确）
    2. 启动Debug CLI
    3. 捕获并处理未预期异常
    """
    # 添加src到Python路径（关键！避免导入错误）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.join(current_dir, 'src')
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    try:
        # 导入并启动整改后的Debug CLI
        from src.ui.debug_cli import DebugCLI
        cli = DebugCLI()
        cli.run()

    except ImportError as e:
        print("\n" + "=" * 60)
        print("❌ 导入错误 - 无法加载必要模块")
        print("=" * 60)
        print(f"错误信息: {e}")
        print(f"Python路径: {sys.path}")
        print("=" * 60)
        input("\n按 Enter 键退出...")
        sys.exit(1)

    except Exception as e:
        # 打印完整错误堆栈
        import traceback
        print("\n" + "=" * 60)
        print("❌ 未预期错误 - 完整堆栈信息:")
        print("=" * 60)
        traceback.print_exc()
        print("=" * 60)
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {e}")
        print("=" * 60)

        # 暂停以便查看错误
        input("\n按 Enter 键退出...")
        sys.exit(1)


if __name__ == "__main__":
    main()