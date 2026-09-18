from datetime import datetime
from zoneinfo import ZoneInfo


def local_now(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def to_local(epoch_ms: int, tz_name: str) -> datetime:
    return datetime.fromtimestamp(epoch_ms / 1000, tz=ZoneInfo(tz_name))


def is_inside_window(ts: datetime, start: str, end: str) -> bool:
    hm = ts.strftime("%H:%M")
    return start <= hm <= end


def window_for(ts: datetime, class_node: dict, active_days: list[int]) -> tuple[str | None, str | None]:
    if ts.weekday() not in active_days:
        return None, "Off day"
    windows = class_node.get("windows") or {}
    for name in ("am", "pm"):
        w = windows.get(name)
        if not w:
            continue
        try:
            if is_inside_window(ts, w["start"], w["end"]):
                return name, None
        except (KeyError, TypeError):
            continue
    return None, "Outside attendance window"