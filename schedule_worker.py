"""
Background worker that applies device ON/OFF schedules to relays.
Runs every 60 seconds: if current time (HH:MM) matches a relay's
default_on_time or default_off_time, updates relay state so the ESP32
picks it up on its next poll.
"""
import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger("schedule_worker")

# Use server local time (set TZ env for timezone, e.g. Asia/Kolkata)
def _current_time_str() -> str:
    return datetime.now().strftime("%H:%M")


def run_schedule_check(relay_states: dict, devices_col) -> None:
    """Check each relay's schedule and set on/off if time matches."""
    now = _current_time_str()
    for relay_num in (1, 2, 3):
        key = f"relay{relay_num}"
        try:
            doc = devices_col.find_one({"relay": relay_num}) or {}
            on_time = doc.get("default_on_time")
            off_time = doc.get("default_off_time")
            if on_time and now == on_time:
                relay_states[key] = True
                logger.info("Schedule: relay %d ON at %s", relay_num, now)
            if off_time and now == off_time:
                relay_states[key] = False
                logger.info("Schedule: relay %d OFF at %s", relay_num, now)
        except Exception as e:
            logger.warning("Schedule check failed for relay %s: %s", relay_num, e)


def start_schedule_loop(relay_states: dict, devices_col, interval_seconds: int = 60) -> None:
    """Start a daemon thread that runs the schedule check every interval_seconds."""

    def _loop():
        while True:
            try:
                run_schedule_check(relay_states, devices_col)
            except Exception as e:
                logger.warning("Schedule loop error: %s", e)
            time.sleep(interval_seconds)

    t = threading.Thread(target=_loop, daemon=True, name="schedule_worker")
    t.start()
    logger.info("Schedule worker started (interval=%ds)", interval_seconds)
