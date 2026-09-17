from pyrevit import forms, revit, script
from Autodesk.Revit.DB import *
import clr
import os
from System import Guid
import System


# ---------------------------------------------------------
# Load lib & EPPlus 
# ---------------------------------------------------------

lib_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__))
)

clr.AddReferenceToFileAndPath(
    os.path.join(lib_path, "EPPlus.dll")
)

from OfficeOpenXml import ExcelPackage
from System.IO import FileInfo

import excel_reader
import geometry

# ---------------------------------------------------------
# Get Revit document
# ---------------------------------------------------------
doc = revit.doc
uidoc = revit.uidoc
view = revit.active_view #uidoc.ActiveView



def paint():
    # -----------------------------------------------------
    # Read Excel class def __init__(self, path)
    # -----------------------------------------------------
    excel_path  = forms.pick_file(file_ext="xlsx", title="Select Excel file")

    reader = excel_reader.ExcelReader(excel_path)

    reader.open()

    sheet_names = reader.get_worksheet_names()

    selected_sheet_name = forms.SelectFromList.show(
        sheet_names,
        title="Select a worksheet",
        multiselect=False
    )

    worksheet = reader.get_worksheet(selected_sheet_name)
    named_ranges = reader.get_named_ranges()
    for named_range in named_ranges:
        print(named_range.Name, named_range.Address)
