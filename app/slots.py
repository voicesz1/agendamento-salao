from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import TIMEZONE
from app.models import Appointment, BusinessHours, ClosedDate, Service
from app.settings_store import get_setting


def now_local() -> datetime:
    return datetime.now(TIMEZONE)


def combine(day: date, t) -> datetime:
    return datetime.combine(day, t, tzinfo=TIMEZONE)


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def available_slots(db: Session, service: Service, day: date) -> list[str]:
    hours = db.query(BusinessHours).filter(BusinessHours.weekday == day.weekday()).first()
    if not hours or not hours.is_open:
        return []

    closed = db.query(ClosedDate).filter(ClosedDate.day == day).first()
    if closed:
        return []

    try:
        interval = int(get_setting(db, "slot_interval_minutes", "30"))
    except ValueError:
        interval = 30
    if interval not in {15, 30, 60}:
        interval = 30
    if hours.close_time <= hours.open_time:
        return []
    duration = timedelta(minutes=service.duration_minutes)
    open_dt = combine(day, hours.open_time)
    close_dt = combine(day, hours.close_time)
    current = now_local()

    busy = (
        db.query(Appointment)
        .filter(Appointment.day == day, Appointment.status == "confirmado")
        .all()
    )
    busy_ranges = [(combine(a.day, a.start_time), combine(a.day, a.end_time)) for a in busy]

    break_range = None
    if hours.break_start and hours.break_end:
        if hours.break_end <= hours.break_start:
            return []
        break_range = (combine(day, hours.break_start), combine(day, hours.break_end))

    slots: list[str] = []
    cursor = open_dt
    step = timedelta(minutes=interval)
    while cursor + duration <= close_dt:
        end = cursor + duration
        if cursor > current:
            blocked = any(overlaps(cursor, end, b0, b1) for b0, b1 in busy_ranges)
            on_break = break_range and overlaps(cursor, end, break_range[0], break_range[1])
            if not blocked and not on_break:
                slots.append(cursor.strftime("%H:%M"))
        cursor += step
    return slots


def slot_is_free(db: Session, service: Service, day: date, start_hhmm: str) -> bool:
    return start_hhmm in available_slots(db, service, day)
