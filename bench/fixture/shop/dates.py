DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def days_in_month(year, month):
    if month < 1 or month > 12:
        raise ValueError("month must be 1-12")
    if month == 2 and is_leap(year):
        return 29
    return DAYS[month - 1]


def day_of_year(year, month, day):
    return sum(days_in_month(year, m) for m in range(1, month)) + day


def quarter(month):
    return (month - 1) // 3 + 1


def format_duration(seconds):
    hours = seconds // 3600
    minutes = seconds % 3600 // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    if minutes > 0:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"
