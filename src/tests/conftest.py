import sys
from pathlib import Path

# 将当前文件所在目录（src/tests）加入 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

pytest_plugins = ['fixtures.entity_fixtures']