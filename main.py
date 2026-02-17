import sys
import os


def main():
    # 添加src到Python路径（关键！避免导入错误）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(current_dir, 'src'))

    try:
        # 启动Debug CLI
        from ui.debug_cli import DebugCLI
        cli = DebugCLI()
        cli.run()

    except Exception as e:
        # 打印完整错误堆栈
        import traceback
        print("\n" + "=" * 60)
        print("❌ ERROR OCCURRED - Full Traceback:")
        print("=" * 60)
        traceback.print_exc()
        print("=" * 60)
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {e}")
        print("=" * 60)

        # 暂停以便查看错误
        input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()