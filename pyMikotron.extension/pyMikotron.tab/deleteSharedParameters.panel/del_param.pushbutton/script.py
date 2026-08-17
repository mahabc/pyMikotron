from pyrevit import forms
import clr
import os
from uuid import UUID

# Load EPPlus
lib_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib")
)

clr.AddReferenceToFileAndPath(
    os.path.join(lib_path, "EPPlus.dll")
)

from OfficeOpenXml import ExcelPackage
from System.IO import FileInfo

#guid checker
def is_guid(value):
    try:
        UUID(str(value))
        return True
    except ValueError:
        return False
    
# Pick file
path = forms.pick_file(file_ext="xlsx", title="Select Excel File")

if path:
    package = ExcelPackage(FileInfo(path))

    # First worksheet
    sheets = package.Workbook.Worksheets
    sheet = forms.SelectFromList.show(sheets, name_attr="Name")
    print("Selected sheet:", sheet.Name)


    # Worksheet dimensions
    rows = sheet.Dimension.End.Row
    cols = sheet.Dimension.End.Column

    print("Rows:", rows)
    print("Columns:", cols)
    
    found_values = []
    found_names = []

    for r in range(1, rows + 1):
        for c in range(1, cols + 1):
            cell_value = sheet.Cells[r, c].Value
            guid_name = sheet.Cells[r,c+1].Value
            if cell_value and is_guid(cell_value):
                found_values.append(cell_value)
                found_names.append(guid_name)

    print(found_values, found_names)
     


    package.Dispose()