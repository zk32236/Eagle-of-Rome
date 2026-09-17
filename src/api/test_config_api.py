# src/api/test_config_api.py
"""WP-G-R5 DA-6（SA-Design §5.5 / Owner §20 #44）— Configure/Test force 控件 API 入口。

暴露**两个独立**的确定性战斗结果控件读写：
- `Force Land Result  → testing.force_battle_result`（Land/CRT override）
- `Force Naval Result → testing.force_naval_result`（Naval override）

**空值 = 正常结算**：空/缺省值不短路，消费点回落既有 canonical 归一化（
`combat_api._normalize_forced_result → None` / `naval_system._normalize_forced_naval_result
→ None`）。

**不改消费语义**：本模块只读写 `testing.*` 两键；消费点仍为 `combat_api:516` /
`naval_system:750`，归一化词表未变（stalemate/draw/triumph/victory/defeat/disaster）。
两键分离（SA §5.5 / D7 非缺陷）——禁止合并为单一跨阶段 override。

**写路径 = 测试/配置面（in-memory）**：只写运行时 `state.config`，不落盘；committed
`data/config/game_config.json` 默认 `""` 不被污染（候选禁含 override）。
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("EOR-API")

# 两个独立字段（互不穿透）
FORCE_LAND_FIELD = "force_battle_result"
FORCE_NAVAL_FIELD = "force_naval_result"
FORCE_RESULT_FIELDS = (FORCE_LAND_FIELD, FORCE_NAVAL_FIELD)

# none/normal + 现五词归一结果（与 combat_api._FORCED_RESULT_MAP /
# naval_system._FORCED_NAVAL_RESULT_MAP 的**键域**一致：stalemate/draw 归一小写；
# 两处消费点大小写容忍）。空字符串 = 正常结算。
_FORCE_RESULT_OPTIONS: List[str] = ["", "stalemate", "triumph", "victory", "defeat", "disaster"]

# 错误身份（fail-closed；与整包 Submit 的 error-code 风格一致）
ERR_UNKNOWN_FIELD = "TEST_CONFIG_UNKNOWN_FIELD"
ERR_INVALID_VALUE = "TEST_CONFIG_INVALID_VALUE"


def land_result_options() -> List[str]:
    """Land 控件选项（none + 五词归一结果）。"""
    return list(_FORCE_RESULT_OPTIONS)


def naval_result_options() -> List[str]:
    """Naval 控件选项（none + 五词归一结果）——与 land 列表独立。"""
    return list(_FORCE_RESULT_OPTIONS)


def _read_field(state, field: str) -> str:
    value = state.config.get(f"testing.{field}", "")
    return value if isinstance(value, str) else ""


def _ok(data: Dict[str, Any], message: str = "") -> Dict[str, Any]:
    return {"success": True, "message": message, "data": data, "errors": []}


def _err(code: str, message: str) -> Dict[str, Any]:
    return {"success": False, "message": message, "data": {}, "errors": [code]}


def get_test_config(state, player_id: Optional[str] = None) -> Dict[str, Any]:
    """只读：两 force 键当前值 + 各自独立选项列表（QML 只消费，不推导）。"""
    return _ok({
        FORCE_LAND_FIELD: _read_field(state, FORCE_LAND_FIELD),
        FORCE_NAVAL_FIELD: _read_field(state, FORCE_NAVAL_FIELD),
        "land_options": land_result_options(),
        "naval_options": naval_result_options(),
    })


def _normalize_token(value: str) -> Optional[str]:
    """token 归一（大小写/空白容忍）；空 = 正常结算；非法 → None。"""
    if not isinstance(value, str):
        return None
    token = value.strip().lower()
    if token == "":
        return ""
    if token in _FORCE_RESULT_OPTIONS:
        return token
    return None


def set_test_config(state, player_id: Optional[str], field: str, value: Any) -> Dict[str, Any]:
    """写入口（测试/配置面）：设置单个 force 键；空值 = 清除 override（正常结算）。

    fail-closed：未知字段 / 非法值 / 非字符串 → 显式失败且**零写入**（不静默变正常结算）。
    只写运行时 `state.config`（in-memory），不落盘。
    """
    if field not in FORCE_RESULT_FIELDS:
        return _err(ERR_UNKNOWN_FIELD, f"未知测试配置字段: {field}")

    token = _normalize_token(value)
    if token is None:
        return _err(ERR_INVALID_VALUE, f"非法强制结果值: {value!r}")

    # in-memory 写入（不持久化；committed 默认 "" 不入提交面）
    proxy = getattr(state.config, "testing")
    setattr(proxy, field, token)
    logger.info(f"[TEST-CONFIG] {field} = {token!r}")

    return _ok({
        field: token,
        "field": field,
        "options": land_result_options() if field == FORCE_LAND_FIELD else naval_result_options(),
    }, message=f"{field} = {token!r}")
