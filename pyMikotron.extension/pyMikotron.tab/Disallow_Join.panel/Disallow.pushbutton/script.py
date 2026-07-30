from pyrevit import revit, DB, forms
from pyrevit import script

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Structure import StructuralFramingUtils

def main():
    doc = revit.doc

    beams = FilteredElementCollector(doc)\
        .OfCategory(BuiltInCategory.OST_StructuralFraming)\
        .WhereElementIsNotElementType()\
        .ToElements()

    with revit.Transaction("Disallow Joint"):
        for beam in beams:
            try:
                StructuralFramingUtils.DisallowJoinAtEnd(beam, 0)
                StructuralFramingUtils.DisallowJoinAtEnd(beam, 1)
            except Exception as e:
                forms.alert(f"An error occurred: {e}")
        forms.alert("Join disallowed for all structural beams.")

if __name__ == "__main__":
    main()