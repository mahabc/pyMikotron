# -*- coding: utf-8 -*-
"""Iso 01 - create the empty isometric schedules (step 1 of 3).

Collects every model element (any category) with the iso parameter filled out
(default PIP_IsoGroup) and, for each iso value you pick, creates one schedule per
schedulable category found in that group:
    name             ISO_<Category>_<value>
    PIP_IsoGroup     <value>
    01_Organisation  ISO
Schedules whose name already exists are skipped.

Manual step afterwards: apply the category schedule templates (they must contain the
iso parameter field), then run Iso 02.
"""
from collections import OrderedDict

from pyrevit import revit, script
from Autodesk.Revit.DB import FilteredElementCollector, ViewSchedule

from general.helpers import set_param
from general.iso import ask_param_and_groups

TITLE = "Iso 01 - Schedules"
ORG_PARAM, ORG_VALUE = "01_Organisation", "ISO"


def main():
    doc = revit.doc
    output = script.get_output()

    param_name, groups = ask_param_and_groups(doc, TITLE)
    existing = set(s.Name for s in FilteredElementCollector(doc).OfClass(ViewSchedule))

    created, skipped, failed = [], [], []
    with revit.Transaction("Iso 01 - Create Schedules"):
        for value, elements in groups.items():
            categories = OrderedDict()
            for e in elements:
                if ViewSchedule.IsValidCategoryForSchedule(e.Category.Id):
                    categories.setdefault(e.Category.Name, e.Category)
            for cat_name, cat in sorted(categories.items()):
                name = "ISO_{}_{}".format(cat_name, value)
                if name in existing:
                    skipped.append(name)
                    continue
                try:
                    schedule = ViewSchedule.CreateSchedule(doc, cat.Id)
                    schedule.Name = name
                    set_param(schedule, param_name, value)
                    set_param(schedule, ORG_PARAM, ORG_VALUE)
                    existing.add(name)
                    created.append(schedule)
                except Exception as ex:
                    failed.append((name, str(ex)))

    output.print_md("## " + TITLE)
    output.print_md("**Created:** {} | **Already existed:** {} | **Failed:** {}".format(
        len(created), len(skipped), len(failed)))
    for s in created:
        output.print_md("- {} {}".format(output.linkify(s.Id), s.Name))
    if skipped:
        output.print_md("### Already existed\n" + "\n".join("- " + n for n in skipped))
    if failed:
        output.print_table([list(f) for f in failed], columns=["Schedule", "Error"], title="Failed")
    output.print_md("**Next:** apply the schedule templates, then run Iso 02.")
