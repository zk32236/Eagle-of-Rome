# src/tests/test_core/test_i18n.py
import pytest
import json
import tempfile
import os
from src.core.i18n import I18n

@pytest.fixture
def temp_i18n_file():
    """创建临时 i18n JSON 文件"""
    data = {
        "test_key": "测试值 {param}",
        "another_key": "另一个值"
    }
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
        temp_path = f.name
    yield temp_path
    os.unlink(temp_path)

def test_i18n_load_and_get(temp_i18n_file):
    """测试加载和获取文本"""
    i18n = I18n()
    # 由于单例，需要重置内部状态（测试专用）
    i18n._strings = {}
    # 临时修改 load 方法读取测试文件
    original_load = i18n.load
    def mock_load(lang="zh-CN"):
        with open(temp_i18n_file, 'r', encoding='utf-8') as f:
            i18n._strings = json.load(f)
    i18n.load = mock_load
    i18n.load()
    assert i18n.get("test_key", param="hello") == "测试值 hello"
    assert i18n.get("another_key") == "另一个值"
    assert i18n.get("missing_key", default="默认") == "默认"
    # 恢复原方法
    i18n.load = original_load

def test_i18n_missing_key_no_default():
    """测试缺失键且无默认值时返回键名"""
    i18n = I18n()
    i18n._strings = {}
    assert i18n.get("missing") == "missing"

def test_i18n_format_missing_param():
    """测试格式化参数缺失时返回原文本"""
    i18n = I18n()
    i18n._strings = {"test": "value {param}"}
    # 不提供 param，应返回原文本（或可记录警告，但不应崩溃）
    result = i18n.get("test")
    assert result == "value {param}"  # 或可根据实现返回原文本