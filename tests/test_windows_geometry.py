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


def test_resolve_client_point_scales_for_dpi_unaware_target(monkeypatch):
    from desktop_control import windows

    monkeypatch.setattr(windows.win32process, "GetWindowThreadProcessId", lambda hwnd: (1, 1234))
    monkeypatch.setattr(windows, "_process_dpi_awareness", lambda pid: windows.PROCESS_DPI_UNAWARE)
    monkeypatch.setattr(windows, "_monitor_dpi_for_window", lambda hwnd: 120)
    monkeypatch.setattr(windows.win32gui, "ClientToScreen", lambda hwnd, point: (1000 + point[0], 2000 + point[1]))

    assert windows.resolve_point(99, 160, 150, "client") == (1200, 2188)

