# -*- coding: utf-8 -*-
"""Shared by the Iso 01 / Iso 02 / Iso 03 tools: iso groups and their dialogs."""
from collections import OrderedDict

from pyrevit import forms, script
from Autodesk.Revit.DB import FilteredElementCollector

from general.helpers import is_model_element, param_text
from general import ui

DEFAULT_PARAM = "PIP_IsoGroup"


def ask_param(title):
    param_name = ui.ask_text("Iso parameter name:", title, ui.recall("iso_param", DEFAULT_PARAM))
    if not param_name:
        script.exit()
    ui.remember(iso_param=param_name)
    return param_name


def iso_groups(doc, param_name):
    """OrderedDict value -> list of model elements (any category), sorted by value."""
    groups = {}
    for e in FilteredElementCollector(doc).WhereElementIsNotElementType():
        if not is_model_element(e):
            continue
        value = param_text(e.LookupParameter(param_name))
        if value:
            groups.setdefault(value, []).append(e)
    return OrderedDict(sorted(groups.items()))


def ask_param_and_groups(doc, title):
    """Iso parameter name + the groups picked from a list. Returns (name, OrderedDict)."""
    param_name = ask_param(title)
    groups = iso_groups(doc, param_name)
    if not groups:
        forms.alert("No model elements have '{}' filled out.".format(param_name),
                    title=title, exitscript=True)
    labels = OrderedDict(("{}  ({} elements)".format(v, len(els)), v) for v, els in groups.items())
    picked = ui.pick_many(list(labels.keys()), "Iso groups to process", "Process")
    return param_name, OrderedDict((labels[p], groups[labels[p]]) for p in picked)
