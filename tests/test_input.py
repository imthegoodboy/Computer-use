import pytest

from desktop_control.errors import DesktopControlError
from desktop_control.input import parse_chord


def test_parse_chord_splits_modifier_sequence():
    assert parse_chord("ctrl+shift+a") == ["ctrl", "shift", "a"]


def test_parse_chord_rejects_empty_value():
    with pytest.raises(DesktopControlError):
        parse_chord(" + ")

