import random
from pathlib import Path

FORTUNES_FILE = "fortunes.txt"


def load_fortunes(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def decorate_fortune(fortune):
    return f"?? {fortune} ??"


def pick_fortune(fortunes):
    if not fortunes:
        return None
    return random.choice(fortunes)
