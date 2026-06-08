import pytest

from desktop_control.errors import DesktopControlError
from desktop_control.uia import _normalize_control_type


def test_normalize_control_type_accepts_common_names():
    assert _normalize_control_type("button") == 50000
    assert _normalize_control_type("menu item") == 50011
    assert _normalize_control_type("Edit") == 50004


def test_normalize_control_type_accepts_numeric_string():
    assert _normalize_control_type("50000") == 50000


def test_normalize_control_type_returns_none_for_unknown_name():
    assert _normalize_control_type("not-a-real-control") is None

