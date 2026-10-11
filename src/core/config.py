# src/core/config.py
"""
配置管理模块 - 独立于 GameState，支持默认值回退、点号路径访问、运行时重载
"""

import json
import copy
import hashlib
import math
from pathlib import Path
from typing import Dict, Any, Optional


class Config:
    """配置管理类"""

    # EOR20261009-03 (FC-11/FC-12, OD-06)：奖励份额配置键（raw 四键，单一来源）。
    # raw schema 键名 = treasury_share/faction_share/commander_share/soldier_share；
    # effective 四键 = treasury/faction/commander/soldier（与 receipt shares_effective 同值映射）。
    REWARD_SHARE_KEYS = ("treasury_share", "faction_share", "commander_share", "soldier_share")
    REWARD_SHARE_EFFECTIVE_KEYS = ("treasury", "faction", "commander", "soldier")
    # 冻结默认（FC-11：sum == 1.0；有效分配逐字保持 50/25/15/10）。
    REWARD_SHARE_DEFAULTS = {
        "treasury_share": 0.50,
        "faction_share": 0.25,
        "commander_share": 0.15,
        "soldier_share": 0.10,
    }
    _REWARD_SHARE_SUM_TOLERANCE = 1e-9

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
                "consul": 5,
                "praetor": 5,
                "quaestor": 2,
                "censor": 3,
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
            "death_count": 1  # 每回合随机死亡1人
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
            "national_opex_rate": 0.0003,  # 国家运营费率（0.03%）
            "province_tax_rate": 0.1,  # 行省基础税率（10%）
            "tax_auction_ratio": 0.8,  # 包税权拍卖底价占年收益的比例（80%）
            "tax_contract_profit_rate": 0.2,  # 保留原利润比例（可沿用，但阶段3将基于实际利润）
            "faction_initial_treasury": 10,  # 派系初始资金
            "faction_tax_rate": 0.1,  # 派系抽成比例（从成员收入中扣除）
            # WP-K（OD-K-01/02/03）新增/接线键（frozen 默认值；镜像 game_config.json）
            "legion_strength_base": 2,  # S1：AI 军团增援敌强匹配单位战力 u（默认 2）
            "project_bid_discount_min": 0.05,  # S2：竞价折扣下界
            "project_bid_discount_max": 0.20,  # S2：竞价折扣上界
            "project_bid_profit_rate_min": 0.05,  # S2：竞价利润率下界
            "project_bid_profit_rate_max": 0.20,  # S2：竞价利润率上界
            "tax_bid_increment_min": 0.05,  # S2：包税加价率下界
            "tax_bid_increment_max": 0.20,  # S2：包税加价率上界
            "public_work_budget_margin_range": [0.05, 0.20],  # S4：AI 建造预算加成 margin 区间
        },
        "combat_rules": {
            "triumph_threshold": 12,
            "victory_threshold": 6,
            "defeat_threshold": -3,
            "disaster_rolls": [2, 3, 4],
            "standoff_rolls": [5, 6, 7, 8, 9],
            # EOR20261009-03（FC-11/FC-12, OD-06）：权威奖励份额（单一来源；sum=1.0；
            # 有效分配 50/25/15/10，配置诚实化非 rebalance）。
            "treasury_share": 0.50,
            "faction_share": 0.25,
            "commander_share": 0.15,
            "soldier_share": 0.10
        },
        "terminology_preset": "original",
        "faction_style_map": {
            "optimates": {
                "color": "#C62828",
                "name": "Optimates",
                "name_i18n": "贵族派",
                "id_display": "Opt",
                "id_display_i18n": "贵",
                "order": 1,
            },
            "populares": {
                "color": "#1565C0",
                "name": "Populares",
                "name_i18n": "平民派",
                "id_display": "Pop",
                "id_display_i18n": "平",
                "order": 2,
            },
            "equites": {
                "color": "#E65100",
                "name": "Equites",
                "name_i18n": "骑士派",
                "id_display": "Equ",
                "id_display_i18n": "骑",
                "order": 3,
            },
            "f4": {
                "color": "#6A1B9A",
                "name": "第四派系",
                "id_display": "F4",
                "order": 4,
            },
            "f5": {
                "color": "#00695C",
                "name": "第五派系",
                "id_display": "F5",
                "order": 5,
            },
            "f6": {
                "color": "#AD1457",
                "name": "第六派系",
                "id_display": "F6",
                "order": 6,
            },
        },
        "faction_style_fallback": {
            "color": "#3A3530",
            "name": "未知派系",
            "id_display": "?",
        },
    }

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置实例

        Args:
            config_path: 配置文件路径，None 时使用内置默认配置
        """
        self._config_path = config_path
        self._config: Dict[str, Any] = {}
        # EOR20261009-03（FC-11/§5.4）：reward-share metadata（raw/effective/identity，
        # 单一来源同一 revision）；在 _load_from_file 中填写。
        self._reward_share_metadata: Dict[str, Any] = {}
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
            self._reward_share_metadata = self._build_reward_share_metadata(
                source="defaults", raw_source=self.DEFAULTS.get("combat_rules", {})
            )
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
            # EOR20261009-03（FC-11）：raw 缺键检测在 **raw JSON 层**（不取 merged get，
            # 因 DEFAULTS 必含 4 键、merged 永不缺）；同一 revision 捕获 raw 后校验→effective。
            raw_rules = loaded.get("combat_rules", {})
            if not isinstance(raw_rules, dict):
                raw_rules = {}
            self._reward_share_metadata = self._build_reward_share_metadata(
                source="file", raw_source=raw_rules
            )
            return True

        except FileNotFoundError as e:
            print(f"⚠️ 配置文件不存在，使用默认配置: {e}")
            self._reward_share_metadata = self._build_reward_share_metadata(
                source="initial_load_fallback", reason="load_failed"
            )
            self._config = copy.deepcopy(self.DEFAULTS)
            return False

        except json.JSONDecodeError as e:
            print(f"⚠️ 配置文件JSON解析错误，使用默认配置: {e}")
            self._reward_share_metadata = self._build_reward_share_metadata(
                source="initial_load_fallback", reason="load_failed"
            )
            self._config = copy.deepcopy(self.DEFAULTS)
            return False

        except PermissionError as e:
            print(f"⚠️ 配置文件权限不足，使用默认配置: {e}")
            self._reward_share_metadata = self._build_reward_share_metadata(
                source="initial_load_fallback", reason="load_failed"
            )
            self._config = copy.deepcopy(self.DEFAULTS)
            return False

        except TypeError as e:
            print(f"⚠️ 配置文件格式错误，使用默认配置: {e}")
            self._reward_share_metadata = self._build_reward_share_metadata(
                source="initial_load_fallback", reason="load_failed"
            )
            self._config = copy.deepcopy(self.DEFAULTS)
            return False

        except Exception as e:
            print(f"⚠️ 配置文件加载未知错误，使用默认配置: {e}")
            self._reward_share_metadata = self._build_reward_share_metadata(
                source="initial_load_fallback", reason="load_failed"
            )
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
        old_metadata = self._reward_share_metadata
        success = self._load_from_file(self._config_path)
        if success:
            return True
        else:
            # EOR20261009-03（FC-11/§5.4）：reload 读/解析失败 → 原 _config + metadata
            #（含 hash）+ 全部保留。
            self._config = old_config
            self._reward_share_metadata = old_metadata
            return False

    # ==================== EOR20261009-03 reward-share snapshot（FC-11/§5.4） ====================
    def _raw_share_spec(self, raw_value: Any) -> Dict[str, Any]:
        """raw 值类型编码（§5.4）：missing={type:"missing"}；finite={type:"number",value:float}；
        bool/string/null/nonfinite={type:类型名,value:字符串}（非finite字符串固定 NaN/+Inf/-Inf）。"""
        if isinstance(raw_value, bool):
            return {"type": "bool", "value": str(raw_value)}
        if isinstance(raw_value, (int, float)):
            fv = float(raw_value)
            if not math.isfinite(fv):
                if math.isnan(fv):
                    return {"type": "float", "value": "NaN"}
                return {"type": "float", "value": ("+Inf" if fv > 0 else "-Inf")}
            return {"type": "number", "value": fv}
        if raw_value is None:
            return {"type": "NoneType", "value": "None"}
        if isinstance(raw_value, str):
            return {"type": "str", "value": raw_value}
        return {"type": type(raw_value).__name__, "value": str(raw_value)}

    def _validate_reward_shares(self, raw_source: Any):
        """校验 raw 四键（完整性/finite 非 bool/[0,1]/sum 容差）→ (raw_specs, effective, valid, reason)。
        reason 依序：missing / invalid_type / nonfinite / out_of_range / sum_mismatch。"""
        if not isinstance(raw_source, dict):
            raw_source = {}
        raw_specs = {}
        reason = None
        for k in self.REWARD_SHARE_KEYS:
            if k not in raw_source:
                raw_specs[k] = {"type": "missing"}
                if reason is None:
                    reason = "missing"
            else:
                raw_specs[k] = self._raw_share_spec(raw_source[k])

        effective = {}
        if reason is None:
            for k in self.REWARD_SHARE_KEYS:
                v = raw_source[k]
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    reason = "invalid_type"
                    break
                fv = float(v)
                if not math.isfinite(fv):
                    reason = "nonfinite"
                    break
                if fv < 0.0 or fv > 1.0:
                    reason = "out_of_range"
                    break
                effective[k] = fv
        if reason is None and abs(sum(effective.values()) - 1.0) > self._REWARD_SHARE_SUM_TOLERANCE:
            reason = "sum_mismatch"

        if reason is not None:
            effective_out = {
                ek: float(self.REWARD_SHARE_DEFAULTS[f"{ek}_share"])
                for ek in self.REWARD_SHARE_EFFECTIVE_KEYS
            }
            return raw_specs, effective_out, False, reason
        effective_out = {
            ek: float(raw_source[f"{ek}_share"]) for ek in self.REWARD_SHARE_EFFECTIVE_KEYS
        }
        return raw_specs, effective_out, True, None

    def _reward_config_version(self, meta: Dict[str, Any]) -> str:
        """config_version = "reward-shares/v1:" + SHA256(canonical JSON of
        {source,raw,effective,valid,reason})（sort_keys/separators/ensure_ascii/allow_nan=False）。"""
        payload = {
            "source": meta["source"],
            "raw": meta["raw"],
            "effective": meta["effective"],
            "valid": meta["valid"],
            "reason": meta["reason"],
        }
        canonical = json.dumps(
            payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False
        )
        return "reward-shares/v1:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _build_reward_share_metadata(
        self, source: str, raw_source: Any = None, reason: Optional[str] = None
    ) -> Dict[str, Any]:
        if reason == "load_failed":
            raw_specs = {k: {"type": "missing"} for k in self.REWARD_SHARE_KEYS}
            effective = {
                ek: float(self.REWARD_SHARE_DEFAULTS[f"{ek}_share"])
                for ek in self.REWARD_SHARE_EFFECTIVE_KEYS
            }
            valid = False
            rs = "load_failed"
        else:
            raw_specs, effective, valid, rs = self._validate_reward_shares(raw_source)
        meta = {
            "source": source,
            "raw": raw_specs,
            "effective": effective,
            "valid": valid,
            "reason": rs,
        }
        meta["config_version"] = self._reward_config_version(meta)
        return meta

    def _sync_reward_share_memory(self) -> None:
        """公开内存赋值（Config.__setattr__ / _ConfigAttrProxy）后同步 raw+校验+identity。"""
        raw = self._config.get("combat_rules", {}) if isinstance(self._config, dict) else {}
        self._reward_share_metadata = self._build_reward_share_metadata(
            source="memory", raw_source=raw
        )

    def get_reward_share_snapshot(self) -> Dict[str, Any]:
        """只读快照：deep-copy {source,raw,effective,valid,reason,config_version}。

        单一来源同一 revision；不重读 JSON；raw 仅四 share 键。
        """
        meta = getattr(self, "_reward_share_metadata", None)
        if not meta:
            meta = self._build_reward_share_metadata(
                source="defaults", raw_source=self.DEFAULTS.get("combat_rules", {})
            )
            self._reward_share_metadata = meta
        return {
            "source": meta["source"],
            "raw": copy.deepcopy(meta["raw"]),
            "effective": copy.deepcopy(meta["effective"]),
            "valid": meta["valid"],
            "reason": meta["reason"],
            "config_version": meta["config_version"],
        }

    def to_dict(self) -> Dict[str, Any]:
        """
        返回配置的深拷贝，防止外部篡改

        Returns:
            配置字典的深拷贝
        """
        return copy.deepcopy(self._config)

    def __getattr__(self, name: str):
        """
        支持属性风格的嵌套读取: config.testing.always_declare
        返回 _ConfigAttrProxy 以便继续链式访问。
        """
        if name.startswith('_'):
            raise AttributeError(name)
        return _ConfigAttrProxy(self, self._config, name)

    def __setattr__(self, name: str, value: Any):
        """
        支持属性风格赋值:
          - 私有属性（_ 开头）走标准 Python 属性设置
          - 公开属性直接写入 _config 顶层，以便链式子代理处理嵌套
        """
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        else:
            self._config[name] = copy.deepcopy(value)
            if name == "combat_rules":
                self._sync_reward_share_memory()

    @property
    def path(self) -> Optional[str]:
        """获取配置文件路径"""
        return self._config_path


class _ConfigAttrProxy:
    """配置属性代理：支持链式属性访问和赋值的辅助对象"""

    def __init__(self, cfg: 'Config', data: dict, path_component: str):
        self._cfg = cfg
        self._data = data
        self._path_component = path_component

    def __getattr__(self, name: str):
        if name.startswith('_'):
            raise AttributeError(name)
        # 在父 data 中确保路径存在（惰性创建），然后传入实际的子 dict
        parent = self._data
        if self._path_component not in parent:
            parent[self._path_component] = {}
        sub = parent[self._path_component]
        if isinstance(sub, dict):
            return _ConfigAttrProxy(self._cfg, sub, name)
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any):
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        else:
            # 确保父路径存在
            parent = self._data
            if self._path_component not in parent:
                parent[self._path_component] = {}
            target = parent[self._path_component]
            if isinstance(target, dict):
                target[name] = copy.deepcopy(value)
                # EOR20261009-03（FC-11/§5.4）：公开对 combat_rules 四键的内存赋值
                # → 同步 raw+校验+identity（source=memory）。
                if self._path_component == "combat_rules" and name in Config.REWARD_SHARE_KEYS:
                    self._cfg._sync_reward_share_memory()
            else:
                raise TypeError(f"无法设置嵌套属性: {self._path_component}.{name}")

    def __repr__(self) -> str:
        val = self._data.get(self._path_component, '<missing>')
        return f"<ConfigAttrProxy {self._path_component}={val!r}>"