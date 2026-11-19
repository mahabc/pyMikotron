# -*- coding: utf-8 -*-
"""Iso 02 - set the iso filter on the isometric schedules (step 2 of 3).

For every schedule whose own iso parameter (default PIP_IsoGroup) is filled out:
existing schedule filters are removed and one filter  <iso field> = <schedule value>
is added.

Prerequisites (manual, after Iso 01):
  - schedule templates applied, containing the iso parameter as a field
  - "Filter" not locked by the schedule's view template
Schedules without the field, or whose filters are locked, are reported.
"""
from pyrevit import revit, script
from Autodesk.Revit.DB import FilteredElementCollector, ScheduleFilter, ScheduleFilterType, ViewSchedule

from general.helpers import param_text
from general.iso import ask_param

TITLE = "Iso 02 - Schedule Filters"


def find_field(definition, name):
    for i in range(definition.GetFieldCount()):
        field = definition.GetField(i)
        if field.GetName() == name:
            return field
    return None


def main():
    doc = revit.doc
    output = script.get_output()

    param_name = ask_param(TITLE)
    schedules = [s for s in FilteredElementCollector(doc).OfClass(ViewSchedule)
                 if not s.IsTemplate and param_text(s.LookupParameter(param_name))]

    done, problems = [], []
    with revit.Transaction("Iso 02 - Set Schedule Filters"):
        for s in schedules:
            value = param_text(s.LookupParameter(param_name))
            definition = s.Definition
            field = find_field(definition, param_name)
            if field is None:
                problems.append((s, "no '{}' field (apply the schedule template first)".format(param_name)))
                continue
            try:
                for i in reversed(range(definition.GetFilterCount())):
                    definition.RemoveFilter(i)
                definition.AddFilter(ScheduleFilter(field.FieldId, ScheduleFilterType.Equal, value))
                done.append((s, value))
            except Exception as ex:
                problems.append((s, str(ex)))

    output.print_md("## " + TITLE)
    output.print_md("**Filtered:** {} | **Problems:** {}".format(len(done), len(problems)))
    for s, value in done:
        output.print_md("- {} {} = {}".format(output.linkify(s.Id), s.Name, value))
    if problems:
        output.print_table([[output.linkify(s.Id), s.Name, msg] for s, msg in problems],
                           columns=["Id", "Schedule", "Problem"], title="Problems")
    output.print_md("**Next:** check the schedules, then run Iso 03.")
