"""
Tracks last-used time per skill and returns which skills are off cooldown.
Used for "pick a random available skill" rotation at each waypoint.
"""
import time
import random
from typing import Optional


class CooldownTracker:
    """
    Each skill is identified by its key (str). cooldowns is a dict key -> cooldown_sec (0 = no cd).
    """

    def __init__(self, cooldowns: dict[str, float]):
        self.cooldowns = dict(cooldowns)
        self.last_used: dict[str, float] = {k: 0.0 for k in self.cooldowns}

    def record_used(self, key: str) -> None:
        self.last_used[key] = time.time()

    def get_available(self) -> list[str]:
        """Return list of skill keys that are off cooldown."""
        now = time.time()
        out = []
        for key, cd in self.cooldowns.items():
            if cd <= 0 or (now - self.last_used[key]) >= cd:
                out.append(key)
        return out

    def pick_random_available(self) -> Optional[str]:
        """Return one random skill key that is off cooldown, or None if none available."""
        available = self.get_available()
        if not available:
            return None
        return random.choice(available)
