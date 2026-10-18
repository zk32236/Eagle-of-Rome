# src/ui/commands/phase_resolution.py
"""
决议阶段命令 - 精简打印，只显示胜利条件
"""
import logging
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from src.ui.commands.sys_base import Command
from src.core.localization import TerminologyService
from src.ui.utils import get_progress_bar
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.api.resolution_api import execute_resolution

if TYPE_CHECKING:
    from src.core.game_state import GameState


class ResolutionCommand(Command):
    """决议阶段命令"""

    name = "resolution"
    aliases = ["x"]
    description = "执行决议阶段 (Resolution Phase)"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        # 委托给 resolution_api 共享用例（bool 语义供 CLI turn/step 使用）
        # R2b（B-02）：恢复基线 CLI 打印路径；未注册会话的内层 guard 按既有
        # CLI 豁免放行，stdout 与 0c4e935 基线逐字节等价。
        result = execute_resolution(self.state)

        if not result["success"]:
            print(f"⚠️ {result['message']}")
            return False

        dto = result.get("data", {})
        terms = TerminologyService.get()
        year_display = dto.get("year_display", f"{abs(self.state.turn.year)} BC")
        print(f"\n--- {terms.phase_resolution} Phase ({year_display}) ---")

        # 打印胜利条件
        self._print_victory_conditions(dto)

        # 打印军团恢复
        legion = dto.get("legion_recovery", {})
        if legion.get("recovered", 0) > 0:
            print(f"\n   🛡️ 军团恢复: {legion['details']}")

        # 打印关键事件
        key_events = dto.get("key_events", [])
        if key_events:
            print(f"\n   📋 关键事件:")
            for evt in key_events:
                print(f"      • {evt}")

        return True

    def execute_with_context(self, args: List[str], *, caller_context=None) -> Dict[str, Any]:
        """D12 / W1：把调用方上下文显式转发到内层 guarded 边界。

        与 ``execute`` 的区别：
        - ``caller_context`` 原样转发给 ``execute_resolution``（不在边界内自取）；
        - 返回结构化结果，内层 typed 失败原样上抛，不用 ``print + False`` 冒充。

        返回：``{success, executed, errors: [{code, message, scope?}], data}``
        并附带 ``message``（供 envelope 在无 stdout 输出时保留文案）。
        """
        result = execute_resolution(self.state, caller_context=caller_context)
        success = bool(result.get("success"))
        message = result.get("message") or ""

        if success:
            return {
                "success": True,
                "executed": True,
                "errors": [],
                "data": result.get("data") or {},
                "message": message,
            }

        return {
            "success": False,
            "executed": False,
            "errors": self._typed_errors(result),
            "data": result.get("data"),
            "message": message,
        }

    @staticmethod
    def _typed_errors(result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """把 resolution_api 的 errors 归一为 typed 结构；dict 原样透传。"""
        typed: List[Dict[str, Any]] = []
        for err in result.get("errors") or []:
            if isinstance(err, dict):
                typed.append(err)
            else:
                code = ("PHASE_NOT_READY" if "not_executed" in str(err)
                        else "EXECUTION_ERROR")
                typed.append({"code": code, "message": str(err)})
        if not typed:
            typed.append({"code": "EXECUTION_ERROR",
                          "message": result.get("message") or "决算阶段执行失败"})
        return typed

    @staticmethod
    def _failure_message(result: Dict[str, Any]) -> str:
        message = (result.get("message") or "").strip()
        if message:
            return message
        for err in result.get("errors") or []:
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])
        return "决算阶段执行失败"

    # ================================= MVP 0.7 ===========================================

    # ======== MVP 0.7.1 停战议和 ========

    def _check_truce_expiry(self):
        """Shell method — 委托 GameState.process_truce_expiry（G3C：到期 → THREAT）。"""
        return self.state.process_truce_expiry()

    # ================================= MVP 0.1-0.5 =======================================

    def _process_governor_return(self):
        """Shell method — logic moved to GameState.advance_year()"""
        return []

    def _print_victory_conditions(self, dto: dict):
        """从 DTO 打印胜利条件结果"""
        victory = dto.get("victory", {})
        conditions = victory.get("conditions", [])
        summary = victory.get("summary", {})
        print(f"\n   🏆 胜利/失败条件检查:")
        for cond in conditions:
            icon = "💀" if cond.get("critical") else "⚠️"
            print(f"      {icon} {cond['details']}")
        if summary.get("top_faction"):
            tf = summary["top_faction"]
            print(f"      📊 元老院主导派系: {tf['name']} ({tf['share']:.1%} 影响力)")
        else:
            print(f"      📊 元老院无派系")

    def _process_contract_expiration(self, terms, verbose=False):
        """Shell method — logic moved to GameState.advance_year()"""
        return 0

    def _prepare_next_year(self, verbose=False):
        """准备下一年（无打印）"""
        # 实际 advance_year 会重置阶段标记，这里不需要额外操作
        pass

    def _apply_annual_decay(self, terms, verbose=False):
        """年度衰减（无打印）"""
        decay_rates = {
            "veterans": 0.20,
            "popularity": 0.50
        }
        for fig in self.state.get_living_members():
            fig.apply_annual_decay(decay_rates)
            fig.age += 1

    def _process_temp_influence_decay(self, verbose=False):
        """处理所有存活人物的临时影响力衰减（无打印）"""
        for fig in self.state.get_living_members():
            if fig.get_temp_influence() > 0:
                fig.decay_temp_influence_tasks()
                fig.update_influence()

