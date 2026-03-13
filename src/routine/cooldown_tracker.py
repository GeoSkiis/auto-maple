"""
跟踪每个技能的上次使用时间并返回哪些技能已冷却完毕。
用于在每个路径点进行"随机选择可用技能"的轮换。
"""
import time
import random
from typing import Optional


class CooldownTracker:
    """
    每个技能由其键（str）标识。cooldowns 是一个字典，键 -> 冷却时间秒（0 = 无冷却）。
    """

    def __init__(self, cooldowns: dict[str, float]):
        self.cooldowns = dict(cooldowns)
        self.last_used: dict[str, float] = {k: 0.0 for k in self.cooldowns}

    def record_used(self, key: str) -> None:
        self.last_used[key] = time.time()

    def get_available(self) -> list[str]:
        """返回已冷却完毕的技能键列表。"""
        now = time.time()
        out = []
        for key, cd in self.cooldowns.items():
            if cd <= 0 or (now - self.last_used[key]) >= cd:
                out.append(key)
        return out

    def pick_random_available(self) -> Optional[str]:
        """返回一个随机的已冷却完毕的技能键，如果没有可用技能则返回 None。"""
        available = self.get_available()
        if not available:
            return None
        return random.choice(available)