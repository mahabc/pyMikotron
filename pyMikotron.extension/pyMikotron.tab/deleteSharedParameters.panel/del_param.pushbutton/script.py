from pyrevit import forms
import clr
import os

# Load EPPlus
lib_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib")
)

clr.AddReferenceToFileAndPath(
    os.path.join(lib_path, "EPPlus.dll")
)

from OfficeOpenXml import ExcelPackage
from System.IO import FileInfo


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
    
    values = []
    # Print all values
    for r in range(1, rows + 1):
        
        for c in range(1, cols + 1):
            values.append(sheet.Cells[r, c].Value)

        print(values)
        print(sheet.Cells[r, 1].Style.HorizontalAlignment)
        print(sheet.Cells[r, 1].Merge)



    package.Dispose()