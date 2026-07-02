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
        "phase.status.actionable": "可操作真实切片",
        "phase.status.ready": "已接入 / 等待正确阶段或玩家",
        "phase.status.placeholder": "后续任务承接 / 暂不可操作",
        "phase.disabled.placeholder": "{handoff_task} 承接，本轮不会改变游戏状态",
    }
}


def gui_text(key: str, locale: str = DEFAULT_LOCALE, **kwargs: Any) -> str:
    template = _TEXT.get(locale, {}).get(key) or _TEXT[DEFAULT_LOCALE].get(key) or key
    try:
        return template.format(**kwargs)
    except KeyError:
        return template
