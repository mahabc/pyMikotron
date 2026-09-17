from pyrevit import forms, revit
from Autodesk.Revit.DB import *
import clr
import os
from System import Guid
from uuid import UUID

doc = revit.doc


# ---------------------------------------------------------
# Load EPPlus
# ---------------------------------------------------------

lib_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__))
)

clr.AddReferenceToFileAndPath(
    os.path.join(lib_path, "EPPlus.dll")
)

from OfficeOpenXml import ExcelPackage
from System.IO import FileInfo


# ---------------------------------------------------------
# Excel cell GUID checker
# ---------------------------------------------------------

def is_guid(value):
    try:
        UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


# ---------------------------------------------------------
# Get shared parameters
# ---------------------------------------------------------

def get_all_shared_params():

    params = (
        FilteredElementCollector(doc)
        .OfClass(SharedParameterElement)
        .ToElements()
    )

    if not params:
        forms.alert(
            "No shared parameters found in the project.",
            title="Error"
        )
        return []

    return params


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def delete_shared_parameters():

    path = forms.pick_file(
        file_ext="xlsx",
        title="Select Excel File"
    )

    if not path:
        return


    # -----------------------------------------------------
    # Read Excel
    # -----------------------------------------------------

    package = ExcelPackage(FileInfo(path))

    sheets = package.Workbook.Worksheets

    sheet = forms.SelectFromList.show(
        sheets,
        name_attr="Name"
    )

    if not sheet:
        package.Dispose()
        return

    print("Selected sheet:", sheet.Name)

    rows = sheet.Dimension.End.Row
    cols = sheet.Dimension.End.Column

    print("Rows:", rows)
    print("Columns:", cols)


    # -----------------------------------------------------
    # Collect GUIDs from Excel
    # -----------------------------------------------------

    found_values = []

    for r in range(1, rows + 1):

        for c in range(1, cols + 1):

            cell_value = sheet.Cells[r, c].Value

            if is_guid(cell_value):
                found_values.append(Guid(str(cell_value)))

    package.Dispose()

    print("GUIDs found:", len(found_values))

    if not found_values:
        forms.alert(
            "No valid GUIDs were found in the Excel file.",
            title="Error"
        )
        return

    # -----------------------------------------------------
    # Get shared parameters in project
    # -----------------------------------------------------

    params = get_all_shared_params()


    # -----------------------------------------------------
    # Confirm found_values are GUIDs
    # -----------------------------------------------------
    for v in found_values:
        if not is_guid(v):
            forms.alert(
                "No valid GUID vas found in Excel file: {}".format(v),
                title="Error"
            )
            return

    # -----------------------------------------------------
    # Find shared parameters NOT in Excel
    # -----------------------------------------------------

    params_to_delete = []

    for p in params:

        guid_value = p.GuidValue

        if guid_value not in found_values:

            params_to_delete.append(p)


    print(
        "Shared parameters to delete:",
        len(params_to_delete)
    )


    if not params_to_delete:

        forms.alert(
            "No shared parameters need to be deleted.",
            title="Finished"
        )
        return


# -----------------------------------------------------
# Delete
# -----------------------------------------------------

    for p in params_to_delete:
    
        name = p.Name
        guid = p.GuidValue
        element_id = p.Id
    
        print(
            "TRYING: {} | GUID: {} | ID: {}".format(
                name,
                guid,
                element_id.IntegerValue
            )
        )
    
        try:
        
            with revit.Transaction(
                "Delete Shared Parameter: {}".format(name)
            ):
    
                doc.Delete(element_id)
    
            print(
                "SUCCESS: {} | GUID: {}".format(
                    name,
                    guid
                )
            )
    
        except Exception as e:
        
            print(
                "FAILED: {} | GUID: {} | ID: {}".format(
                    name,
                    guid,
                    element_id.IntegerValue
                )
            )
    
            print(
                "ERROR: {}".format(str(e))
            )
    
    
if __name__ == "__main__":
    main()