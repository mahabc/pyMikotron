from pyrevit import revit, forms

import clr
clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Structure import StructuralFramingUtils

doc = revit.doc
view = revit.active_view

def select_in_view():
    beams = (
        FilteredElementCollector(doc, view.Id)
        .OfCategory(BuiltInCategory.OST_StructuralFraming)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    if not beams:
        forms.alert("No structural beams found in the current view.")
        return
    return beams


def select_all():
    

    beams = (
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_StructuralFraming)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    if not beams:
        forms.alert("No structural beams found in the current view.")
        return
    return beams

def disallow_joint_in_beams():

    options = ["Select beams in view", "Select all beams"]

    i = forms.SelectFromList.show(
        options,
        title="Select Beams",
        button_name="Select"
    )

    if i is None:
        return

    if i == "Select beams in view":
        beams = select_in_view()

    elif i == "Select all beams":
        beams = select_all()

    if not beams:
        return

    count = [len(beams)]

    with revit.Transaction("Disallow Joint"):
        for beam in beams:
            try:
                StructuralFramingUtils.DisallowJoinAtEnd(beam, 0)
                StructuralFramingUtils.DisallowJoinAtEnd(beam, 1)
            except Exception as e:
                forms.alert("An error occurred:\n{}".format(e))
    
    forms.alert("Join disallowed for all structural beams ({}).".format(len(beams)))

