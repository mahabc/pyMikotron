# -*- coding: utf-8 -*-
"""Worksets - create user worksets from a list in Excel.

Pick an .xlsx file and one of its sheets. Every non-empty cell in column A
(no header row) is a workset name. Existing worksets are skipped and reported.
The model must be workshared.
"""
from pyrevit import forms, revit, script
from Autodesk.Revit.DB import FilteredWorksetCollector, Workset, WorksetKind, WorksetTable

from general import excel_reader
from general import ui

TITLE = "Worksets"


def read_column_a(path, sheet_name=None):
    reader = excel_reader.ExcelReader(path)
    reader.open()
    try:
        if sheet_name is None:
            sheet_name = ui.pick_one(reader.get_worksheet_names(), "Sheet with the workset list")
        ws = reader.get_worksheet(sheet_name)
        names = []
        if ws.Dimension is not None:
            for row in range(1, ws.Dimension.End.Row + 1):
                text = (ws.Cells[row, 1].Text or "").strip()
                if text and text not in names:
                    names.append(text)
        return sheet_name, names
    finally:
        reader.close()


def main():
    doc = revit.doc
    output = script.get_output()

    if not doc.IsWorkshared:
        forms.alert("This model is not workshared.\nEnable worksharing first "
                    "(Collaborate > Worksets).", title=TITLE, exitscript=True)

    path = forms.pick_file(file_ext="xlsx", title="Excel file with workset names")
    if not path:
        script.exit()
    sheet_name, names = read_column_a(path)
    if not names:
        forms.alert("Column A of sheet '{}' is empty.".format(sheet_name), title=TITLE, exitscript=True)

    existing = set(w.Name for w in FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset))
    created, skipped, failed = [], [], []
    with revit.Transaction("Create Worksets"):
        for name in names:
            if name in existing or not WorksetTable.IsWorksetNameUnique(doc, name):
                skipped.append(name)
                continue
            try:
                Workset.Create(doc, name)
                created.append(name)
            except Exception as ex:
                failed.append((name, str(ex)))

    output.print_md("## " + TITLE)
    output.print_md("Sheet **{}**: {} name(s) | **Created:** {} | **Already existed:** {} | "
                    "**Failed:** {}".format(sheet_name, len(names), len(created),
                                            len(skipped), len(failed)))
    for title, items in (("Created", created), ("Already existed", skipped)):
        if items:
            output.print_md("### " + title)
            output.print_md("\n".join("- " + n for n in items))
    if failed:
        output.print_table([[n, err] for n, err in failed], columns=["Name", "Error"], title="Failed")
