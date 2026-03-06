"""Tests for GUI-specific asyncio exception filtering."""

from __future__ import annotations

from unittest.mock import Mock

import rewired.gui.app as gui_app
from rewired.gui.charts import build_heatmap_update
from rewired.gui.components import _add_color_cell_slot


def test_benign_windows_asyncio_transport_error_is_detected(monkeypatch):
    monkeypatch.setattr(gui_app.sys, "platform", "win32")

    context = {
        "exception": ConnectionResetError("[WinError 10054] existing connection was forcibly closed"),
        "handle": "<Handle _ProactorBasePipeTransport._call_connection_lost()>",
    }

    assert gui_app._is_benign_windows_asyncio_transport_error(context) is True


def test_unrelated_connection_reset_is_not_suppressed(monkeypatch):
    monkeypatch.setattr(gui_app.sys, "platform", "win32")

    context = {
        "exception": ConnectionResetError("[WinError 10054] existing connection was forcibly closed"),
        "handle": "<Handle some_other_callback()>",
        "message": "socket recv failed",
    }

    assert gui_app._is_benign_windows_asyncio_transport_error(context) is False


def test_gui_exception_handler_suppresses_only_benign_windows_case(monkeypatch):
    monkeypatch.setattr(gui_app.sys, "platform", "win32")
    default_handler = Mock()
    loop = Mock()
    handler = gui_app._build_gui_exception_handler(default_handler)

    context = {
        "exception": ConnectionResetError("[WinError 10054] existing connection was forcibly closed"),
        "handle": "<Handle _ProactorBasePipeTransport._call_connection_lost()>",
    }

    handler(loop, context)

    default_handler.assert_not_called()
    loop.default_exception_handler.assert_not_called()


def test_gui_exception_handler_delegates_unrelated_errors(monkeypatch):
    monkeypatch.setattr(gui_app.sys, "platform", "win32")
    default_handler = Mock()
    loop = Mock()
    handler = gui_app._build_gui_exception_handler(default_handler)
    context = {"exception": RuntimeError("boom"), "message": "unexpected"}

    handler(loop, context)

    default_handler.assert_called_once_with(loop, context)


def test_build_heatmap_update_returns_javascript_object_literal():
    update = build_heatmap_update(None, {("1", "1"): []})

    assert isinstance(update, str)
    assert update.startswith("{")
    assert "series:[{data:" in update
    assert "tooltip:{formatter:(function(params){" in update
    assert "[object Object]" not in update


def test_add_color_cell_slot_uses_row_color_field_not_js_color_map():
    table = Mock()

    _add_color_cell_slot(table, "color")

    table.add_slot.assert_called_once()
    slot_name, slot_template = table.add_slot.call_args.args
    assert slot_name == "body-cell-color"
    assert "props.row.color_hex" in slot_template
    assert "props.value.toLowerCase()" not in slot_template
