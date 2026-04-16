import logging
from datetime import datetime, timedelta
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import Schedule

logger = logging.getLogger(__name__)

DAY_MAP = {
    "monday": "mon", "tuesday": "tue", "wednesday": "wed",
    "thursday": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun",
}


def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse 'HH:MM' into (hour, minute)."""
    parts = time_str.strip().split(":")
    return int(parts[0]), int(parts[1])


def build_cron_trigger(schedule: Schedule) -> CronTrigger:
    """Convert a Schedule config into an APScheduler CronTrigger."""
    hour, minute = _parse_time(schedule.time)

    freq = schedule.frequency.strip().lower()

    if freq == "daily":
        return CronTrigger(hour=hour, minute=minute)

    if freq == "weekdays":
        day_abbrevs = []
        for d in schedule.days:
            abbrev = DAY_MAP.get(d.strip().lower())
            if abbrev:
                day_abbrevs.append(abbrev)
        if not day_abbrevs:
            day_abbrevs = ["mon", "wed", "fri"]
        day_of_week = ",".join(day_abbrevs)
        return CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)

    # Treat as raw cron expression: "minute hour day month day_of_week"
    parts = freq.split()
    if len(parts) == 5:
        return CronTrigger.from_crontab(freq)

    logger.warning("Unrecognized frequency '%s', defaulting to daily at %02d:%02d", freq, hour, minute)
    return CronTrigger(hour=hour, minute=minute)


def compute_publish_dates(
    num_shorts: int,
    schedule: Schedule,
    start_from: Optional[datetime] = None,
) -> list[datetime]:
    """
    Pre-compute publish datetimes for a batch of shorts based on the schedule.

    This powers the "content machine" feature: e.g. 30 shorts get 30 scheduled dates.
    """
    if start_from is None:
        start_from = datetime.utcnow()

    hour, minute = _parse_time(schedule.time)
    freq = schedule.frequency.strip().lower()

    dates: list[datetime] = []
    current = start_from.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if current <= start_from:
        current += timedelta(days=1)

    if freq == "daily":
        for _ in range(num_shorts):
            dates.append(current)
            current += timedelta(days=1)

    elif freq == "weekdays":
        allowed = set()
        for d in schedule.days:
            abbrev = DAY_MAP.get(d.strip().lower())
            if abbrev:
                weekday_num = list(DAY_MAP.values()).index(abbrev)
                allowed.add(weekday_num)
        if not allowed:
            allowed = {0, 2, 4}  # Mon, Wed, Fri

        while len(dates) < num_shorts:
            if current.weekday() in allowed:
                dates.append(current)
            current += timedelta(days=1)

    else:
        # Fallback: one per day
        for _ in range(num_shorts):
            dates.append(current)
            current += timedelta(days=1)

    return dates


class PostingScheduler:
    """Manages the APScheduler instance for periodic upload triggers."""

    def __init__(self):
        self._scheduler = BackgroundScheduler()
        self._job_id = "upload_trigger"

    def start(self, schedule: Schedule, callback: Callable[[], None]) -> None:
        """Start the scheduler with the configured posting schedule."""
        trigger = build_cron_trigger(schedule)

        self._scheduler.add_job(
            callback,
            trigger=trigger,
            id=self._job_id,
            replace_existing=True,
            misfire_grace_time=3600,
        )

        self._scheduler.start()
        logger.info("Posting scheduler started — next run: %s", self._scheduler.get_job(self._job_id).next_run_time)

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Posting scheduler stopped")

    @property
    def next_run_time(self) -> Optional[datetime]:
        job = self._scheduler.get_job(self._job_id)
        return job.next_run_time if job else None
