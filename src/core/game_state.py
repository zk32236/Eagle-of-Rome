# src/core/game_state.py
"""
游戏状态容器 - 已移除单例模式，支持多实例独立创建
集成 Config 配置管理
"""
import logging.handlers
from datetime import datetime
import copy
import random
import logging
import logging.handlers
import os
import threading
from typing import Dict, List, Optional, Set, Any, Tuple
from typing import TYPE_CHECKING

from src.core.config import Config
from src.core.entities.curia import Curia
from src.core.entities.contract import Contract, ContractType, ContractStatus
from src.core.entities.province import Province
from src.core.entities.figure import Figure
from src.core.systems.war_system import WarSystem
from src.core.systems.military_system import MilitarySystem
from src.core.systems.naval_system import NavalSystem
from src.core.entities.city import City


if TYPE_CHECKING:
    from src.core.entities import Faction, GameTurn, Player
    from src.core.systems.war_system import WarSystem
    from src.core.systems.military_system import MilitarySystem


class GameState:
    """游戏状态容器 - 多实例独立版本"""

    MAX_MEMBER_ID = 300
    _log_filename = None  # 新增：存储本次运行生成的日志文件名（所有实例共享）

    def __init__(self, config_path: Optional[str] = None):
        # 创建配置实例
        self._config = Config(config_path)
        Figure.load_config(self._config)


        # 所有状态改为实例属性，确保实例隔离
        self._members: Dict[int, 'Figure'] = {}
        self._factions: Dict[str, 'Faction'] = {}
        self._treasury: int = 0
        self._national_public_land = 0
        self._turn: 'GameTurn' = None
        self._event_log: List[str] = []
        self._used_ids: Set[int] = set()
        self._mortality_pool: List[int] = []

        self._war_system: Optional['WarSystem'] = None
        self._military_system: Optional['MilitarySystem'] = None
        self._curia: Optional[Curia] = None
        self._contracts: List[Any] = []

        # 阶段执行跟踪
        self._executed_phases: Set[str] = set()
        self._phase_results: Dict[str, Any] = {}

        # MVP 0.5 新增字段
        self._provinces: Dict[int, Province] = {}
        self._contracts_dict: Dict[int, Contract] = {}
        self._public_land_total: int = 0
        self._contract_id_counter: int = 1
        self._treasury_deficit_turns = 0
        self._pending_land_acts: List[Dict] = []  # 新增

        # ---------- 新增：日志记录器 ----------
        self._logger: Optional[logging.Logger] = None
        self._setup_logging()
        self._log_filename = None

        # ---------- 新增：战争系统 MVP0.7-4 ----------

        self._naval_system: Optional['NavalSystem'] = None   # 海军系统实例（稍后赋值）
        self._pyrrhic_war_won: bool = False                   # 皮洛士战争胜利标记
        self._wartime_tax_collected: int = 0                  # 财产税已收总额（预留）
        self._tax_refund_due: int = 0                          # 待返还财产税（预留）
        self._naval_system = NavalSystem(self)

        # ---------- 新增：天命系统 MVP0.7-5~8 ----------
        self._active_events: Dict[str, Any] = {}           # 本回合生效的事件
        self._hero_spawned_this_turn: bool = False         # 本回合是否有英雄生成
        self._hero_to_spawn: Optional[Dict] = None         # 待生成英雄的数据
        self._spawned_hero_ids: Set[str] = set()           # 已出现的历史人物卡ID
        # MVP 0.7 城市系统预留
        self._cities: Dict[int, City] = {}
        self._city_id_counter: int = 1

        # ---------- 新增：玩家系统 MVP0.7.11-12 ----------

        self._players: Dict[str, 'Player'] = {}  # 玩家ID -> Player对象
        self._current_player_id: Optional[str] = None  # 当前操作玩家ID
        self._turn_order: List[str] = []  # 回合顺序（玩家ID列表）
        # 广场阶段
        self._forum_pending = {
            "retirements": [],  # 被淘汰的人物ID列表
            "recruitment_bids": [],  # 招募出价记录，每个元素为 (faction_id, figure_id, amount)
            "contract_bids": [],  # 合同竞标记录，每个元素为 (contract_id, faction_id, amount)
            "land_purchases": [],  # 公地认购记录，每个元素为 (faction_id, amount)
            "triumph_votes": [],  # 凯旋投票记录，每个元素为 (faction_id, vote)  # vote为True/False
            "land_trades": [],  # 土地交易记录，每个元素为 (seller_id, buyer_id, land, price)
            "market_opened": [],  # GUI/CLI market generation guard
        }

        # 人口阶段临时存储
        self._population_pending = {
            "campaigns": [],  # 每个元素为 (player_id, figure_id, amount)
            "votes": [],  # 每个元素为 (player_id, office, figure_id)
            "committed_batches": set(),  # 已提交的批次签名（幂等守卫）
            "committed_vote_batches": set(),
        }
        # WP-02a v3: runtime guard (不持久化) + 按 player_id 完成状态
        self._batch_guard_lock = threading.Lock()  # runtime 互斥，不序列化
        self._batch_completed_by_player: Dict[str, bool] = {}  # player_id → completed
        self._vote_completed_by_player: Dict[str, bool] = {}

        # 元老院阶段临时存储
        self._pending_land_sale_quota: int = 0  # 新增：贵族买地法案待售公地数量
        self._senate_pending = {
            "proposals": [],  # 列表，每个元素为提案字典
            "votes": {},  # {player_id: {proposal_id: bool}}
            "vetoes": set(),  # 被否决的提案ID集合
            "proposal_id_counter": 1
        }

        # 初始化时调用 reset，确保状态一致性
        self.reset()

    def reset(self):
        """重置状态 - 实例方法，仅影响当前实例"""
        self._members.clear()
        self._factions.clear()
        self._treasury = 0
        self._national_public_land = 0
        self._turn = None
        self._event_log.clear()
        self._used_ids.clear()
        self._initialize_mortality_pool()

        # 重置系统（重新创建）
        self._war_system = WarSystem(self)
        self._war_system.load_wars_from_json("wars.json")
        self._military_system = MilitarySystem(self)  # <-- 创建军事系统实例
        self._curia = Curia()
        self._contracts.clear()
        self._executed_phases.clear()
        self._phase_results.clear()

        # MVP 0.5 重置新增字段
        self._provinces.clear()
        self._contracts_dict.clear()
        self._public_land_total = 0
        self._contract_id_counter = 1

        self._pending_land_acts.clear()  # 新增
        self._naval_system = None
        self._pyrrhic_war_won = False
        self._wartime_tax_collected = 0
        self._tax_refund_due = 0

        self._naval_system = NavalSystem(self)

        # MVP 0.7 城市系统重置
        self._cities.clear()
        self._city_id_counter = 1

        #新增：玩家系统 MVP0.7.11-12
        self._players.clear()
        self._current_player_id = None
        self._turn_order.clear()
        self._forum_pending = {k: [] for k in self._forum_pending}
        self._population_pending = {
            "campaigns": [],
            "votes": [],
            "committed_batches": set(),
            "committed_vote_batches": set(),
        }
        self._batch_completed_by_player.clear()
        self._vote_completed_by_player.clear()
        self._batch_guard_lock = threading.Lock()  # fresh runtime lock, 不序列化
        self._pending_land_sale_quota: int = 0  # 新增：贵族买地法案待售公地数量
        self.clear_senate_pending()

    #========================= 功能函数 ===================================

    # 元老阶段玩家操作
    def add_senate_proposal(self, proposal: dict) -> int:
        """添加提案，返回分配ID"""
        proposal_id = self._senate_pending["proposal_id_counter"]
        self._senate_pending["proposal_id_counter"] += 1
        proposal["id"] = proposal_id
        self._senate_pending["proposals"].append(proposal)
        return proposal_id

    def get_senate_proposals(self) -> list:
        """获取当前所有提案的副本"""
        return self._senate_pending["proposals"].copy()

    def get_senate_votes_copy(self) -> dict:
        """获取当前元老院投票记录副本。"""
        return {
            player_id: votes.copy()
            for player_id, votes in self._senate_pending["votes"].items()
        }

    def get_senate_vetoes_copy(self) -> set:
        """获取当前元老院否决记录副本。"""
        return self._senate_pending["vetoes"].copy()

    def has_senate_vote(self, player_id: str, proposal_id: int) -> bool:
        """检查玩家是否已对指定提案投票。"""
        return proposal_id in self._senate_pending["votes"].get(player_id, {})

    def clear_senate_votes(self) -> None:
        """清空当前元老院投票记录，保留提案与否决状态。"""
        self._senate_pending["votes"] = {}

    def record_senate_vote(self, player_id: str, proposal_id: int, vote: bool) -> bool:
        """记录投票，返回是否成功（未重复投票）"""
        if player_id not in self._senate_pending["votes"]:
            self._senate_pending["votes"][player_id] = {}
        if proposal_id in self._senate_pending["votes"][player_id]:
            return False  # 已投过票
        self._senate_pending["votes"][player_id][proposal_id] = vote
        return True

    def record_senate_veto(self, proposal_id: int) -> bool:
        """记录否决"""
        self._senate_pending["vetoes"].add(proposal_id)
        return True

    def clear_senate_pending(self):
        """清空所有元老院临时数据"""
        self._senate_pending = {
            "proposals": [],
            "votes": {},
            "vetoes": set(),
            "proposal_id_counter": 1
        }

    # 人口阶段玩家操作
    def record_population_campaign(self, player_id: str, figure_id: int, amount: int) -> None:
        """记录一次已完成的庆典。"""
        self._population_pending["campaigns"].append((player_id, figure_id, amount))

    def get_population_campaigns(self) -> list:
        """返回庆典记录副本。"""
        return self._population_pending["campaigns"].copy()

    def record_population_vote(
        self,
        player_id: str,
        office: str,
        figure_id: int,
        replace: bool = False
    ) -> bool:
        """记录人口阶段投票；replace=True 时覆盖同玩家同官职旧票。"""
        votes = self._population_pending["votes"]
        existing_index = next(
            (
                index
                for index, vote in enumerate(votes)
                if vote[0] == player_id and vote[1] == office
            ),
            None
        )
        if existing_index is not None:
            if not replace:
                return False
            votes[existing_index] = (player_id, office, figure_id)
            return True
        votes.append((player_id, office, figure_id))
        return True

    def get_population_votes(self) -> list:
        """返回投票记录副本。"""
        return self._population_pending["votes"].copy()

    def get_population_pending_snapshot(self) -> dict:
        """返回人口阶段临时数据快照。"""
        return {
            "campaigns": self.get_population_campaigns(),
            "votes": self.get_population_votes(),
            "committed_batches": self.get_committed_batches(),
            "committed_vote_batches": self.get_committed_vote_batches(),
        }

    def clear_population_pending(self) -> None:
        """清空人口阶段临时数据。"""
        self._population_pending = {
            "campaigns": [],
            "votes": [],
            "committed_batches": set(),
            "committed_vote_batches": set(),
        }
        self._batch_completed_by_player.clear()
        self._vote_completed_by_player.clear()
        # 注意：_batch_guard_lock 不在此清空——runtime guard 绝不持久化

    def record_committed_batch(self, signature: str) -> None:
        """记录已提交的批量批次签名。"""
        self._population_pending["committed_batches"].add(signature)

    def has_committed_batch(self, signature: str) -> bool:
        """检查批次签名是否已提交（幂等守卫）。"""
        return signature in self._population_pending["committed_batches"]

    def remove_committed_batch(self, signature: str) -> None:
        """移除单个已提交的批次签名（回滚时调用）。"""
        self._population_pending["committed_batches"].discard(signature)

    def clear_committed_batches(self) -> None:
        """清除所有已提交的批次签名（在年度推进时一并清理）。"""
        self._population_pending["committed_batches"].clear()

    def get_committed_batches(self) -> set:
        """返回已提交批次签名副本。"""
        return self._population_pending["committed_batches"].copy()

    def has_committed_vote_batch(self, signature) -> bool:
        return signature in self._population_pending["committed_vote_batches"]

    def record_committed_vote_batch(self, signature) -> None:
        self._population_pending["committed_vote_batches"].add(signature)

    def remove_committed_vote_batch(self, signature) -> None:
        self._population_pending["committed_vote_batches"].discard(signature)

    def get_committed_vote_batches(self) -> set:
        return self._population_pending["committed_vote_batches"].copy()

    def snapshot_vote_state(self) -> list:
        return self.get_population_votes()

    def restore_vote_state(self, snapshot: list) -> None:
        self._population_pending["votes"] = list(snapshot)

    def set_vote_completed(self, player_id: str, value: bool) -> None:
        self._vote_completed_by_player[player_id] = bool(value)

    def get_vote_completed(self, player_id: str) -> bool:
        return self._vote_completed_by_player.get(player_id, False)

    def truncate_population_campaigns(self, target_len: int) -> None:
        """截断 campaign 记录到指定长度（回滚时调用）。"""
        campaigns = self._population_pending["campaigns"]
        if target_len < 0:
            target_len = 0
        while len(campaigns) > target_len:
            campaigns.pop()

    # ────────── WP-02a v3: runtime guard + 按玩家完成状态 ──────────

    def try_acquire_batch_guard(self, owner: str = "") -> bool:
        """
        尝试获取运行时互斥守卫（不可序列化）。
        使用 threading.Lock 保证包括同一线程在内的并发提交均返回 BUSY。
        返回 True 表示获取成功，False 表示 BUSY（其他提交进行中）。

        注意：幂等性检查不由本方法负责，由 caller 在获取 guard 前完成。
        """
        acquired = self._batch_guard_lock.acquire(blocking=False)
        if acquired:
            self.log_event(
                "BATCH_GUARD: acquired",
                level=logging.DEBUG
            )
        else:
            self.log_event(
                "BATCH_GUARD: BUSY, another commit in progress",
                level=logging.DEBUG
            )
        return acquired

    def release_batch_guard(self) -> None:
        """
        释放运行时互斥守卫。
        此方法必须在 finally 块中调用，确保异常路径也释放。
        """
        try:
            self._batch_guard_lock.release()
            self.log_event(
                "BATCH_GUARD: released",
                level=logging.DEBUG
            )
        except RuntimeError:
            # 未持有锁时释放可能抛 RuntimeError，安全忽略
            pass

    def set_batch_completed(self, player_id: str, value: bool) -> None:
        """
        按 player_id 设置批次提交完成状态。
        D-12: p1 成功不推进 p2。
        """
        if value:
            self._batch_completed_by_player[player_id] = True
        else:
            self._batch_completed_by_player.pop(player_id, None)
        self.log_event(
            f"batch_completed_by_player[{player_id}]={'True' if value else 'False'}",
            level=logging.DEBUG
        )

    def get_batch_completed(self, player_id: str) -> bool:
        """
        按 player_id 返回批次提交是否已完成。
        D-12: 每个玩家独立判断。
        """
        return self._batch_completed_by_player.get(player_id, False)

    def clear_all_batch_completed(self) -> None:
        """清空所有玩家的完成状态（年度推进时调用）。"""
        self._batch_completed_by_player.clear()
        self.log_event(
            "batch_completed_by_player: all cleared",
            level=logging.DEBUG
        )

    def snapshot_campaign_figures(
        self,
        entries: List[Tuple[int, int, Any]]
    ) -> Dict[int, Dict[str, int]]:
        """
        对即将修改的人物字段拍摄快照。
        entries: [(figure_id, amount, figure), ...]
        返回: {figure_id: {wealth, popularity}, ...}
        只通过公开属性访问，不写私有字段。
        """
        snapshots: Dict[int, Dict[str, int]] = {}
        for fid, amount, figure in entries:
            snapshots[fid] = {
                "wealth": figure.wealth,
                "popularity": figure.popularity,
            }
        return snapshots

    def restore_campaign_figures(
        self,
        snapshots: Dict[int, Dict[str, int]]
    ) -> None:
        """
        从快照恢复人物字段（回滚时调用）。
        只通过公开属性写入，不操作私有字段。
        然后调用 figure.update_influence() 保证影响力一致。
        """
        for fid, snap in snapshots.items():
            figure = self._members.get(fid)
            if figure is None:
                continue
            figure.wealth = snap["wealth"]
            figure.popularity = snap["popularity"]
            # 用公开方法重新计算影响力
            figure.update_influence()
        self.log_event(
            f"restore_campaign_figures: restored {len(snapshots)} figures from snapshot",
            level=logging.DEBUG
        )

    # 广场阶段玩家操作
    def add_forum_action(self, category: str, data) -> None:
        """添加广场阶段操作记录"""
        if category in self._forum_pending:
            self._forum_pending[category].append(data)
            self.log_event(f"添加广场操作: {category} - {data}", level=logging.DEBUG,
                           extra={"category": category, "data": data})

    def clear_forum_pending(self) -> None:
        """清除所有广场阶段临时数据"""
        for key in self._forum_pending:
            self._forum_pending[key] = []

    def clear_forum_action(self, category: str) -> None:
        """清除指定类别的广场阶段临时数据。"""
        if category in self._forum_pending:
            self._forum_pending[category] = []

    def get_forum_pending(self) -> dict:
        """获取当前所有广场阶段临时数据副本"""
        return {k: v.copy() for k, v in self._forum_pending.items()}


    # ========== 玩家管理 ==========

    def add_player(self, player: 'Player') -> None:
        """添加玩家"""
        self._players[player.player_id] = player
        self.log_event(f"添加玩家: {player.player_id}", level=logging.DEBUG,
                       extra={"player_id": player.player_id, "faction": player.faction_id})

    def get_player(self, player_id: str) -> Optional['Player']:
        """根据ID获取玩家"""
        return self._players.get(player_id)

    def get_all_players(self) -> List['Player']:
        """获取所有玩家列表"""
        return list(self._players.values())

    def get_player_by_faction(self, faction_id: str) -> Optional['Player']:
        """根据派系ID获取玩家（假设一个派系最多一个玩家）"""
        for player in self._players.values():
            if player.faction_id == faction_id:
                return player
        return None

    def remove_player(self, player_id: str) -> bool:
        """移除玩家"""
        if player_id in self._players:
            del self._players[player_id]
            if self._current_player_id == player_id:
                self._current_player_id = None
            if player_id in self._turn_order:
                self._turn_order.remove(player_id)
            self.log_event(f"移除玩家: {player_id}", level=logging.DEBUG,
                           extra={"player_id": player_id})
            return True
        return False

    def set_turn_order(self, order: List[str]) -> None:
        """设置回合顺序（玩家ID列表）"""
        self._turn_order = order
        self.log_event(f"设置回合顺序: {order}", level=logging.DEBUG,
                       extra={"turn_order": order})

    def get_current_player(self) -> Optional['Player']:
        """获取当前玩家"""
        if self._current_player_id:
            return self._players.get(self._current_player_id)
        return None

    def set_current_player(self, player_id: str) -> bool:
        """设置当前玩家"""
        if player_id in self._players:
            self._current_player_id = player_id
            self.log_event(f"设置当前玩家: {player_id}", level=logging.DEBUG,
                           extra={"player_id": player_id})
            return True
        return False

    def next_player(self) -> Optional[str]:
        """
        切换到下一个玩家，返回新玩家ID。
        如果轮完一圈则返回第一个玩家（循环）。
        如果没有玩家则返回 None。
        """
        if not self._turn_order:
            return None
        if self._current_player_id not in self._turn_order:
            # 当前玩家不在顺序中，默认从第一个开始
            self._current_player_id = self._turn_order[0]
            return self._current_player_id
        idx = self._turn_order.index(self._current_player_id)
        next_idx = (idx + 1) % len(self._turn_order)
        self._current_player_id = self._turn_order[next_idx]
        self.log_event(f"切换到下一个玩家: {self._current_player_id}", level=logging.DEBUG,
                       extra={"new_player": self._current_player_id})
        return self._current_player_id

    def is_current_player(self, player_id: str) -> bool:
        """检查指定ID是否为当前玩家"""
        return self._current_player_id == player_id


    def log_exception(self, e: Exception, context: str = "", extra: dict = None):
        """
        记录异常日志，包含异常类型、消息和可选的上下文信息。
        Args:
            e: 异常对象
            context: 自定义上下文描述
            extra: 额外的结构化字段
        """
        import traceback
        tb_str = traceback.format_exc()
        log_extra = {
            "exception_type": type(e).__name__,
            "exception_msg": str(e),
            "traceback": tb_str,
        }
        if extra:
            log_extra.update(extra)
        if context:
            log_extra["context"] = context
        self.log_event(f"异常: {context} - {type(e).__name__}: {e}", level=logging.ERROR, extra=log_extra)

    def _setup_logging(self):
        """根据配置初始化文件日志（每个实例独立，但使用同一文件）"""
        log_config = self._config.get("logging", {})
        if not log_config.get("enabled", False):
            return

        # 如果类变量未设置，则生成带时间戳的文件名
        if GameState._log_filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = log_config.get("file_path", "logs/game.log")
            # 分离目录和文件名，插入时间戳
            dir_name = os.path.dirname(base_name)
            base_file = os.path.basename(base_name)
            name, ext = os.path.splitext(base_file)
            new_name = f"{name}_{timestamp}{ext}"
            GameState._log_filename = os.path.join(dir_name, new_name)

        file_path = GameState._log_filename
        max_bytes = log_config.get("max_bytes", 10485760)
        backup_count = log_config.get("backup_count", 3)
        level_str = log_config.get("log_level", "INFO")

        level = getattr(logging, level_str.upper(), logging.INFO)

        # 确保日志目录存在
        log_dir = os.path.dirname(file_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        # 创建独立 logger，不通过 getLogger 共享
        self._logger = logging.Logger(name=f"EOR-{id(self)}", level=level)
        handler = logging.handlers.RotatingFileHandler(
            file_path, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8'
        )
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)
        self._logger.propagate = False  # 防止日志传播到根 logger

    def log_event(self, message: str, level: int = logging.INFO, extra: dict = None):
        """
        记录事件到内存日志，并写入文件日志（如果启用）
        Args:
            message: 日志消息
            level: 日志级别，默认为 INFO
            extra: 附加的结构化字段，如 {"war_id": "war1", "amount": 100}
        """
        self._event_log.append(message)
        if self._logger:
            log_msg = message
            if extra:
                extra_str = " ".join([f"{k}={v}" for k, v in extra.items()])
                log_msg = f"{extra_str} - {message}"
            self._logger.log(level, log_msg)

    def close_logging(self):
        """关闭日志处理器，释放文件句柄（主要用于测试）"""
        if self._logger:
            for handler in self._logger.handlers[:]:
                handler.close()
                self._logger.removeHandler(handler)



    # ========== 序列化 ==========
    def to_dict(self) -> Dict[str, Any]:
        """将游戏状态序列化为字典，用于存档。"""
        data = {
            "_treasury": self._treasury,
            "_national_public_land": self._national_public_land,
            "_turn": self._turn.to_dict() if self._turn else None,
            "_executed_phases": list(self._executed_phases),
            "_phase_results": self._phase_results.copy(),
            "_contract_id_counter": self._contract_id_counter,
            "_treasury_deficit_turns": self._treasury_deficit_turns,
            "_pending_land_acts": self._pending_land_acts.copy(),
            "_pyrrhic_war_won": self._pyrrhic_war_won,
            "_wartime_tax_collected": self._wartime_tax_collected,
            "_tax_refund_due": self._tax_refund_due,
            # 实体集合
            "_members": {mid: member.to_dict() for mid, member in self._members.items()},
            "_factions": {fid: faction.to_dict() for fid, faction in self._factions.items()},
            "_provinces": {pid: province.to_dict() for pid, province in self._provinces.items()},
            "_contracts_dict": {cid: contract.to_dict() for cid, contract in self._contracts_dict.items()},
            # 海军系统
            "_naval_system": self._naval_system.to_dict() if self._naval_system else None,
            # 天命系统
            "_active_events": self._active_events.copy(),
            "_hero_spawned_this_turn": self._hero_spawned_this_turn,
            "_hero_to_spawn": self._hero_to_spawn.copy() if self._hero_to_spawn else None,
            "_spawned_hero_ids": list(self._spawned_hero_ids),
            # 城市系统
            "_cities": {cid: city.to_dict() for cid, city in self._cities.items()},
            "_city_id_counter": self._city_id_counter,
            # 玩家系统
            "_players": {pid: player.to_dict() for pid, player in self._players.items()},
            "_current_player_id": self._current_player_id,
            "_turn_order": self._turn_order.copy(),
            "_population_pending": {
                "campaigns": self._population_pending["campaigns"].copy(),
                "votes": self._population_pending["votes"].copy(),
                "committed_batches": list(self._population_pending["committed_batches"]),
                "committed_vote_batches": list(
                    self._population_pending["committed_vote_batches"]
                ),
            },
            # WP-02a v3: 按 player_id 完成状态（runtime guard 不序列化）
            "_batch_completed_by_player": self._batch_completed_by_player.copy(),
            "_vote_completed_by_player": self._vote_completed_by_player.copy(),
            # Phase 2 新增字段：curia、forum、senate
            "_curia": self._curia.to_dict() if self._curia else None,
            "_forum_pending": self.get_forum_pending(),
            "_senate_pending": {
                "proposals": self._senate_pending["proposals"].copy(),
                "votes": {k: v.copy() for k, v in self._senate_pending["votes"].items()},
                "vetoes": list(self._senate_pending["vetoes"]),
                "proposal_id_counter": self._senate_pending["proposal_id_counter"],
            },
            "_pending_land_sale_quota": self._pending_land_sale_quota,
        }
        return data

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """从字典加载游戏状态，覆盖当前状态。"""
        # 先重置当前状态（清空所有）
        self.reset()

        # 恢复基础字段
        self._treasury = data.get("_treasury", 0)
        self._national_public_land = data.get("_national_public_land", 0)
        if data.get("_turn"):
            from src.core.entities.entities import GameTurn
            self._turn = GameTurn(**data["_turn"])
        self._executed_phases = set(data.get("_executed_phases", []))
        self._phase_results = data.get("_phase_results", {}).copy()
        self._contract_id_counter = data.get("_contract_id_counter", 1)
        self._treasury_deficit_turns = data.get("_treasury_deficit_turns", 0)
        self._pending_land_acts = data.get("_pending_land_acts", []).copy()
        self._pyrrhic_war_won = data.get("_pyrrhic_war_won", False)
        self._wartime_tax_collected = data.get("_wartime_tax_collected", 0)
        self._tax_refund_due = data.get("_tax_refund_due", 0)

        # 恢复人物
        self._members.clear()
        self._used_ids.clear()
        from src.core.entities.figure import Figure
        for mid, member_data in data.get("_members", {}).items():
            member = Figure.from_dict(member_data)
            self._members[int(mid)] = member
            self._used_ids.add(member.id)

        # 恢复派系
        self._factions.clear()
        from src.core.entities.entities import Faction
        for fid, faction_data in data.get("_factions", {}).items():
            faction = Faction.from_dict(faction_data)
            self._factions[fid] = faction

        # 恢复行省
        self._provinces.clear()
        for pid, prov_data in data.get("_provinces", {}).items():
            province = Province.from_dict(prov_data)
            self._provinces[int(pid)] = province

        # 恢复合同
        self._contracts_dict.clear()
        from src.core.entities.contract import Contract
        for cid, contract_data in data.get("_contracts_dict", {}).items():
            contract = Contract.from_dict(contract_data)
            self._contracts_dict[int(cid)] = contract

        # 恢复海军系统
        if data.get("_naval_system") and self._naval_system:
            self._naval_system.load_from_dict(data["_naval_system"])

        # 更新全局公地总数
        self._update_global_public_land()

        # 恢复天命系统
        self._active_events = data.get("_active_events", {}).copy()
        self._hero_spawned_this_turn = data.get("_hero_spawned_this_turn", False)
        self._hero_to_spawn = data.get("_hero_to_spawn")
        self._spawned_hero_ids = set(data.get("_spawned_hero_ids", []))

        # 恢复城市
        self._cities.clear()
        for cid, city_data in data.get("_cities", {}).items():
            city = City.from_dict(city_data)
            self._cities[int(cid)] = city
        self._city_id_counter = data.get("_city_id_counter", 1)

        # 恢复玩家
        self._players.clear()
        from src.core.entities.player import Player
        for pid, player_data in data.get("_players", {}).items():
            self._players[pid] = Player.from_dict(player_data)
        self._current_player_id = data.get("_current_player_id")
        self._turn_order = data.get("_turn_order", []).copy()
        self._population_pending = data.get("_population_pending", {
            "campaigns": [],
            "votes": [],
            "committed_batches": set(),
            "committed_vote_batches": set(),
        })
        # 确保结构完整
        if "campaigns" not in self._population_pending:
            self._population_pending["campaigns"] = []
        if "votes" not in self._population_pending:
            self._population_pending["votes"] = []
        if "committed_batches" not in self._population_pending:
            self._population_pending["committed_batches"] = set()
        elif isinstance(self._population_pending["committed_batches"], list):
            self._population_pending["committed_batches"] = set(
                self._population_pending["committed_batches"]
            )
        self._population_pending["committed_vote_batches"] = set(
            self._population_pending.get("committed_vote_batches", [])
        )

        # WP-02a v3: 按 player_id 完成状态（runtime guard 不序列化）
        raw_bcp = data.get("_batch_completed_by_player", {})
        self._batch_completed_by_player = {}
        for pid, val in raw_bcp.items():
            if isinstance(val, bool):
                self._batch_completed_by_player[pid] = val
        self._vote_completed_by_player = dict(data.get("_vote_completed_by_player", {}))
        # guard 永远是全新的 Lock（不持久化）
        self._batch_guard_lock = threading.Lock()

        # Phase 2 新增：恢复 curia
        if data.get("_curia"):
            from src.core.entities.curia import Curia
            curia = Curia.from_dict(data["_curia"])
            # 解析 pending figure IDs 为实际的 Figure 对象
            for fid in getattr(curia, '_pending_figure_ids', []):
                figure = self._members.get(fid)
                if figure:
                    curia.add_figure(figure)
            self._curia = curia

        # Phase 2 新增：恢复 forum pending
        self._forum_pending = data.get("_forum_pending", {
            "retirements": [],
            "recruitment_bids": [],
            "contract_bids": [],
            "land_purchases": [],
            "triumph_votes": [],
            "land_trades": [],
            "market_opened": [],
        })
        # 确保所有 key 都存在
        required_forum_keys = [
            "retirements", "recruitment_bids", "contract_bids",
            "land_purchases", "triumph_votes", "land_trades", "market_opened",
        ]
        for key in required_forum_keys:
            if key not in self._forum_pending:
                self._forum_pending[key] = []

        # Phase 2 新增：恢复 senate pending
        senate_data = data.get("_senate_pending", {})
        self._senate_pending = {
            "proposals": senate_data.get("proposals", []).copy(),
            "votes": {k: v.copy() for k, v in senate_data.get("votes", {}).items()},
            "vetoes": set(senate_data.get("vetoes", [])),
            "proposal_id_counter": senate_data.get("proposal_id_counter", 1),
        }

        # Phase 2 新增：恢复待售公地配额
        self._pending_land_sale_quota = data.get("_pending_land_sale_quota", 0)

    def _initialize_mortality_pool(self):
        """初始化天命池"""
        self._mortality_pool = list(range(1, self.MAX_MEMBER_ID + 1))
        random.shuffle(self._mortality_pool)

    @classmethod
    def create_for_testing(cls, test_config: Dict[str, Any]) -> 'GameState':
        """
        工厂方法: 创建测试专用实例
        绕过 __init__，直接注入测试配置，避免文件依赖
        """
        instance = cls.__new__(cls)
        instance._members = {}
        instance._factions = {}
        instance._treasury = 0
        instance._turn = None
        instance._event_log = []
        instance._used_ids = set()
        instance._mortality_pool = []
        instance._config = Config()
        instance._config._config = test_config
        instance._war_system = None
        instance._military_system = None
        instance._curia = Curia()
        instance._contracts = []
        instance._executed_phases = set()
        instance._phase_results = {}
        instance._initialize_mortality_pool()

        # MVP 0.5 新增字段
        instance._provinces = {}
        instance._contracts_dict = {}
        instance._public_land_total = 0
        instance._contract_id_counter = 1
        instance._national_public_land = test_config.get("economic_rules", {}).get("initial_national_public_land", 1000)
        instance._pending_land_acts = []
        instance._treasury_deficit_turns = 0

        # MVP 0.7 新增字段
        instance._active_events = {}
        instance._hero_spawned_this_turn = False
        instance._hero_to_spawn = None
        instance._spawned_hero_ids = set()

        # ---------- 新增：日志记录器 ----------
        instance._logger = None
        instance._setup_logging()

        # ----------新增：MVP 0.7-4 战争系统------------
        instance._naval_system = None
        instance._pyrrhic_war_won = False
        instance._wartime_tax_collected = 0
        instance._tax_refund_due = 0

        # MVP 0.7 城市系统预留
        instance._cities = {}
        instance._city_id_counter = 1

        # MVP 0.7.11-12 玩家系统
        instance._players = {}
        instance._current_player_id = None
        instance._turn_order = []
        instance._forum_pending = {
            "retirements": [],
            "recruitment_bids": [],
            "contract_bids": [],
            "land_purchases": [],
            "triumph_votes": [],
            "land_trades": [],
            "market_opened": [],
        }
        instance._population_pending = {
            "campaigns": [],
            "votes": [],
            "committed_batches": set(),
            "committed_vote_batches": set(),
        }
        instance._batch_completed_by_player = {}
        instance._vote_completed_by_player = {}
        instance._batch_guard_lock = threading.Lock()
        instance._pending_land_sale_quota = 0
        instance._senate_pending = {
            "proposals": [],
            "votes": {},
            "vetoes": set(),
            "proposal_id_counter": 1
        }


        return instance

    # ========== 成员管理 ==========

    def add_member(self, member: 'Figure'):
        """添加人物"""
        self._used_ids.add(member.id)
        self._members[member.id] = member

    def get_member(self, member_id: int) -> Optional['Figure']:
        """获取人物"""
        return self._members.get(member_id)

    def get_living_members(self) -> List['Figure']:
        """获取所有存活人物"""
        return [m for m in self._members.values() if hasattr(m, 'is_dead') and not m.is_dead]

    def get_living_member(self, member_id: int) -> Optional['Figure']:
        """获取存活人物"""
        member = self._members.get(member_id)
        return member if (member and not member.is_dead) else None

    # ========== 新增：人物财富管理 ==========
    def add_figure_wealth(self, figure_id: int, amount: int) -> bool:
        """
        增加/减少人物财富

        Args:
            figure_id: 人物ID
            amount: 增加金额（可为负）

        Returns:
            bool: 操作成功返回 True，人物不存在或已死亡返回 False
        """
        figure = self.get_member(figure_id)
        if not figure or figure.is_dead:
            return False
        figure.wealth += amount
        return True

    # ========== 派系管理 ==========

    def add_faction(self, faction: 'Faction'):
        """添加派系"""
        self._factions[faction.id] = faction

    def get_faction(self, faction_id: str) -> Optional['Faction']:
        """获取派系"""
        return self._factions.get(faction_id)

    def get_active_factions(self) -> List['Faction']:
        """获取活跃派系"""
        active = []
        for faction in self._factions.values():
            living = [m for m in faction.get_members(self) if not m.is_dead]
            if living:
                active.append(faction)
        return active

    # ========== 新增：派系资金管理 ==========
    def add_faction_treasury(self, faction_id: str, amount: int) -> bool:
        """
        增加/减少派系资金

        Args:
            faction_id: 派系ID
            amount: 增加金额（可为负）

        Returns:
            bool: 操作成功返回 True，派系不存在返回 False
        """
        faction = self.get_faction(faction_id)
        if not faction:
            return False
        faction.treasury += amount
        return True

    # ========== 国库管理 ==========

    @property
    def treasury_deficit_turns(self):
        return self._treasury_deficit_turns

    def reset_treasury_deficit_turns(self):
        self._treasury_deficit_turns = 0

    def increment_treasury_deficit_turns(self):
        self._treasury_deficit_turns += 1

    @property
    def treasury(self):
        return self._treasury

    @treasury.setter
    def treasury(self, value):
        self._treasury = value

    # ========== 新增：国库增减方法 ==========
    def add_treasury(self, amount: int) -> int:
        self._treasury += amount
        return self._treasury

    # ========== 新增：公地增减方法 ==========
    def add_national_public_land(self, amount: int) -> None:
        old = self._national_public_land
        self._national_public_land += amount
        self.sync_italy_public_land()

    # ========== 配置获取（通过 Config 实例）==========

    def get_cooldown_years(self) -> int:
        """获取执政官冷却期"""
        return self._config.get("political_rules.leader_cooldown_years", 10)

    def get_leaders_per_election(self) -> int:
        """获取执政官选举人数"""
        return self._config.get("political_rules.leaders_per_election", 2)

    def get_office_cooldown(self, office_type: str) -> int:
        """获取指定公职的冷却期"""
        return self._config.get(f"political_rules.office_cooldowns.{office_type}", 2)

    def get_offices_per_election(self, office_type: str) -> int:
        """获取每次选举该公职的名额"""
        return self._config.get(f"political_rules.offices_per_election.{office_type}", 1)

    def get_min_age(self, office_type: str) -> int:
        """获取指定公职的最低年龄"""
        return self._config.get(f"political_rules.min_ages.{office_type}", 30)

    # ========== 新增：经济规则配置获取 ==========
    def get_economic_rule(self, key: str, default: Any = None) -> Any:
        """
        获取经济规则配置值

        Args:
            key: 配置键，如 "base_tax"
            default: 默认值

        Returns:
            配置值
        """
        return self._config.get(f"economic_rules.{key}", default)

    def check_victory_conditions(self) -> dict:
        """
        Check all victory/failure conditions.

        Also handles treasury deficit turn counting (increment if negative,
        reset if non-negative).

        Returns:
            dict: {
                "game_over": bool,
                "conditions": [
                    {
                        "type": "bankruptcy" | "legions_destroyed" | "revolt_majority"
                               | "dictatorship" | "italy_grievance",
                        "triggered": bool,
                        "details": str,
                        "critical": bool,  # True = triggers game over
                    },
                    ...
                ],
                "summary": {
                    "deficit_turns": int,
                    "deficit_limit": int,
                    "total_influence": int,
                    "top_faction": { "id": str, "name": str, "share": float } | None,
                }
            }
        """
        # 1. Treasury deficit counting
        if self.treasury < 0:
            self.increment_treasury_deficit_turns()
        else:
            self.reset_treasury_deficit_turns()

        deficit = self.treasury_deficit_turns
        limit = self.get_economic_rule("national_opex_deficit_limit", 3)

        conditions = []
        game_over = False

        # Bankruptcy check
        bankruptcy_triggered = deficit >= limit
        if bankruptcy_triggered:
            conditions.append({
                "type": "bankruptcy",
                "triggered": True,
                "details": f"国库连续{limit}回合赤字，共和覆灭！（调试模式仅提示）",
                "critical": True,
            })
            game_over = True
        elif deficit > 0:
            conditions.append({
                "type": "bankruptcy",
                "triggered": False,
                "details": f"国库赤字（第{deficit}回合），再持续{limit - deficit}回合将导致共和覆灭",
                "critical": False,
            })

        # 2. Legions all destroyed
        ms = self.get_military_system()
        all_destroyed = False
        if ms:
            all_legions = ms.get_all_legions()
            if all_legions and all(l.status.name == "DESTROYED" for l in all_legions):
                all_destroyed = True
                conditions.append({
                    "type": "legions_destroyed",
                    "triggered": True,
                    "details": "所有军团已被消灭，共和覆灭！",
                    "critical": True,
                })
                game_over = True

        # 3. Province revolt majority
        provinces = self.get_all_provinces()
        revolt_majority = False
        if provinces:
            revolt_provinces = [p for p in provinces if p.grievance >= 3]
            if len(revolt_provinces) > len(provinces) // 2:
                revolt_majority = True
                conditions.append({
                    "type": "revolt_majority",
                    "triggered": True,
                    "details": "超过半数行省爆发起义，共和覆灭！",
                    "critical": True,
                })
                game_over = True

        # 4. Faction dictatorship (>=70% influence)
        total_senate_influence = 0
        faction_influences = {}
        for faction in self.factions.values():
            inf = faction.get_senate_influence(self)
            total_senate_influence += inf
            faction_influences[faction.id] = inf

        dictatorship = False
        if total_senate_influence > 0:
            for faction in self.factions.values():
                share = faction_influences[faction.id] / total_senate_influence
                if share >= 0.7:
                    dictatorship = True
                    conditions.append({
                        "type": "dictatorship",
                        "triggered": True,
                        "details": f"{faction.name} 获得元老院 {share:.1%} 影响力，可能宣布独裁！",
                        "critical": True,
                    })
                    game_over = True
                    break

        # 5. Italy grievance level 3
        italy = self.get_province(0)
        italy_grievance = False
        if italy and italy.grievance == 3:
            italy_grievance = True
            conditions.append({
                "type": "italy_grievance",
                "triggered": True,
                "details": "意大利本土民怨已达3级，若不在本年度内处理，共和国将面临覆灭！",
                "critical": True,
            })

        # 6. Summary — top faction
        top_faction = None
        if total_senate_influence > 0:
            top_faction_id = max(faction_influences, key=lambda fid: faction_influences[fid])
            top_f = self.get_faction(top_faction_id)
            top_share = faction_influences[top_faction_id] / total_senate_influence
            top_faction = {
                "id": top_f.id,
                "name": top_f.name,
                "share": top_share,
            }

        return {
            "game_over": game_over,
            "conditions": conditions,
            "summary": {
                "deficit_turns": deficit,
                "deficit_limit": limit,
                "total_influence": total_senate_influence,
                "top_faction": top_faction,
            },
        }

    # ========== 天命机制 ==========

    def draw_mortality_number(self) -> int:
        """抽取天命号码"""
        if not self._mortality_pool:
            self._initialize_mortality_pool()
        return self._mortality_pool.pop() if self._mortality_pool else 0

    # ========== 回合管理 ==========

    def advance_year(self):
        """推进到下一年"""
        if self._turn:
            self._turn.advance_year()
        self._executed_phases.clear()
        self._phase_results.clear()

        # P0: curia 清理
        self._cleanup_curia()

        # P0: 清空所有阶段临时数据
        self.clear_population_pending()
        self.clear_forum_pending()
        self.clear_senate_pending()
        self.clear_pending_land_acts()

        # P0: 年度衰减（含年龄递增 — 由 advance_year 统一处理）
        decay_rates = {"veterans": 0.20, "popularity": 0.50}
        for member in self.get_living_members():
            member.apply_annual_decay(decay_rates)
            member.age += 1

        # P0: 临时影响力衰减
        for member in self.get_living_members():
            if member.get_temp_influence() > 0:
                member.decay_temp_influence_tasks()
                member.update_influence()

        # P1: 合同过期处理
        self.process_contract_expiration()

        # P1: 总督交接处理
        self.process_governor_transitions()

        # P1: 和约到期处理
        self.process_truce_expiry()

        # P0: 年度衰减完成日志
        self.log_event(
            f"年度衰减完成: 衰减率 veterans={decay_rates['veterans']}, popularity={decay_rates['popularity']}",
            level=logging.DEBUG
        )

    # ========== P1: 年度推进附加处理 ==========

    def process_contract_expiration(self) -> int:
        """P1: 处理合同过期 - 所有 PENDING 合同存在 ≥3 回合则过期"""
        expired_count = 0
        for contract in self.contracts:
            if getattr(contract, '_is_fleet_construction', False):
                continue
            if contract.status == ContractStatus.PENDING:
                current_turn = self._turn.turn_number if self._turn else 0
                created_turn = contract.create_turn
                turns_pending = current_turn - created_turn
                if turns_pending >= 3:
                    contract.expire()
                    expired_count += 1
                    self.log_event(
                        f"合同 {contract.id} ({contract.contract_type.name}) 已过期，存在 {turns_pending} 回合",
                        level=logging.DEBUG
                    )
        return expired_count

    def process_governor_transitions(self) -> list:
        """P1: 处理总督交接 - 旧总督返回 + 候任总督上任"""
        transitions = []
        for province in self.get_all_provinces():
            designate_id = province.governor_designate_id
            designate = (
                self.get_member(designate_id)
                if designate_id is not None
                else None
            )
            promote_designate = designate is not None and not designate.is_dead
            old_id, designate_id = province.complete_governor_transition(
                self._turn.turn_number if self._turn else 0,
                promote_designate=promote_designate
            )

            # 处理旧总督返回
            if old_id is not None:
                old_fig = self.get_member(old_id)
                if old_fig is not None and not old_fig.is_dead:
                    assert old_fig is not None
                    old_fig.is_absent = False
                    old_fig.office = None
                    old_fig.update_influence()
                    self.log_event(
                        f"旧总督 {old_fig.get_formal_name()} 返回罗马 (province_id={province.province_id})",
                        level=logging.DEBUG
                    )

            # 处理候任总督上任或跳过
            if promote_designate:
                designate.office = province.governor_type
                designate.update_influence()
                self.log_event(
                    f"新总督 {designate.get_formal_name()} 正式上任 {province.name} (province_id={province.province_id})",
                    level=logging.DEBUG
                )
            else:
                self.log_event(
                    f"行省 {province.name} (ID={province.province_id}) 无候任总督，跳过交接",
                    level=logging.DEBUG
                )

            transitions.append({
                "province_id": province.province_id,
                "old_governor_id": old_id,
                "new_governor_id": designate_id if promote_designate else None,
            })
        return transitions

    def process_truce_expiry(self) -> list:
        """P1: 处理和约到期 - 到期停战转为威胁"""
        war_system = self.get_war_system()
        if not war_system:
            return []

        current_turn = self._turn.turn_number if self._turn else 0
        truce_wars = war_system.get_truce_wars_with_approved_treaty()
        expired = []
        for war in truce_wars:
            if war.is_truce_expired(current_turn):
                # noinspection PyProtectedMember
                war_system._move_to_threat(war, threat_level=1)
                war.clear_peace_treaty()
                expired.append(war.name)
                self.log_event(
                    f"和约到期: {war.name} (ID={war.id}) 重启威胁",
                    level=logging.DEBUG
                )
        if expired:
            self.log_event(
                f"{len(expired)} 场战争和约到期",
                level=logging.DEBUG
            )
        return expired

    def _cleanup_curia(self) -> None:
        """P0-1: 清理人才市场中无派系的广场人物。"
        
        - 无 faction_id 的人物（广场生成的新人物）→ 从 _members 删除
        - 有 faction_id 的人物（退休的派系成员）→ 保留在 _members 中
        """
        curia = self._curia
        if curia and not curia.is_empty():
            for fig in curia.get_all_available():
                if fig.faction_id is None:
                    self._members.pop(fig.id, None)
            curia.available_figures = [
                fig for fig in curia.available_figures
                if fig.faction_id is not None
            ]

    def is_phase_executed(self, phase_name: str) -> bool:
        """检查阶段是否已执行"""
        return phase_name in self._executed_phases

    def mark_phase_executed(self, phase_name: str):
        """标记阶段已执行"""
        self._executed_phases.add(phase_name)

    def record_phase_result(self, phase_id: str, result: Any) -> None:
        """记录阶段结算结果，供 GUI/API 在阶段推进前后读取。"""
        self._phase_results[phase_id] = copy.deepcopy(result)

    def get_phase_result(self, phase_id: str) -> Any:
        """读取阶段结算结果。"""
        return copy.deepcopy(self._phase_results.get(phase_id))

    def clear_phase_result(self, phase_id: str) -> None:
        """清除阶段结算结果。"""
        self._phase_results.pop(phase_id, None)

    # ========== 战争/军事系统 ==========

    # ---------- MVP0.7-4 战争类访问方法 ----------
    @property
    def naval_system(self) -> Optional['NavalSystem']:
        return self._naval_system

    @naval_system.setter
    def naval_system(self, value):
        self._naval_system = value

    @property
    def pyrrhic_war_won(self) -> bool:
        return self._pyrrhic_war_won

    @pyrrhic_war_won.setter
    def pyrrhic_war_won(self, value: bool):
        self._pyrrhic_war_won = value

    # ---------- 其他战争类 ----------

    def get_war_system(self) -> Optional['WarSystem']:
        """获取战争系统"""
        return self._war_system

    #def get_active_wars(self) -> List[Any]:
    #    """获取活跃战争列表"""
    #    return []

    def get_military_system(self) -> Optional['MilitarySystem']:
        """获取军事系统"""
        return self._military_system

    def is_military_prepared(self) -> bool:
        """检查军事准备状态"""
        return True

    def get_military_preparation_status(self) -> tuple:
        """获取军事准备详细状态"""
        return True, [], []

    # ========== 主持人 ==========

    def get_presiding_officer(self) -> Optional['Figure']:
        """获取元老院主持人（官职等级最高且未出征者，同等级则选影响力高者）"""
        candidates = [
            m for m in self._members.values()
            if not m.is_dead and m.is_present and not m.is_absent  # 新增 is_absent 过滤
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda m: (m.rank, m.influence))

    # ========== 日志 ==========

    def log_event(self, message: str, level: int = logging.INFO, extra: dict = None):
        """
        记录事件到内存日志，并写入文件日志（如果启用）
        Args:
            message: 日志消息
            level: 日志级别，默认为 INFO
            extra: 附加的结构化字段，如 {"war_id": "war1", "amount": 100}
        """
        self._event_log.append(message)
        if self._logger:
            log_msg = message
            if extra:
                extra_str = " ".join([f"{k}={v}" for k, v in extra.items()])
                log_msg = f"{extra_str} - {message}"
            self._logger.log(level, log_msg)

    def get_status_summary(self) -> str:
        """生成状态摘要"""
        return f"GameState [国库:{self._treasury}, 人物:{len(self.get_living_members())}]"

    # ========== ID 分配 ==========

    def allocate_id(self, preferred_id: Optional[int] = None) -> int:
        """分配成员ID"""
        if preferred_id and preferred_id not in self._used_ids:
            if 1 <= preferred_id <= self.MAX_MEMBER_ID:
                self._used_ids.add(preferred_id)
                return preferred_id

        available = set(range(1, self.MAX_MEMBER_ID + 1)) - self._used_ids
        if not available:
            raise ValueError("No available IDs!")

        new_id = random.choice(list(available))
        self._used_ids.add(new_id)
        return new_id

    # ========== 死亡标记（之前添加）==========
    def mark_member_dead(self, member_id: int, transfer_land: bool = True, transfer_wealth: bool = True) -> bool:
        """
        标记指定ID的人物为死亡，并回收资产

        Args:
            member_id: 要标记死亡的人物ID
            transfer_land: 是否将私地转为国家公地
            transfer_wealth: 是否将财富归入国库

        Returns:
            bool: 操作成功返回 True，人物不存在或已死亡返回 False
        """
        member = self._members.get(member_id)
        if not member:
            return False
        if member.is_dead:
            return False

        # 财富回收：归入国库
        if transfer_wealth and member.wealth > 0:
            self.add_treasury(member.wealth)
            print(f"      💰 {member.get_formal_name()} 的 {member.wealth} Talents 归入国库")
            member.wealth = 0

        # 土地回收：将私地转为国家公地
        if transfer_land:
            land = member._land_private
            if land > 0:
                self.add_national_public_land(land)
                print(f"      🏞️ 当前国家公地: {self._national_public_land - land} C (土地回收前)")
                print(f"      🏞️ 土地回收后国家公地: {self._national_public_land} C (+{land})")
                member._land_private = 0

        member.is_dead = True

        if member.is_faction_leader:
            member.is_faction_leader = False

        if self._turn and hasattr(self._turn, 'leader_ids'):
            if member_id in self._turn.leader_ids:
                self._turn.leader_ids.remove(member_id)
                self.log_event(
                    f"[DEBUG] 死亡人物 {member_id} 从 leader_ids 移除",
                    level=logging.DEBUG,
                    extra={"figure_id": member_id, "leader_ids_after": self._turn.leader_ids.copy()}
                )

        return True

    # ========== 属性访问 ==========

    @property
    def pending_land_sale_quota(self) -> int:
        """获取待售公地配额"""
        return self._pending_land_sale_quota

    def set_pending_land_sale_quota(self, quota: int) -> None:
        """设置待售公地配额（用于元老院通过贵族买地法案）"""
        self._pending_land_sale_quota = quota
        self.log_event(
            f"设置待售公地配额: {quota} C",
            level=logging.DEBUG,
            extra={"quota": quota}
        )

    def clear_pending_land_sale_quota(self) -> None:
        """清除待售公地配额（公示结算后调用）"""
        self._pending_land_sale_quota = 0

    @property
    def active_events(self) -> Dict[str, Any]:
        """返回当前生效的事件字典副本"""
        return self._active_events.copy()

    def record_active_event(self, event_key: str, payload: Any) -> None:
        """记录本回合生效事件，供阶段服务写入权威状态。"""
        self._active_events[event_key] = payload

    def clear_active_events(self):
        """清除本回合生效的事件（在决议阶段调用）"""
        self._active_events.clear()

    @property
    def hero_spawned_this_turn(self) -> bool:
        return self._hero_spawned_this_turn

    @hero_spawned_this_turn.setter
    def hero_spawned_this_turn(self, value: bool):
        self._hero_spawned_this_turn = value

    @property
    def hero_to_spawn(self) -> Optional[Dict]:
        return self._hero_to_spawn

    @hero_to_spawn.setter
    def hero_to_spawn(self, value: Optional[Dict]):
        self._hero_to_spawn = value

    @property
    def spawned_hero_ids(self) -> Set[str]:
        return self._spawned_hero_ids

    def add_spawned_hero_id(self, hero_id: str):
        """记录已生成的历史人物ID"""
        self._spawned_hero_ids.add(hero_id)

    @property
    def members(self):
        return self._members

    @property
    def factions(self):
        return self._factions

    @property
    def turn(self):
        return self._turn

    @turn.setter
    def turn(self, value):
        self._turn = value

    @property
    def event_log(self):
        return self._event_log

    @property
    def mortality_pool(self):
        return self._mortality_pool

    @property
    def config(self):
        """获取配置实例"""
        return self._config

    @property
    def executed_phases(self):
        return self._executed_phases

    @property
    def contracts(self):
        """获取合同列表（从 _contracts_dict 获取）"""
        return list(self._contracts_dict.values())

    @property
    def curia(self) -> Curia:
        """获取广场等待区实例"""
        return self._curia

    @contracts.setter
    def contracts(self, value):
        """兼容旧版设置"""
        self._contracts = value

    # ==================== MVP 0.5 新增接口 ====================

    # ----------公地管理----------
    def get_national_public_land(self) -> int:
        """获取国家公地总量"""
        return self._national_public_land

    def add_pending_land_act(self, act: dict):
        self._pending_land_acts.append(act)

    def get_pending_land_acts(self) -> List[dict]:
        return self._pending_land_acts.copy()

    def clear_pending_land_acts(self):
        self._pending_land_acts.clear()

    # ---------- 行省管理 ----------
    def conquer_provinces(self, war_id: str) -> None:
        war_system = self.get_war_system()
        if not war_system:
            return
        war = war_system.get_war_by_id(war_id)
        if not war:
            return
        for province_id in war.unlocked_provinces:
            province = self.get_province(province_id)
            if not province or province.conquered:
                continue

            # ----- 新增调试打印 -----
            # 如果需要记录到日志（DEBUG级别）：
            self.log_event(
                f"[DEBUG] 征服前行省 {province.name} (ID:{province_id}) governor_type = {province.governor_type}",
                level=logging.DEBUG,
                extra={"province_id": province_id, "governor_type": province.governor_type, "phase": "pre_conquest"}
            )
            # ------------------------

            province._conquered = True
            province.set_grievance(3)

            # ----- 新增调试打印 -----
            self.log_event(
                f"[DEBUG] 征服后行省 {province.name} (ID:{province_id}) governor_type = {province.governor_type}",
                level=logging.DEBUG,
                extra={"province_id": province_id, "governor_type": province.governor_type, "phase": "post_conquest"}
            )
            # ------------------------

            self.log_event(
                f"行省扩张：通过 {war.name} 的胜利，罗马征服了 {province.name}！当地民怨高涨（等级3）。"
            )

    def add_province(self, province: Province) -> None:
        """
        向行省注册表添加行省对象，并更新全局公地总数。

        Args:
            province: 要添加的行省对象。
        """
        self._provinces[province.province_id] = province
        self._update_global_public_land()

    def get_province(self, province_id: int) -> Optional[Province]:
        """
        根据ID获取行省对象，不存在则返回None。

        Args:
            province_id: 行省ID。

        Returns:
            行省对象或None。
        """
        return self._provinces.get(province_id)

    def get_all_provinces(self) -> List[Province]:
        """
        返回所有行省对象的列表（副本，防止外部修改）。

        Returns:
            行省列表。
        """
        return list(self._provinces.values())

    def _update_global_public_land(self) -> None:
        """
        私有方法：遍历行省注册表，更新全局公地总数。
        """
        self._public_land_total = sum(p.land_public for p in self._provinces.values())

    # ---------- 城市管理 ----------
    def add_city(self, city: City) -> None:
        """添加城市到注册表"""
        self._cities[city.city_id] = city
        # 确保城市ID不小于当前计数器
        if city.city_id >= self._city_id_counter:
            self._city_id_counter = city.city_id + 1

    def get_city(self, city_id: int) -> Optional[City]:
        """根据ID获取城市"""
        return self._cities.get(city_id)

    def get_all_cities(self) -> List[City]:
        """获取所有城市列表"""
        return list(self._cities.values())

    def create_city(self, name: str, infrastructure: Optional[Dict[str, int]] = None) -> City:
        """创建新城市并自动分配ID"""
        city_id = self._city_id_counter
        self._city_id_counter += 1
        city = City(city_id, name, infrastructure)
        self.add_city(city)
        return city

    # ---------- 合同管理 ----------
    def create_contract(self, contract_type: ContractType, province_id: int,
                        base_cost: int, current_turn: int) -> Contract:
        """
        创建并添加合同对象，自动分配唯一ID。

        Args:
            contract_type: 合同类型（ContractType.TAX_FARMING 或 ContractType.PUBLIC_WORKS）
            province_id: 关联的行省ID。
            base_cost: 基础成本/预算。
            current_turn: 当前回合数。

        Returns:
            新建的 Contract 对象。
        """
        contract = Contract(
            id=self._contract_id_counter,
            contract_type=contract_type,
            _province_id=province_id,
            _create_turn=current_turn,
            base_cost=base_cost
        )
        self._contracts_dict[self._contract_id_counter] = contract
        self._contract_id_counter += 1
        return contract

    def get_contract(self, contract_id: int) -> Optional[Contract]:
        return self._contracts_dict.get(contract_id)

    def get_all_contracts(self) -> List[Contract]:
        return list(self._contracts_dict.values())

    def get_province_contract(self, province_id: int, contract_type: ContractType) -> Optional[Contract]:
        province = self.get_province(province_id)
        if not province:
            return None

        # 使用正确的枚举成员进行比较
        if contract_type == ContractType.TAX_FARMING:
            contract_id = province.tax_contract_id
        elif contract_type == ContractType.PUBLIC_WORKS:
            contract_id = province.project_contract_id
        else:
            return None

        if contract_id is None:
            return None
        return self.get_contract(contract_id)

    def place_bid(self, contract_id: int, bidder_id: int, amount: int, **kwargs) -> bool:
        contract = self.get_contract(contract_id)
        if not contract or contract.status != ContractStatus.BUDGETED:
            return False
        bid = {"bidder_id": bidder_id, "amount": amount}
        bid.update(kwargs)
        contract._bids.append(bid)
        return True

    def sync_italy_public_land(self):
        italy = self.get_province(0)
        if italy:
            italy._land_public = self._national_public_land
            italy.recalc_total_land()  # 新增：更新总土地

    def resolve_auction(self, contract_id: int) -> bool:
        contract = self.get_contract(contract_id)
        if not contract or contract.status != ContractStatus.BUDGETED:
            return False
        if not contract._bids:
            # 无出价，流拍
            if contract.status == ContractStatus.BUDGETED:
                # 保持 BUDGETED，以便下次竞标
                contract.status = ContractStatus.BUDGETED
            else:
                contract.status = ContractStatus.EXPIRED
            return False

        # 根据合同类型选择中标者
        if contract.contract_type == ContractType.TAX_FARMING:
            max_bid = max(contract._bids, key=lambda b: b["amount"])
            winner = max_bid
        else:  # PUBLIC_WORKS
            min_bid = min(contract._bids, key=lambda b: b["amount"])
            winner = min_bid

        contract.mark_winner(winner["bidder_id"], self.turn.turn_number, 0)

        # 包税合同处理
        if contract.contract_type == ContractType.TAX_FARMING:
            # ===== 新增：存储合同价和利润率 =====
            contract._contract_price = winner["amount"]
            # 利润率 = 加价比例 r (来自出价时存储的 tax_rate 键)
            contract._profit_rate = winner.get("tax_rate", (winner["amount"] / contract.base_cost) - 1.0)

            # 先解除该行省所有活跃的包税合同（旧合同）
            active_tax = [c for c in self._contracts_dict.values()
                          if c.province_id == contract.province_id
                          and c.contract_type == ContractType.TAX_FARMING
                          and c.status == ContractStatus.ACTIVE
                          and c.id != contract.id]
            for ac in active_tax:
                ac.mark_complete(self.turn.turn_number)
                # 从原持有者中移除合同
                if ac.awarded_to:
                    old_figure = self.get_member(ac.awarded_to)
                    if old_figure:
                        old_figure.remove_contract(ac.id)
                province = self.get_province(contract.province_id)
                if province and province.tax_contract_id == ac.id:
                    province.unbind_tax_contract()

            contract._winning_bid = winner
            contract._tax_rate = winner["tax_rate"]
            province = self.get_province(contract.province_id)
            if province:
                # 以下计算仍保留，但新逻辑中收入阶段将使用 _contract_price 和 _profit_rate
                land_price = self.get_economic_rule("land_price_per_unit", 10)
                private_income_rate = self.get_economic_rule("private_land_income_rate", 0.05)
                base_tax_rate = self.get_economic_rule("province_tax_rate", 0.1)
                land_value = province.land_public * land_price
                base_income = int(land_value * private_income_rate)
                actual_tax_rate = base_tax_rate * (1 + winner["tax_rate"])
                actual_tax = int(base_income * actual_tax_rate)
                annual_net = actual_tax - winner["amount"]
                contract._annual_profit = annual_net
                contract.expected_profit = annual_net * contract.duration_years

            # 绑定骑士和行省
            figure = self.get_member(winner["bidder_id"])
            if figure:
                figure.add_contract(contract_id)
                contract.awarded_faction = figure.faction_id

            province = self.get_province(contract.province_id)
            if province:
                province.bind_tax_contract(contract_id)  # 此时应无冲突

        # 公共工程处理
        else:
            # 先解除该行省所有活跃的工程合同
            active_works = [c for c in self._contracts_dict.values()
                            if c.province_id == contract.province_id
                            and c.contract_type == ContractType.PUBLIC_WORKS
                            and c.status == ContractStatus.ACTIVE
                            and c.id != contract.id]
            for aw in active_works:
                aw.mark_complete(self.turn.turn_number)
                if aw.awarded_to:
                    old_figure = self.get_member(aw.awarded_to)
                    if old_figure:
                        old_figure.remove_contract(aw.id)
                province = self.get_province(contract.province_id)
                if province and province.project_contract_id == aw.id:
                    province.unbind_project_contract()

            contract._winning_bid = winner
            r = winner["r"]
            contract._original_budget = winner["original_budget"]
            contract._construction_years = winner["construction"]
            contract._warranty_years = winner["warranty"]
            contract._annual_income = winner["annual_income"]
            contract._annual_cost = winner["annual_cost"]
            contract.base_cost = winner["amount"]
            contract.remaining_years = winner["construction"]
            contract._warranty_remaining = winner["warranty"]

            province = self.get_province(contract.province_id)
            if province:
                land_price = self.get_economic_rule("land_price_per_unit", 10)
                infra_rate = self.get_economic_rule("infrastructure_cost_rate", 0.001)
                land_value = province.land_public * land_price
                infra_cost = int(land_value * infra_rate)
                actual_cost = int(infra_cost * (1 - r))
                contract.expected_profit = winner["amount"] - actual_cost

            figure = self.get_member(winner["bidder_id"])
            if figure:
                figure.add_contract(contract_id)
                contract.awarded_faction = figure.faction_id

            province = self.get_province(contract.province_id)
            if province:
                province.bind_project_contract(contract_id)

        # 如果是舰队建造合同，通知海军系统
        if hasattr(contract, '_is_fleet_construction') and contract._is_fleet_construction:
            if self._naval_system:
                self._naval_system.on_contract_awarded(contract, winner["bidder_id"])

        return True
