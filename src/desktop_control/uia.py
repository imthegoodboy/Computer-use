from __future__ import annotations

from typing import Any

import win32gui

TREE_SCOPE_CHILDREN = 0x2


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


def get_uia_tree(hwnd: int, max_depth: int = 3, max_nodes: int = 200) -> dict[str, Any]:
    try:
        import comtypes
        from comtypes.client import CreateObject

        comtypes.CoInitialize()
        automation = CreateObject("UIAutomationClient.CUIAutomation")
        root = automation.ElementFromHandle(hwnd)
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

