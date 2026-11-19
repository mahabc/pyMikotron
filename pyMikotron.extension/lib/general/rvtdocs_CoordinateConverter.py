# -*- coding: utf-8 -*-
__title__   =  "Proo Coordinator"
# Author: Erik Frits from LearnRevitAPI.com

# ╦╔╦╗╔═╗╔═╗╦═╗╔╦╗╔═╗
# ║║║║╠═╝║ ║╠╦╝ ║ ╚═╗
# ╩╩ ╩╩  ╚═╝╩╚═ ╩ ╚═╝
#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
from Autodesk.Revit.DB import *

#pyRevit
from pyrevit import forms, script, revit

#.NET Imports
import clr
clr.AddReference('System')
from System.Collections.Generic import List


# ╦  ╦╔═╗╦═╗╦╔═╗╔╗ ╦  ╔═╗╔═╗
# ╚╗╔╝╠═╣╠╦╝║╠═╣╠╩╗║  ║╣ ╚═╗
#  ╚╝ ╩ ╩╩╚═╩╩ ╩╚═╝╩═╝╚═╝╚═╝
#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
doc    = __revit__.ActiveUIDocument.Document #type:Document
uidoc  = __revit__.ActiveUIDocument          # __revit__ is internal variable in pyRevit
app    = __revit__.Application
output = script.get_output()                 # pyRevit Output Menu


# ╔═╗╦  ╔═╗╔═╗╔═╗╔═╗╔═╗
# ║  ║  ╠═╣╚═╗╚═╗║╣ ╚═╗
# ╚═╝╩═╝╩ ╩╚═╝╚═╝╚═╝╚═╝
#░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
class CoordSys:
    Internal = 'Internal'
    Project  = 'Project'
    Survey   = 'Survey'

class CoordUnits:
    Meters   = 'Meters'
    Internal = 'Internal'

