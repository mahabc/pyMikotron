import clr
import os


# ---------------------------------------------------------
# Load lib & EPPlus
# ---------------------------------------------------------

lib_path = os.path.dirname(__file__)


clr.AddReferenceToFileAndPath(
    os.path.join(lib_path, "EPPlus.dll")
)

from OfficeOpenXml import ExcelPackage
from System.IO import FileInfo


# ---------------------------------------------------------
# Excel Reader
# ---------------------------------------------------------

class ExcelReader(object):

    def __init__(self, path):
        self.path = path
        self.package = None
        self.workbook = None

    def open(self):
        self.package = ExcelPackage(FileInfo(self.path))
        self.workbook = self.package.Workbook

    def close(self):
        if self.package is not None:
            self.package.Dispose()
            self.package = None
            self.workbook = None

    def get_worksheet_names(self):
        names = []

        for worksheet in self.workbook.Worksheets:
            names.append(worksheet.Name)

        return names

    def get_worksheet(self, name):
        return self.workbook.Worksheets[name]

    def get_named_ranges(self):

        named_ranges = []
    
        for name in self.workbook.Names:
            named_ranges.append(name)
    
        if not named_ranges:
            print("No named ranges found in the workbook.")
    
        return named_ranges