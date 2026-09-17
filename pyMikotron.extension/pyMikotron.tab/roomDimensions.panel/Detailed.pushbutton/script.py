from pyrevit import revit, forms
import os

import clr
clr.AddReference("RevitAPI")
import placeRoomDimensions

from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Structure import StructuralFramingUtils

doc = revit.doc
view = revit.active_view

lib_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))



def main():

    placeRoomDimensions.place_dimensions()

if __name__ == "__main__":
    main()



