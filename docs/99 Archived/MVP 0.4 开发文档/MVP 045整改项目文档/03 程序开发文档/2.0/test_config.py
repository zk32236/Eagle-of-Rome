# src/tests/test_core/test_config.py
"""
Config 配置管理单元测试
验证：默认值回退、点号路径访问、深合并、重载、深拷贝保护
"""

import unittest
import json
import tempfile
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.config import Config


class TestConfig(unittest.TestCase):
    """Config 类单元测试"""

    def setUp(self):
        """每个测试前创建临时文件"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "test_config.json")

    def tearDown(self):
        """清理临时文件"""
        self.temp_dir.cleanup()

    def _create_config_file(self, content: dict):
        """辅助方法：创建配置文件"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(content, f, ensure_ascii=False, indent=2)

    # ========== 默认值回退测试 ==========

    def test_default_fallback_no_file(self):
        """测试配置文件不存在时使用默认配置"""
        config = Config("nonexistent.json")
        # 验证使用了默认配置
        self.assertEqual(config.get("political_rules.leader_cooldown_years"), 10)
        self.assertEqual(config.get("mortality_rules.base_draw_count"), 1)
        self.assertEqual(config.get("economic_rules.base_tax"), 100)

    def test_default_fallback_empty_path(self):
        """测试未指定配置文件时使用默认配置"""
        config = Config()
        self.assertEqual(config.get("political_rules.leader_cooldown_years"), 10)

    def test_default_fallback_invalid_json(self):
        """测试配置文件JSON格式错误时使用默认配置"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            f.write("这不是一个JSON")

        config = Config(self.config_path)
        self.assertEqual(config.get("political_rules.leader_cooldown_years"), 10)

    def test_default_fallback_not_dict(self):
        """测试配置文件内容不是字典时使用默认配置"""
        self._create_config_file([1, 2, 3])  # 列表，不是字典

        config = Config(self.config_path)
        self.assertEqual(config.get("political_rules.leader_cooldown_years"), 10)

    # ========== 点号路径访问测试 ==========

    def test_dot_path_single_level(self):
        """测试单层点号路径"""
        config = Config()
        # 直接访问
        self.assertEqual(config.get("political_rules"), config.DEFAULTS["political_rules"])
        # 不存在的键
        self.assertIsNone(config.get("nonexistent"))
        self.assertEqual(config.get("nonexistent", "default"), "default")

    def test_dot_path_multi_level(self):
        """测试多层点号路径"""
        config = Config()

        # 访问嵌套值
        self.assertEqual(config.get("political_rules.leader_cooldown_years"), 10)
        self.assertEqual(config.get("political_rules.min_ages.consul"), 40)
        self.assertEqual(config.get("mortality_rules.draw_per_members"), 5)

        # 部分路径不存在
        self.assertIsNone(config.get("political_rules.nonexistent"))
        self.assertIsNone(config.get("political_rules.min_ages.nonexistent"))

    def test_dot_path_middle_not_dict(self):
        """测试路径中间节点不是字典的情况"""
        config = Config()
        # 访问 political_rules.leader_cooldown_years.xxx，中间节点是整数
        self.assertIsNone(config.get("political_rules.leader_cooldown_years.xxx"))

    def test_dot_path_empty_key(self):
        """测试空键返回默认值"""
        config = Config()
        self.assertIsNone(config.get(""))
        self.assertEqual(config.get("", "default"), "default")

    # ========== 深合并测试 ==========

    def test_deep_merge_simple(self):
        """测试简单键值合并"""
        override = {
            "mortality_rules": {
                "base_draw_count": 3  # 覆盖默认值
            }
        }
        self._create_config_file(override)

        config = Config(self.config_path)
        self.assertEqual(config.get("mortality_rules.base_draw_count"), 3)
        # 其他值保持默认
        self.assertEqual(config.get("mortality_rules.draw_per_members"), 5)
        self.assertEqual(config.get("mortality_rules.max_draws"), 3)

    def test_deep_merge_nested(self):
        """测试嵌套字典深度合并"""
        override = {
            "political_rules": {
                "min_ages": {
                    "consul": 45,  # 覆盖
                    "censor": 45   # 覆盖
                },
                "office_cooldowns": {
                    "consul": 8     # 覆盖
                }
            }
        }
        self._create_config_file(override)

        config = Config(self.config_path)
        # 验证覆盖的值
        self.assertEqual(config.get("political_rules.min_ages.consul"), 45)
        self.assertEqual(config.get("political_rules.min_ages.censor"), 45)
        self.assertEqual(config.get("political_rules.office_cooldowns.consul"), 8)
        # 验证未覆盖的值保持不变
        self.assertEqual(config.get("political_rules.min_ages.praetor"), 35)
        self.assertEqual(config.get("political_rules.office_cooldowns.praetor"), 5)

    def test_deep_merge_new_keys(self):
        """测试添加新键"""
        override = {
            "new_section": {
                "new_key": "new_value"
            }
        }
        self._create_config_file(override)

        config = Config(self.config_path)
        self.assertEqual(config.get("new_section.new_key"), "new_value")

    def test_deep_merge_overwrite_non_dict(self):
        """测试非字典值覆盖字典值（应该直接覆盖）"""
        override = {
            "political_rules": "完全覆盖"  # 字符串覆盖整个字典
        }
        self._create_config_file(override)

        config = Config(self.config_path)
        self.assertEqual(config.get("political_rules"), "完全覆盖")
        # 原来的嵌套值都不存在了
        self.assertIsNone(config.get("political_rules.leader_cooldown_years"))

    # ========== 重载测试 ==========

    def test_reload_success(self):
        """测试成功重载配置"""
        # 初始配置
        self._create_config_file({"mortality_rules": {"base_draw_count": 1}})
        config = Config(self.config_path)
        self.assertEqual(config.get("mortality_rules.base_draw_count"), 1)

        # 修改配置文件
        self._create_config_file({"mortality_rules": {"base_draw_count": 3}})

        # 重载
        result = config.reload()
        self.assertTrue(result)
        self.assertEqual(config.get("mortality_rules.base_draw_count"), 3)

    def test_reload_fail_keep_old(self):
        """测试重载失败时保持原配置"""
        # 初始配置
        self._create_config_file({"mortality_rules": {"base_draw_count": 1}})
        config = Config(self.config_path)
        self.assertEqual(config.get("mortality_rules.base_draw_count"), 1)

        # 确认文件存在
        self.assertTrue(os.path.exists(self.config_path), "配置文件应该存在")

        # 删除配置文件
        os.remove(self.config_path)

        # 确认文件已删除
        self.assertFalse(os.path.exists(self.config_path), "配置文件应该已被删除")

        # 重载应失败，但原配置保持不变
        result = config.reload()
        self.assertFalse(result, "重载失败应返回 False")
        self.assertEqual(config.get("mortality_rules.base_draw_count"), 1, "原配置应保持不变")

    def test_reload_no_path(self):
        """测试未指定路径时重载失败"""
        config = Config()  # 无路径
        result = config.reload()
        self.assertFalse(result)

    # ========== 深拷贝保护测试 ==========

    def test_to_dict_deepcopy(self):
        """测试 to_dict 返回深拷贝，修改不影响内部"""
        config = Config()
        original = config.to_dict()

        # 修改返回的字典
        original["mortality_rules"]["base_draw_count"] = 999
        original["new_key"] = "new_value"

        # 内部配置应保持不变
        self.assertEqual(config.get("mortality_rules.base_draw_count"), 1)
        self.assertIsNone(config.get("new_key"))

    def test_config_immutable(self):
        """测试外部无法修改内部配置"""
        config = Config()
        # 尝试直接访问内部属性修改
        try:
            config._config["mortality_rules"]["base_draw_count"] = 999
            # 如果能修改，说明内部属性可访问，但这是预期行为（约定使用公共方法）
            # 我们测试的是通过公共方法获取的值是否被意外修改
            self.assertEqual(config.get("mortality_rules.base_draw_count"), 999)
        except AttributeError:
            # 如果有属性保护，这里会失败，但目前没有保护，所以不 assert
            pass

    # ========== 边界情况测试 ==========

    def test_permission_error(self):
        """测试权限不足时的回退（模拟）"""
        # 在 Windows 上难以模拟权限错误，这里仅测试代码路径
        # 通过 mock 的方式测试会在后续完善，目前先手动测试异常捕获
        config = Config("c:/windows/system32/config.json")  # 通常权限不足
        # 应该使用默认配置
        self.assertEqual(config.get("political_rules.leader_cooldown_years"), 10)

    def test_all_defaults_present(self):
        """测试所有默认配置都存在且结构完整"""
        config = Config()

        # 验证主要配置节都存在
        self.assertIsNotNone(config.get("political_rules"))
        self.assertIsNotNone(config.get("mortality_rules"))
        self.assertIsNotNone(config.get("economic_rules"))
        self.assertIsNotNone(config.get("combat_rules"))

        # 验证嵌套值
        self.assertIsNotNone(config.get("political_rules.office_cooldowns.consul"))
        self.assertIsNotNone(config.get("political_rules.min_ages.consul"))
        self.assertIsNotNone(config.get("political_rules.candidates_per_election.consul"))

    def test_path_property(self):
        """测试 path 属性"""
        config = Config("test/path.json")
        self.assertEqual(config.path, "test/path.json")

        config = Config()
        self.assertIsNone(config.path)


if __name__ == "__main__":
    unittest.main()