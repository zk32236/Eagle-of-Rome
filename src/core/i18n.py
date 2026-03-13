# src/core/i18n.py
import json
import os
from typing import Optional

class I18n:
    _instance = None
    _strings = {}
    _current_language = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, language: str = "zh-CN", force: bool = False):
        if not force and self._current_language == language and self._strings:
            return
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        file_path = os.path.join(base_path, "data", "i18n", f"{language}.json")
        print(f"[DEBUG] Loading i18n from: {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                self._strings = json.load(f)
                self._current_language = language
                print(f"[DEBUG] Loaded {len(self._strings)} keys")
        except FileNotFoundError:
            if language != "zh-CN":
                self.load("zh-CN")
            else:
                raise RuntimeError(f"Missing i18n file: {file_path}")

    def get(self, key: str, default: Optional[str] = None, **kwargs) -> str:
        if not self._strings:
            self.load("zh-CN")
        text = self._strings.get(key, default if default is not None else key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError:
                return text
        return text

i18n = I18n()
# 立即加载默认语言
i18n.load("zh-CN")