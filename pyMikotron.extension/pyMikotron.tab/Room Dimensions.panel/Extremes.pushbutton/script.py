import clr
import os
import re
import placeRoomExtremes

clr.AddReference("System.Drawing")
clr.AddReference("RevitAPI")

from System.Drawing import Size
from System.Drawing.Imaging import ImageFormat
from Autodesk.Revit.DB import *

from pyrevit import revit, forms, script


lib_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib")
)

doc = revit.doc
view = doc.ActiveView

#---------------------------------------------------------
# Run testing script

placeRoomExtremes.place_dimensions()