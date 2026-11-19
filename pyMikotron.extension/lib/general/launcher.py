# -*- coding: utf-8 -*-
"""Runs a tool script from the lib folder by name.

Every pushbutton calls run("<ToolName>"), where lib/<ToolName>.py defines main().
The tool module is reloaded on each click, so edits to lib/<ToolName>.py and the
current document/view are always picked up. Edits to modules in lib/general are
picked up after a pyRevit Reload.
"""
import importlib
import sys

try:
    from importlib import reload as _reload     # IronPython 3 / CPython
except ImportError:
    _reload = reload                             # IronPython 2.7 builtin


def run(name):
    module = sys.modules.get(name)
    if module is None:
        module = importlib.import_module(name)
    else:
        module = _reload(module)
    module.main()
