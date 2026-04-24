"""Circular history buffer for sparkline rendering."""

from collections import deque
from typing import Sequence


SPARK_CHARS = " ▁▂▃▄▅▆▇█"


class History:
    def __init__(self, maxlen: int = 60):
        self._cpu: deque = deque(maxlen=maxlen)
        self._mem: deque = deque(maxlen=maxlen)
        self._disk: deque = deque(maxlen=maxlen)

    def push(self, cpu: float, mem: float, disk: float) -> None:
        self._cpu.append(cpu)
        self._mem.append(mem)
        self._disk.append(disk)

    @staticmethod
    def _sparkline(values: Sequence[float], width: int = 30) -> str:
        if not values:
            return " " * width
        data = list(values)[-width:]
        lo, hi = 0.0, 100.0
        span = hi - lo or 1
        chars = []
        for v in data:
            idx = int((v - lo) / span * (len(SPARK_CHARS) - 1))
            idx = max(0, min(len(SPARK_CHARS) - 1, idx))
            chars.append(SPARK_CHARS[idx])
        # Pad left if shorter than width
        return " " * (width - len(chars)) + "".join(chars)

    def cpu_spark(self, width: int = 30) -> str:
        return self._sparkline(self._cpu, width)

    def mem_spark(self, width: int = 30) -> str:
        return self._sparkline(self._mem, width)

    def disk_spark(self, width: int = 30) -> str:
        return self._sparkline(self._disk, width)

    @property
    def sample_count(self) -> int:
        return len(self._cpu)