class PointConverter:
    pt_internal = None
    pt_survey   = None
    pt_project  = None

    def __init__(self, input_pt, coord_sys=CoordSys.Internal, coord_units = CoordUnits.Internal):
        """Class for converting XYZ points between any Coordinate Systems.
        Args:
            :param input_pt: The XYZ point in Internal Coordinate System. Adjust coord_sys argument if you want to use other Cooridnate Systems.
            :param coord_sys: The coordinate system chosen from CoordSys helper class (Internal, Project, Survey)

        Example:
            pt = elem.Location.Point

            converter   = PointConverter(pt, CoordSys.Internal)
            pt_survey   = converter.pt_survey   # XYZ in FEET
            pt_survey_m = converter.pt_survey_m # XYZ in Meters

            converter.print_in_metric(coord_sys=CoordSys.Survey)
        """
        # type: float, float, float, CoordSys

        if coord_units == CoordUnits.Meters:
            X = UnitUtils.ConvertToInternalUnits(input_pt.X, UnitTypeId.Meters)
            Y = UnitUtils.ConvertToInternalUnits(input_pt.Y, UnitTypeId.Meters)
            Z = UnitUtils.ConvertToInternalUnits(input_pt.Z, UnitTypeId.Meters)
            input_pt = XYZ(X,Y,Z)


        # Get Systems Transform
        srvTrans  = self._GetSurveyTransform()
        projTrans = self._GetProjectTransform()

        #1️⃣ INPUT - INTERNAL COORDINATE SYSTEM
        if coord_sys == CoordSys.Internal:
            self.pt_internal = input_pt
            self.pt_survey   = self._ApplyInverseTransformation(srvTrans, self.pt_internal)
            self.pt_project  = self._ApplyInverseTransformation(projTrans, self.pt_internal)

        #2️⃣ INPUT -  PROJECT COORDINATE SYSTEM
        elif coord_sys == CoordSys.Project:
            self.pt_project  = input_pt
            self.pt_internal = self._ApplyTransformation(projTrans, self.pt_project)
            self.pt_survey   = self._ApplyInverseTransformation(srvTrans, self.pt_internal)

        #3️⃣ - SURVEY COORDINATE SYSTEM
        elif coord_sys == CoordSys.Survey:
            self.pt_survey   = input_pt
            self.pt_internal = self._ApplyTransformation(srvTrans, self.pt_survey)
            self.pt_project  = self._ApplyInverseTransformation(projTrans, self.pt_internal)

        else:
            raise Exception("Wrong argument value for 'coord_sys' in PointConverter class.")


        #🧮 Create Metric Points
        self.pt_internal_m = self._get_metric_XYZ(CoordSys.Internal)
        self.pt_project_m   = self._get_metric_XYZ(CoordSys.Project)
        self.pt_survey_m   = self._get_metric_XYZ(CoordSys.Survey)


    def print_in_metric(self, coord_sys, units=UnitTypeId.Meters):
        """ Helper function to display coordinates in Metric System."""
        pt_m = self._get_metric_XYZ(coord_sys, units)
        print('[{}] XYZ: ({}m, {}m, {}m)'.format(coord_sys, round(pt_m.X,4), round(pt_m.Y,4), round(pt_m.Z,4)))


    #🚧 INTERNAL HELPING METHODS
    def _get_metric_XYZ(self, coord_sys, units=UnitTypeId.Meters):
        """Convert the point into Metric XYZ System.
        NB! Do not use it with Revit API as it needs internal units."""
        # Get Point With Correct Coordinate System
        if coord_sys   == CoordSys.Internal:  pt = self.pt_internal
        elif coord_sys == CoordSys.Project: pt = self.pt_project
        elif coord_sys == CoordSys.Survey:  pt = self.pt_survey

        # Convert Values to Metric
        X_m = UnitUtils.ConvertFromInternalUnits(pt.X, units)
        Y_m = UnitUtils.ConvertFromInternalUnits(pt.Y, units)
        Z_m = UnitUtils.ConvertFromInternalUnits(pt.Z, units)

        return (XYZ(X_m, Y_m, Z_m))

    def _GetSurveyTransform(self):
        """Gets the Active Project Locations Transform (Survey)."""
        return doc.ActiveProjectLocation.GetTotalTransform()

    def _GetProjectTransform(self):
        """Get the Project Base Points Transform."""
        basePtLoc = next((l for l in FilteredElementCollector(doc) \
                          .OfClass(ProjectLocation) \
                          .WhereElementIsNotElementType() \
                          .ToElements() if l.Name == "Project"), None)
        return basePtLoc.GetTotalTransform()

    def _ApplyInverseTransformation(self, t, pt):
        """Applies the inverse transformation of
        the given Transform to the given point."""
        return t.Inverse.OfPoint(pt)

    def _ApplyTransformation(self, t, pt):
        """Applies the transformation of
        the given Transform to the given point."""
        return t.OfPoint(pt)



# ╔═╗═╗ ╦╔═╗╔╦╗╔═╗╦  ╔═╗
# ║╣ ╔╩╦╝╠═╣║║║╠═╝║  ║╣ 
# ╚═╝╩ ╚═╩ ╩╩ ╩╩  ╩═╝╚═╝ EXAMPLE


# Pick Elements For Test
#------------------------------
from pyrevit import revit
boxes = revit.query.get_elements_by_familytype(family_name='Box', symbol_name='PointBox') # 

# Data Placeholder
#------------------------------
data    = []
for box in boxes:

    # Get Element Coordinate Point
    pt_ft = box.Location.Point


    # Create Point Converter
    converter = PointConverter(pt_ft, CoordSys.Internal)

    #📐 Get Converted Coordinates in Feet
    pt_survey_ft   = converter.pt_survey       # Coorindate in Feet
    pt_project_ft  = converter.pt_project      # Coorindate in Feet
    pt_internal_ft = converter.pt_internal     # Coorindate in Feet

    #📏 Get Converted Coorinates in Meters
    pt_survey_m   = converter.pt_survey_m        # Coorindate in Meters
    pt_project_m  = converter.pt_project_m     # Coorindate in Meters
    pt_internal_m = converter.pt_internal_m    # Coorindate in Meters

    # Print Values in Metric
    converter.print_in_metric(coord_sys=CoordSys.Internal)
    converter.print_in_metric(coord_sys=CoordSys.Project)
    converter.print_in_metric(coord_sys=CoordSys.Survey)



    #⚠️ P.S.  Points in meters create fake XYZ points that would display correct values in meters
    #       But they wouldn not match the real Revit locations (because it needs Internal in Feet...)


# Happy Coding!
# Author: Erik Frits from LearnRevitAPI.com