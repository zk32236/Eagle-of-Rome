import random
from typing import List


class DiceBag:
    """骰子和随机数工具类"""

    @staticmethod
    def roll_2d6() -> int:
        """投掷2个六面骰，返回总和"""
        return random.randint(1, 6) + random.randint(1, 6)

    @staticmethod
    def roll_1d6() -> int:
        """投掷1个六面骰"""
        return random.randint(1, 6)

    @staticmethod
    def draw_random_from_list(item_list: List) -> any:
        """从列表中随机抽取一项并移除（类似从袋中抽取）"""
        if not item_list:
            return None
        item = random.choice(item_list)
        item_list.remove(item)
        return item

    @staticmethod
    def draw_random_keep_list(item_list: List) -> any:
        """从列表中随机选择一项，不移除"""
        if not item_list:
            return None
        return random.choice(item_list)