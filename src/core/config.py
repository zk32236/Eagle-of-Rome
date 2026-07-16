# src/core/config.py
"""
配置管理模块 - 独立于 GameState，支持默认值回退、点号路径访问、运行时重载
"""

import json
import copy
from pathlib import Path
from typing import Dict, Any, Optional


class Config:
    """配置管理类"""

    # 内置默认配置（从原 game_state.py 的 _load_config 默认值中抽取）
    DEFAULTS: Dict[str, Any] = {
        "logging": {
            "enabled": True,
            "file_path": "logs/game.log",
            "max_bytes": 10485760,
            "backup_count": 3,
            "log_level": "INFO"
        },
        "political_rules": {
            "leader_cooldown_years": 10,
            "leaders_per_election": 2,
            "office_cooldowns": {
                "consul": 10,
                "praetor": 5,
                "quaestor": 2,
                "censor": 8,
                "aedile": 4
            },
            "offices_per_election": {
                "consul": 2,
                "praetor": 2,
                "quaestor": 2,
                "censor": 1,
                "aedile": 2
            },
            "min_ages": {
                "consul": 40,
                "praetor": 35,
                "quaestor": 30,
                "censor": 42,
                "aedile": 36
            },
            "candidates_per_election": {
                "consul": 2,
                "praetor": 2,
                "quaestor": 2,
                "censor": 2,
                "tribune": 2
            },
            "voting": {
                "finalist_count": 2,
                "tiebreaker": "highest_influence"
            }
        },
        "mortality_rules": {
            # 新增事件卡配置
            "event_deck": [
                {"name": "死神来了", "type": "厄运", "effect": "death", "weight": 1},
                {"name": "丰调雨顺", "type": "好运", "effect": "bountiful_harvest", "weight": 1},
                {"name": "国泰民安", "type": "好运", "effect": "peace", "weight": 1},
                {"name": "天降猛男", "type": "好运", "effect": "mighty_man", "weight": 1},
                {"name": "无妄天灾", "type": "厄运", "effect": "disaster", "weight": 1}
            ],
            "event_draw_count": 1,  # 每回合抽取事件卡数量
            "death_count": 2  # 添加这一行，每回合死2人
        },
        "economic_rules": {
            "base_tax": 100,
            "faction_stipend": 10,
            "legion_recruit_cost": 10,
            "legion_maintenance_base": 2,
            "veteran_maintenance_bonus": 1,
            "public_land_rent_per_unit": 1,
            # 新增配置
            "land_price_per_unit": 10,  # 土地单价（塔兰特/C）
            "national_public_land_tax_rate": 0.02,  # 国家公地税率（2%）
            "private_land_income_rate": 0.05,  # 私地收益率 5%
            "initial_national_public_land": 1000,  # 初始国家公地数量
            "province_tax_rate": 0.1,  # 行省基础税率（10%）
            "tax_auction_ratio": 0.8,  # 包税权拍卖底价占年收益的比例（80%）
            "tax_contract_profit_rate": 0.2,  # 保留原利润比例（可沿用，但阶段3将基于实际利润）
            "faction_initial_treasury": 10,  # 派系初始资金
            "faction_tax_rate": 0.1,  # 派系抽成比例（从成员收入中扣除）
        },
        "combat_rules": {
            "triumph_threshold": 12,
            "victory_threshold": 6,
            "defeat_threshold": -3,
            "disaster_rolls": [2, 3, 4],
            "standoff_rolls": [5, 6, 7, 8, 9]
        },
        "terminology_preset": "original"
    }

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置实例

        Args:
            config_path: 配置文件路径，None 时使用内置默认配置
        """
        self._config_path = config_path
        self._config: Dict[str, Any] = {}
        self._load_from_file(config_path)  # 忽略返回值，首次加载失败也用默认配置

    def _load_from_file(self, config_path: Optional[str]) -> bool:
        """
        从文件加载配置，失败时回退到默认配置

        Args:
            config_path: 配置文件路径

        Returns:
            bool: 加载成功返回 True，失败返回 False（但会使用默认配置）
        """
        # 如果没有指定路径，直接使用默认配置
        if not config_path:
            self._config = copy.deepcopy(self.DEFAULTS)
            return False

        try:
            path = Path(config_path)
            if not path.exists():
                raise FileNotFoundError(f"配置文件不存在: {config_path}")

            with open(path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)

            # 验证加载内容是否为字典
            if not isinstance(loaded, dict):
                raise TypeError(f"配置文件内容应为字典，实际为 {type(loaded).__name__}")

            # 深度合并加载的配置到默认配置
            self._config = self._deep_merge(copy.deepcopy(self.DEFAULTS), loaded)
            return True

        except FileNotFoundError as e:
            print(f"⚠️ 配置文件不存在，使用默认配置: {e}")
            self._config = copy.deepcopy(self.DEFAULTS)
            return False

        except json.JSONDecodeError as e:
            print(f"⚠️ 配置文件JSON解析错误，使用默认配置: {e}")
            self._config = copy.deepcopy(self.DEFAULTS)
            return False

        except PermissionError as e:
            print(f"⚠️ 配置文件权限不足，使用默认配置: {e}")
            self._config = copy.deepcopy(self.DEFAULTS)
            return False

        except TypeError as e:
            print(f"⚠️ 配置文件格式错误，使用默认配置: {e}")
            self._config = copy.deepcopy(self.DEFAULTS)
            return False

        except Exception as e:
            print(f"⚠️ 配置文件加载未知错误，使用默认配置: {e}")
            self._config = copy.deepcopy(self.DEFAULTS)
            return False

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """
        深度合并两个字典（递归更新）

        Args:
            base: 基础字典（默认配置）
            override: 覆盖字典（用户配置）

        Returns:
            合并后的新字典
        """
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # 递归合并嵌套字典
                result[key] = self._deep_merge(result[key], value)
            else:
                # 直接覆盖非字典值或新键
                result[key] = copy.deepcopy(value)

        return result

    def get(self, key: str, default=None):
        """
        点号路径获取配置值

        Args:
            key: 点号分隔的键，如 "economic.base_tax"
            default: 若路径不存在返回的默认值

        Returns:
            配置值或默认值
        """
        if not key:
            return default

        parts = key.split('.')
        value = self._config

        for part in parts:
            if not isinstance(value, dict):
                return default
            if part not in value:
                return default
            value = value[part]

        return value

    def reload(self) -> bool:
        """
        重新加载配置文件

        Returns:
            bool: 重载成功返回 True，失败返回 False（保持原配置）
        """
        if not self._config_path:
            return False

        old_config = self._config.copy()
        success = self._load_from_file(self._config_path)
        if success:
            return True
        else:
            self._config = old_config
            return False

    def to_dict(self) -> Dict[str, Any]:
        """
        返回配置的深拷贝，防止外部篡改

        Returns:
            配置字典的深拷贝
        """
        return copy.deepcopy(self._config)

    @property
    def path(self) -> Optional[str]:
        """获取配置文件路径"""
        return self._config_path