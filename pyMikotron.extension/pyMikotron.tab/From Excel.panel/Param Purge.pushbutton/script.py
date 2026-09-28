from pyrevit import forms, revit
from Autodesk.Revit.DB import *
import clr
import os
from System import Guid
from uuid import UUID
import deleteSharedParameters

doc = revit.doc


# ---------------------------------------------------------
# Load EPPlus
# ---------------------------------------------------------

lib_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib")
)


from OfficeOpenXml import ExcelPackage
from System.IO import FileInfo


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():

    deleteSharedParameters.delete_shared_parameters()
    
if __name__ == "__main__":
    main()