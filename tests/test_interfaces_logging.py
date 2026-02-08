"""Tests for interface import/logging behavior."""

import importlib
import logging
import sys


def test_importing_interfaces_does_not_configure_global_logging(monkeypatch):
    calls = {"count": 0}

    def fake_basic_config(*args, **kwargs):
        calls["count"] += 1

    monkeypatch.setattr(logging, "basicConfig", fake_basic_config)

    for module_name in (
        "flavia.interfaces",
        "flavia.interfaces.telegram_interface",
        "flavia.interfaces.cli_interface",
    ):
        sys.modules.pop(module_name, None)

    importlib.import_module("flavia.interfaces")
    assert calls["count"] == 0
