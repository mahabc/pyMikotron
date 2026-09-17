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
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib")
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



def main():
    # -----------------------------------------------------
    # Read Excel class def __init__(self, path)
    # -----------------------------------------------------
    excel_path  = forms.pick_file(file_ext="xlsx", title="Select Excel file")

    print("Success")


if __name__ == "__main__":
    main()