"""
Lightweight GUI text catalog for shell-level copy.

GUI-P0-02A keeps zh-CN as the only resolved language, but routes new shell
copy through stable keys so a later GUI-I18N task can add en-US without
rewiring Store/QML call sites.
"""
from typing import Any, Dict


DEFAULT_LOCALE = "zh-CN"

_TEXT: Dict[str, Dict[str, str]] = {
    "zh-CN": {
        "feedback.snapshot.refreshed": "状态已刷新",
        "feedback.phase.unknown": "未知阶段: {phase_id}",
        "feedback.phase.selected": "已切换到{name}阶段。",
        "feedback.phase.placeholder": "{name}由{handoff_task}承接，当前暂不可操作。",
        "feedback.query.not_initialized": "GUI 会话尚未初始化",
        "feedback.query.selected": "已打开{title}查询。",
        "phase.status.actionable": "可操作真实切片",
        "phase.status.ready": "已接入 / 等待正确阶段或玩家",
        "phase.status.readonly": "已接入只读 / 后续子任务接入操作",
        "phase.status.placeholder": "后续任务承接 / 暂不可操作",
        "phase.disabled.placeholder": "{handoff_task} 承接，本轮不会改变游戏状态",
        "phase.disabled.readonly": "已接入只读，政治操作由后续子任务承接",
        "query.game_status.title": "游戏状态",
        "query.faction_info.title": "派系信息",
        "query.war_list.title": "战争列表",
        "query.legion_status.title": "军团状态",
        "query.figure_search.title": "人物查询",
        "query.faction_treasury.title": "派系金库",
        "query.public_land.title": "公地信息",
        "query.private_land.title": "私地信息",
        "query.contract_status.title": "合同状态",
        "query.province_info.title": "行省信息",
        "query.fleet_status.title": "舰队状态",
        "query.help.title": "帮助",
        "query.game_status.empty": "游戏状态暂无可显示摘要",
        "query.faction_info.message": "仅显示当前 viewer 派系的安全摘要。",
        "query.war_list.message": "战争列表来自已接入的元老院只读摘要。",
        "query.game_status.message": "共和国公开状态摘要。",
        "query.legion_status.message": "军团状态为只读摘要，不征召、不解散、不分配。",
        "query.error": "查询失败",
        "query.placeholder.message": "{handoff_task} 后续任务承接；当前仅显示入口占位。",
        "query.empty": "暂无记录",
        "query.item.year": "年份",
        "query.item.turn": "回合",
        "query.item.current_phase": "当前阶段",
        "query.item.current_player": "当前玩家",
        "query.item.treasury": "金库",
        "query.item.living_members": "在世人物",
        "query.item.factions": "派系数",
        "query.item.faction": "派系",
        "query.item.public_faction": "公开派系",
        "query.item.members": "人物数",
        "query.item.influence": "影响力",
        "query.item.war": "战争",
        "query.item.legion": "军团",
        "query.item.active_war": "进行中",
        "query.item.war_threat": "威胁",
        "query.item.status": "状态",
        "query.item.handoff": "承接任务",
    }
}


def gui_text(key: str, locale: str = DEFAULT_LOCALE, **kwargs: Any) -> str:
    template = _TEXT.get(locale, {}).get(key) or _TEXT[DEFAULT_LOCALE].get(key) or key
    try:
        return template.format(**kwargs)
    except KeyError:
        return template
