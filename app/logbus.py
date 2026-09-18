import asyncio
import time
from collections import deque
from datetime import datetime

from . import config


class LogBus:
    def __init__(self):
        self._buffer = deque(maxlen=config.LOG_BUFFER_SIZE)
        self._subscribers: set[asyncio.Queue] = set()

    def publish(self, level: str, message: str, **extra):
        entry = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message,
            **extra,
        }
        self._buffer.append(entry)
        stale = []
        for q in self._subscribers:
            try:
                q.put_nowait(entry)
            except asyncio.QueueFull:
                stale.append(q)
        for q in stale:
            self._subscribers.discard(q)

    def snapshot(self):
        return list(self._buffer)

    def subscribe(self):
        q = asyncio.Queue(maxsize=1000)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q):
        self._subscribers.discard(q)


logbus = LogBus()


def log(level: str, message: str, **extra):
    logbus.publish(level, message, **extra)
    print(f"{level.upper():5} {message}", flush=True)