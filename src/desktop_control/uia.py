from __future__ import annotations

import time
from typing import Any

import win32gui

from .errors import DesktopControlError
from .input import click_at, send_text

TREE_SCOPE_CHILDREN = 0x2
UIA_INVOKE_PATTERN_ID = 10000
UIA_VALUE_PATTERN_ID = 10002

CONTROL_TYPES = {
    "button": 50000,
    "calendar": 50001,
    "checkbox": 50002,
    "combobox": 50003,
    "edit": 50004,
    "hyperlink": 50005,
    "image": 50006,
    "listitem": 50007,
    "list": 50008,
    "menu": 50009,
    "menubar": 50010,
    "menuitem": 50011,
    "progressbar": 50012,
    "radiobutton": 50013,
    "scrollbar": 50014,
    "slider": 50015,
    "spinner": 50016,
    "statusbar": 50017,
    "tab": 50018,
    "tabitem": 50019,
    "text": 50020,
    "toolbar": 50021,
    "tooltip": 50022,
    "tree": 50023,
    "treeitem": 50024,
    "custom": 50025,
    "group": 50026,
    "thumb": 50027,
    "datagrid": 50028,
    "dataitem": 50029,
    "document": 50030,
    "splitbutton": 50031,
    "window": 50032,
    "pane": 50033,
    "header": 50034,
    "headeritem": 50035,
    "table": 50036,
    "titlebar": 50037,
    "separator": 50038,
}


def _safe_get(obj: object, attr: str, default: Any = None) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def _rect_to_dict(rect: object) -> dict[str, int] | None:
    try:
        left = int(getattr(rect, "left"))
        top = int(getattr(rect, "top"))
        right = int(getattr(rect, "right"))
        bottom = int(getattr(rect, "bottom"))
    except Exception:
        return None
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": max(0, right - left),
        "height": max(0, bottom - top),
    }


def _element_to_dict(element: object) -> dict[str, Any]:
    return {
        "name": _safe_get(element, "CurrentName", "") or "",
        "automation_id": _safe_get(element, "CurrentAutomationId", "") or "",
        "class_name": _safe_get(element, "CurrentClassName", "") or "",
        "control_type": _safe_get(element, "CurrentControlType", None),
        "enabled": _safe_get(element, "CurrentIsEnabled", None),
        "keyboard_focusable": _safe_get(element, "CurrentIsKeyboardFocusable", None),
        "has_keyboard_focus": _safe_get(element, "CurrentHasKeyboardFocus", None),
        "rect": _rect_to_dict(_safe_get(element, "CurrentBoundingRectangle")),
    }


def _create_automation_root(hwnd: int) -> tuple[object, object]:
    try:
        import comtypes
        from comtypes.client import CreateObject, GetModule

        comtypes.CoInitialize()
        try:
            GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient

            automation = CreateObject(
                "{ff48dba4-60ef-4201-aa87-54103eef594e}",
                interface=UIAutomationClient.IUIAutomation,
            )
        except Exception:
            automation = CreateObject("UIAutomationClient.CUIAutomation")
        root = automation.ElementFromHandle(hwnd)
        return automation, root
    except Exception as exc:
        raise DesktopControlError("uia_unavailable", "Windows UI Automation is unavailable", {"exception": repr(exc)}) from exc


def _uia_client_module() -> object:
    from comtypes.client import GetModule

    GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient

    return UIAutomationClient


def get_uia_tree(hwnd: int, max_depth: int = 3, max_nodes: int = 200) -> dict[str, Any]:
    try:
        automation, root = _create_automation_root(hwnd)
        true_condition = automation.CreateTrueCondition()
        nodes_seen = 0

        def walk(element: object, depth: int) -> dict[str, Any]:
            nonlocal nodes_seen
            nodes_seen += 1
            node = _element_to_dict(element)
            if depth >= max_depth or nodes_seen >= max_nodes:
                return node

            children = []
            try:
                collection = element.FindAll(TREE_SCOPE_CHILDREN, true_condition)
                for index in range(int(collection.Length)):
                    if nodes_seen >= max_nodes:
                        break
                    children.append(walk(collection.GetElement(index), depth + 1))
            except Exception:
                pass
            if children:
                node["children"] = children
            return node

        return {
            "source": "uia",
            "truncated": nodes_seen >= max_nodes,
            "root": walk(root, 0),
        }
    except Exception as exc:
        return {
            "source": "win32-child-windows",
            "uia_error": repr(exc),
            "nodes": get_child_windows(hwnd, max_nodes=max_nodes),
        }


