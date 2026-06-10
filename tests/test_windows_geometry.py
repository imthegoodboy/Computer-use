from desktop_control.models import Rect


def test_rect_dimensions_are_non_negative():
    rect = Rect(10, 20, 5, 15)
    assert rect.width == 0
    assert rect.height == 0


def test_rect_contains_screen_point():
    rect = Rect(10, 20, 30, 40)
    assert rect.contains_screen_point(10, 20)
    assert rect.contains_screen_point(29, 39)
    assert not rect.contains_screen_point(30, 40)

