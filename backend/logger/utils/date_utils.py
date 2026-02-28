from datetime import datetime


def parse_date(date_str: str) -> str:
    """Parse M/D/YY or M/D/YYYY → ISO 8601 YYYY-MM-DD."""
    date_str = date_str.strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {date_str}")


DAY_MAP = {
    "mon": "Mon", "monday": "Mon",
    "tue": "Tue", "tues": "Tue", "tuesday": "Tue",
    "wed": "Wed", "wednesday": "Wed",
    "thur": "Thu", "thurs": "Thu", "thu": "Thu", "thursday": "Thu",
    "fri": "Fri", "friday": "Fri",
    "sat": "Sat", "saturday": "Sat",
    "sun": "Sun", "sunday": "Sun",
}


def normalize_day(day_str: str | None) -> str | None:
    """Normalize day-of-week to 3-letter Title case."""
    if not day_str:
        return None
    return DAY_MAP.get(day_str.strip().lower(), day_str.strip().title()[:3])