def _normalize_control_type(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    normalized = value.replace("_", "").replace("-", "").replace(" ", "").lower()
    if normalized.isdigit():
        return int(normalized)
    return CONTROL_TYPES.get(normalized)


def _matches_selector(element: object, selector: dict[str, Any]) -> bool:
    name = selector.get("name")
    if name is not None and (_safe_get(element, "CurrentName", "") or "") != str(name):
        return False

    name_contains = selector.get("name_contains")
    if name_contains is not None and str(name_contains).lower() not in (_safe_get(element, "CurrentName", "") or "").lower():
        return False

    automation_id = selector.get("automation_id")
    if automation_id is not None and (_safe_get(element, "CurrentAutomationId", "") or "") != str(automation_id):
        return False

    class_name = selector.get("class_name")
    if class_name is not None and (_safe_get(element, "CurrentClassName", "") or "") != str(class_name):
        return False

    control_type = _normalize_control_type(selector.get("control_type"))
    if control_type is not None and int(_safe_get(element, "CurrentControlType", 0) or 0) != control_type:
        return False

    return True


def _iter_elements(hwnd: int, max_depth: int, max_nodes: int) -> list[object]:
    automation, root = _create_automation_root(hwnd)
    true_condition = automation.CreateTrueCondition()
    elements: list[object] = []

    def walk(element: object, depth: int) -> None:
        if len(elements) >= max_nodes:
            return
        elements.append(element)
        if depth >= max_depth:
            return
        try:
            collection = element.FindAll(TREE_SCOPE_CHILDREN, true_condition)
            for index in range(int(collection.Length)):
                if len(elements) >= max_nodes:
                    break
                walk(collection.GetElement(index), depth + 1)
        except Exception:
            return

    walk(root, 0)
    return elements


def find_uia_elements(
    hwnd: int,
    selector: dict[str, Any],
    max_depth: int = 6,
    max_nodes: int = 500,
) -> list[dict[str, Any]]:
    matches = [
        _element_to_dict(element)
        for element in _iter_elements(hwnd, max_depth=max_depth, max_nodes=max_nodes)
        if _matches_selector(element, selector)
    ]
    return matches


def _find_one_element(
    hwnd: int,
    selector: dict[str, Any],
    max_depth: int = 6,
    max_nodes: int = 500,
) -> object:
    matches = [
        element
        for element in _iter_elements(hwnd, max_depth=max_depth, max_nodes=max_nodes)
        if _matches_selector(element, selector)
    ]
    if not matches:
        raise DesktopControlError("element_not_found", "No UIA element matched the selector", {"selector": selector})
    if len(matches) > 1 and not selector.get("allow_multiple", False):
        raise DesktopControlError(
            "ambiguous_element",
            "Multiple UIA elements matched the selector",
            {"selector": selector, "count": len(matches), "matches": [_element_to_dict(item) for item in matches[:10]]},
        )
    index = int(selector.get("index", 0) or 0)
    if index < 0 or index >= len(matches):
        raise DesktopControlError(
            "element_index_out_of_range",
            "UIA element index is outside the matched element list",
            {"selector": selector, "count": len(matches), "index": index},
        )
    return matches[index]


def _element_center(element: object) -> tuple[int, int]:
    rect = _rect_to_dict(_safe_get(element, "CurrentBoundingRectangle"))
    if not rect or rect["width"] <= 0 or rect["height"] <= 0:
        raise DesktopControlError("element_has_no_bounds", "UIA element does not expose a usable rectangle", {"element": _element_to_dict(element)})
    return rect["left"] + rect["width"] // 2, rect["top"] + rect["height"] // 2


def click_uia_element(
    hwnd: int,
    selector: dict[str, Any],
    button: str = "left",
    count: int = 1,
    max_depth: int = 6,
    max_nodes: int = 500,
) -> dict[str, Any]:
    element = _find_one_element(hwnd, selector, max_depth=max_depth, max_nodes=max_nodes)
    x, y = _element_center(element)
    click_at(x, y, button=button, count=count)
    return {
        "ok": True,
        "action": "click_element",
        "element": _element_to_dict(element),
        "screen_point": {"x": x, "y": y},
        "button": button,
        "count": count,
    }


def invoke_uia_element(
    hwnd: int,
    selector: dict[str, Any],
    max_depth: int = 6,
    max_nodes: int = 500,
) -> dict[str, Any]:
    element = _find_one_element(hwnd, selector, max_depth=max_depth, max_nodes=max_nodes)
    try:
        pattern = element.GetCurrentPattern(UIA_INVOKE_PATTERN_ID)
        uia_client = _uia_client_module()
        pattern.QueryInterface(uia_client.IUIAutomationInvokePattern).Invoke()
        method = "invoke_pattern"
    except Exception:
        x, y = _element_center(element)
        click_at(x, y)
        method = "center_click_fallback"
    return {
        "ok": True,
        "action": "invoke_element",
        "element": _element_to_dict(element),
        "method": method,
    }


def set_uia_element_value(
    hwnd: int,
    selector: dict[str, Any],
    value: str,
    max_depth: int = 6,
    max_nodes: int = 500,
    fallback_text_method: str = "clipboard",
) -> dict[str, Any]:
    element = _find_one_element(hwnd, selector, max_depth=max_depth, max_nodes=max_nodes)
    try:
        pattern = element.GetCurrentPattern(UIA_VALUE_PATTERN_ID)
        uia_client = _uia_client_module()
        pattern.QueryInterface(uia_client.IUIAutomationValuePattern).SetValue(value)
        method = "value_pattern"
    except Exception:
        x, y = _element_center(element)
        click_at(x, y)
        time.sleep(0.05)
        send_text(value, method=fallback_text_method)
        method = f"{fallback_text_method}_fallback"
    return {
        "ok": True,
        "action": "set_element_value",
        "element": _element_to_dict(element),
        "characters": len(value),
        "method": method,
    }


def get_child_windows(hwnd: int, max_nodes: int = 200) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def collect(child_hwnd: int, _: object) -> bool:
        if len(nodes) >= max_nodes:
            return False
        try:
            left, top, right, bottom = win32gui.GetWindowRect(child_hwnd)
            nodes.append(
                {
                    "hwnd": int(child_hwnd),
                    "title": win32gui.GetWindowText(child_hwnd) or "",
                    "class_name": win32gui.GetClassName(child_hwnd) or "",
                    "visible": bool(win32gui.IsWindowVisible(child_hwnd)),
                    "rect": {
                        "left": int(left),
                        "top": int(top),
                        "right": int(right),
                        "bottom": int(bottom),
                        "width": max(0, int(right - left)),
                        "height": max(0, int(bottom - top)),
                    },
                }
            )
        except Exception:
            pass
        return True

    win32gui.EnumChildWindows(hwnd, collect, None)
    return nodes

