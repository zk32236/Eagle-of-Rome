# src/ui/commands/phase_mortality.py
"""
天命阶段命令 - CLI 包装层。
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, TYPE_CHECKING

from src.core.localization import TerminologyService
from src.core.service.mortality_service import MortalityService
from src.ui.commands.sys_base import Command

if TYPE_CHECKING:
    from src.core.game_state import GameState


class MortalityCommand(Command):
    """天命阶段命令"""

    name = "mortality"
    aliases = ["m"]
    description = "执行天命阶段 (Mortality Phase) - 抽取事件卡"

    def __init__(self, state: "GameState"):
        super().__init__(state)

    def execute(self, args: List[str]) -> bool:
        if self.state.is_phase_executed("mortality"):
            print("⚠️ 天命阶段在本回合已执行过")
            return False

        terms = TerminologyService.get()
        print(f"\n--- {terms.phase_mortality} Phase (Year {abs(self.state.turn.year)} BC) ---")

        service = MortalityService(
            self.state,
            disaster_loader=self._load_disasters,
            hero_loader=self._load_heroes,
        )
        result = service.execute(mark_phase=True)
        self._print_result(result)
        return True

    def _print_result(self, result: Dict):
        for event in result.get("events", []):
            effect = event.get("effect", "")
            if effect != "none":
                print(f"   🎴 事件卡: {event.get('name', '未知事件')}")
            for line in event.get("logs", []):
                print(line)

    def _service(self) -> MortalityService:
        return MortalityService(
            self.state,
            disaster_loader=self._load_disasters,
            hero_loader=self._load_heroes,
        )

    def _load_disasters(self) -> List[Dict]:
        """从 disasters.json 加载灾害数据，如果文件不存在或解析失败则返回空列表"""
        base_path = Path(__file__).parent.parent.parent.parent
        file_path = base_path / "data" / "cards" / "disasters.json"
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("disasters", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.state.log_event(f"灾害数据加载失败: {e}", level=logging.WARNING)
            return []

    def _load_heroes(self) -> List[Dict]:
        """从 heroes.json 加载英雄数据，如果文件不存在或解析失败则返回空列表"""
        base_path = Path(__file__).parent.parent.parent.parent
        file_path = base_path / "data" / "cards" / "heroes.json"
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("heroes", [])
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.state.log_event(f"英雄数据加载失败: {e}", level=logging.WARNING)
            return []

    def _handle_disaster_event(self):
        result = self._service().apply_disaster_event()
        for line in result.get("logs", []):
            print(line)

    def _handle_mighty_man_event(self):
        result = self._service().apply_mighty_man_event()
        for line in result.get("logs", []):
            print(line)

    def _handle_death_event(self):
        result = self._service().apply_death_event()
        for line in result.get("logs", []):
            print(line)

    def _handle_bountiful_harvest(self):
        result = self._service().apply_bountiful_harvest()
        for line in result.get("logs", []):
            print(line)

    def _handle_peace_event(self):
        result = self._service().apply_peace_event()
        for line in result.get("logs", []):
            print(line)
