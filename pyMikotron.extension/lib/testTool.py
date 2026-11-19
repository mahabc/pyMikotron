import clr
import os
import re
from general import APISyntax

clr.AddReference("System.Drawing")
clr.AddReference("RevitAPI")

from System.Drawing import Size
from System.Drawing.Imaging import ImageFormat
from Autodesk.Revit.DB import *

from pyrevit import revit, forms, script


def main():
    doc = revit.doc
    view = doc.ActiveView

    #---------------------------------------------------------
    # Run testing script
    cats = APISyntax.get_all_categories()
    for c in cats:
        print(c)
