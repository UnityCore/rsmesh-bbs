import random
import sys
from pathlib import Path

import pytest

MODULES_DIR = Path(__file__).resolve().parent.parent / "modules"
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

from fortune import fortunes


class TestFortunes:
    def test_load_fortunes_skips_blank_lines(self, tmp_path):
        path = tmp_path / "fortunes.txt"
        path.write_text("first\n\n second \n", encoding="utf-8")
        assert fortunes.load_fortunes(path) == ["first", "second"]

    def test_load_fortunes_missing_file(self, tmp_path):
        assert fortunes.load_fortunes(tmp_path / "missing.txt") == []

    def test_decorate_fortune(self):
        assert fortunes.decorate_fortune("Hello") == "?? Hello ??"

    def test_pick_fortune_from_list(self, monkeypatch):
        lines = ["one", "two", "three"]
        monkeypatch.setattr(random, "choice", lambda items: "two")
        assert fortunes.pick_fortune(lines) == "two"

    def test_pick_fortune_empty(self):
        assert fortunes.pick_fortune([]) is None

    def test_bundled_fortunes_file_has_entries(self):
        path = MODULES_DIR / "fortune" / "fortunes.txt"
        loaded = fortunes.load_fortunes(path)
        assert len(loaded) >= 90
