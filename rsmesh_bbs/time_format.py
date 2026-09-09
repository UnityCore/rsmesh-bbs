import time
from datetime import datetime


def format_relative_time(timestamp):
    if timestamp is None:
        return "UNK"

    seconds = max(0, int(time.time()) - int(timestamp))
    if seconds < 60:
        return "just now" if seconds < 10 else f"{seconds} sec"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr" if hours == 1 else f"{hours} hrs"
    days = hours // 24
    return f"{days} day" if days == 1 else f"{days} days"


def format_timestamp(timestamp):
    if timestamp is None:
        return "UNK"
    return datetime.fromtimestamp(int(timestamp)).strftime('%Y/%m/%d %H:%M:%S')
