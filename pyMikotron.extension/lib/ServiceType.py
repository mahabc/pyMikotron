# -*- coding: utf-8 -*-
"""Service Type - fill ELE_ServiceType from the ELE_Service_* / ELE_CC_* checkboxes.

Whole model. Every element that has ELE_ServiceType gets:
  - the service of the FIRST ticked checkbox, in the order of SERVICES below
  - "none" when no checkbox is ticked
Elements with more than one ticked checkbox are a modelling issue: they still get the
first service, and are listed in the output window so they can be fixed in the model.
"""
from pyrevit import revit, script
from Autodesk.Revit.DB import FilteredElementCollector, StorageType

from general.helpers import is_writable

TARGET_PARAM = "ELE_ServiceType"
NO_SERVICE = "none"

# Checked in this order; the first ticked one wins.
SERVICES = [
    ("ELE_Service_SmallPower", "Small Power"),
    ("ELE_Service_Telecom",    "Telecom"),
    ("ELE_CC_HV",              "High Voltage"),
    ("ELE_CC_LV_Tray",         "Low Voltage"),
    ("ELE_CC_LV_Ladder",       "Low Voltage"),
    ("ELE_Service_Control",    "Control"),
    ("ELE_Service_Lighting",   "Lighting"),
    ("ELE_Service_Security",   "Security"),
    ("ELE_CC_MV",              "Medium Voltage"),
    ("ELE_Service_FireAlarm",  "Fire Alarm"),
    ("ELE_Service_Emergency",  "Emergency"),
    ("ELE_Service_Earthing",   "Earthing"),
    ("ELE_Service_Other",      "Other"),
]


def ticked_services(element):
    ticked = []
    for param_name, service in SERVICES:
        p = element.LookupParameter(param_name)
        if p is not None and p.StorageType == StorageType.Integer and p.AsInteger() == 1:
            ticked.append((param_name, service))
    return ticked


def main():
    doc = revit.doc
    output = script.get_output()

    elements = [e for e in FilteredElementCollector(doc).WhereElementIsNotElementType()
                if e.LookupParameter(TARGET_PARAM) is not None]

    updated, unchanged, not_writable, multiple = 0, 0, [], []
    with revit.Transaction("Set " + TARGET_PARAM):
        for e in elements:
            target = e.LookupParameter(TARGET_PARAM)
            if not is_writable(target, StorageType.String):
                not_writable.append(e)
                continue
            ticked = ticked_services(e)
            value = ticked[0][1] if ticked else NO_SERVICE
            if len(ticked) > 1:
                multiple.append((e, ticked))
            if (target.AsString() or "") == value:
                unchanged += 1
            elif target.Set(value):
                updated += 1

    output.print_md("## Service Type")
    output.print_md("**Updated:** {} | **Unchanged:** {} | **Not writable:** {} | "
                    "**Multiple checkboxes:** {}".format(updated, unchanged,
                                                         len(not_writable), len(multiple)))
    if multiple:
        output.print_md("### Multiple checkboxes ticked (first one was used)")
        output.print_table(
            [[output.linkify(e.Id), e.Category.Name if e.Category else "",
              ticked[0][1], ", ".join(p for p, _ in ticked)] for e, ticked in multiple],
            columns=["Element", "Category", "Used", "Ticked checkboxes"])
    if not_writable:
        output.print_md("### {} not writable (read-only or not text)".format(TARGET_PARAM))
        output.print_md(", ".join(output.linkify(e.Id) for e in not_writable))
