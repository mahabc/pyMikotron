import clr
import os
import re

clr.AddReference("System.Drawing")
clr.AddReference("RevitAPI")

from System.Drawing import Size
from System.Drawing.Imaging import ImageFormat
from Autodesk.Revit.DB import *

from pyrevit import revit, forms, script

doc = revit.doc
view = doc.ActiveView

def get_all_parameters(element):
    return element.Parameters
    # Returns: ParameterSet (Autodesk.Revit.DB.ParameterSet)

def get_all_text_note_types():
    return FilteredElementCollector(doc).OfClass(TextNoteType).ToElements()
    # Returns: ICollection[Element] of TextNoteType (Autodesk.Revit.DB.TextNoteType)

def get_all_dimension_types():
    return FilteredElementCollector(doc).OfClass(DimensionType).ToElements()
    # Returns: ICollection[Element] of DimensionType (Autodesk.Revit.DB.DimensionType)

def get_all_views():
    return FilteredElementCollector(doc).OfClass(View).ToElements()
    # Returns: ICollection[Element] of View (Autodesk.Revit.DB.View)

def get_all_categories():
    cats = doc.Settings.Categories
    categories = []
    for c in cats:
        bic=BuiltInCategory(c.Id.IntegerValue)
        categories.append(bic)
    return categories
    # Returns: Categories (Autodesk.Revit.DB.Categories)

def get_elements_of_category(category):
    return FilteredElementCollector(doc).OfCategory(category).WhereElementIsNotElementType().ToElements()
    # Returns: ICollection[Element] (Autodesk.Revit.DB.Element)

def get_all_elements():
    return FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements()
    # Returns: ICollection[Element] (Autodesk.Revit.DB.Element)

def get_all_element_types():
    return FilteredElementCollector(doc).WhereElementIsElementType().ToElements()
    # Returns: ICollection[Element] (Autodesk.Revit.DB.ElementType)

def get_all_family_symbols():
    return FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements()
    # Returns: ICollection[Element] of FamilySymbol (Autodesk.Revit.DB.FamilySymbol)

def get_all_families():
    return FilteredElementCollector(doc).OfClass(Family).ToElements()
    # Returns: ICollection[Element] of Family (Autodesk.Revit.DB.Family)

def get_all_filters():
    return FilteredElementCollector(doc).OfClass(ParameterFilterElement).ToElements()
    # Returns: ICollection[Element] of ParameterFilterElement (Autodesk.Revit.DB.ParameterFilterElement)
    
def get_element_type(element):
    return doc.GetElement(element.GetTypeId())
    # Returns: ElementType (Autodesk.Revit.DB.ElementType)

def get_type_name(element):
    return element.LookupParameter("Type Name").AsString()
    # Returns: str
    
def get_element_family(element):
    return element.Symbol.Family
    # Returns: Family (Autodesk.Revit.DB.Family)

def get_element_family_name(element):
    if not isinstance(element, FamilyInstance):
        return None

    try:
        symbol = element.Symbol
        if symbol is None:
            return None

        family = symbol.Family
        if family is None:
            return None

        return Element.Name.GetValue(family)

    except:
        return None

def get_parameter_from_type(element_type, name):
    return element_type.LookupParameter(name)
    # Returns: Parameter (Autodesk.Revit.DB.Parameter)

def get_parameter_by_name(element, name):
    return element.LookupParameter(name)
    # Returns: Parameter (Autodesk.Revit.DB.Parameter)

def set_parameter(parameter, value):
    return parameter.Set(value)
    # Returns: bool

def inspect_parameter(parameter):
    return {
        "name": parameter.Definition.Name,
        "storage_type": parameter.StorageType,
        "value": parameter.AsValueString(),
        "raw_value": parameter.AsDouble() if parameter.StorageType == StorageType.Double else
                     parameter.AsInteger() if parameter.StorageType == StorageType.Integer else
                     parameter.AsElementId() if parameter.StorageType == StorageType.ElementId else
                     parameter.AsString()
    }

def get_element_bbox(element):
    return element.get_BoundingBox(None)
    # Returns: BoundingBoxXYZ (Autodesk.Revit.DB.BoundingBoxXYZ)

def get_bbox_2d(bbox):
    return Outline(
        XYZ(bbox.Min.X, bbox.Min.Y, 0),
        XYZ(bbox.Max.X, bbox.Max.Y, 0)
    )
    # Returns: Outline (Autodesk.Revit.DB.Outline)

def get_element_curve(element):
    return element.Location.Curve
    # Returns: Curve (Autodesk.Revit.DB.Curve)

def create_curve(start, end):
    return Line.CreateBound(start, end)
    # Returns: Line (Autodesk.Revit.DB.Line)

#start = XYZ(x1, y1, z1)
#end = XYZ(x2, y2, z2)
# Inputs: XYZ points (Autodesk.Revit.DB.XYZ)

def get_curve_endpoints(curve):
    return curve.GetEndPoint(0), curve.GetEndPoint(1)
    # Returns: tuple[XYZ, XYZ]

def get_curve_vector(curve):
    return curve.GetEndPoint(1) - curve.GetEndPoint(0)
    # Returns: XYZ

def get_element_faces(element):
    options = Options()
    geometry = element.get_Geometry(options)
    return [face for obj in geometry for face in obj.Faces]
    # Returns: list[Face]

def get_face_elements(face):
    return face.Reference
    # Returns: Reference

def get_element_by_id(element_id):
    return doc.GetElement(element_id)
    # Returns: Element

def place_element_at_point(family_symbol, point, level):
    if not family_symbol.IsActive:
        family_symbol.Activate()
    return doc.Create.NewFamilyInstance(
        point,
        family_symbol,
        level,
        StructuralType.NonStructural
    )
    # point: XYZ
    # level: Level
    # Returns: FamilyInstance

def place_beam(curve, family_symbol, level):
    return doc.Create.NewFamilyInstance(
        curve,
        family_symbol,
        level,
        StructuralType.Beam
    )
    # Returns: FamilyInstance

def place_wall(curve, wall_type, level):
    return Wall.Create(
        doc,
        curve,
        wall_type.Id,
        level.Id,
        False
    )
    # Returns: Wall

def place_element(point, family_symbol, structural_type):
    return doc.Create.NewFamilyInstance(
        point,
        family_symbol,
        structural_type
    )
    # Returns: FamilyInstance

def place_pipe(curve, pipe_type, level):
    return Pipe.Create(
        doc,
        pipe_type.Id,
        level.Id,
        curve.GetEndPoint(0),
        curve.GetEndPoint(1)
    )
    # Returns: Pipe

def place_annotation_symbol(point, family_symbol, view):
    return doc.Create.NewFamilyInstance(
        point,
        family_symbol,
        view
    )
    # point: XYZ
    # family_symbol: FamilySymbol
    # view: View
    # Returns: FamilyInstance

def place_text_note(point, text, text_note_type, view):
    return TextNote.Create(
        doc,
        view.Id,
        point,
        text,
        text_note_type.Id
    )
    # Returns: TextNote
    
def place_filled_region(boundary, filled_region_type, view):
    return FilledRegion.Create(
        doc,
        filled_region_type.Id,
        view.Id,
        boundary
    )
    # boundary: IList[CurveLoop]
    # Returns: FilledRegion

def curve_loop_from_points(points):
    loop = CurveLoop()
    for i in range(len(points)):
        loop.Append(Line.CreateBound(points[i], points[(i + 1) % len(points)]))
    return [loop]
    # points: list[XYZ]
    # Returns: CurveLoop

def place_detail_line(curve, view):
    return doc.Create.NewDetailCurve(view, curve)
    # curve: Curve
    # view: View
    # Returns: DetailCurve

def place_model_line(curve, sketch_plane):
    return doc.Create.NewModelCurve(curve, sketch_plane)
    # curve: Curve
    # sketch_plane: SketchPlane
    # Returns: ModelCurve

def get_view_plane(view):
    return Plane.CreateByNormalAndOrigin(view.ViewDirection, view.Origin)

def get_sym_hosting(family_symbol):
    hosting_behavior = {
        0: None,
        1: "Wall",
        2: "Floor",
        3: "Ceiling",
        4: "Roof",
        5: "Face"
    }
    return hosting_behavior.get(family_symbol.Family.get_Parameter(
        BuiltInParameter.FAMILY_HOSTING_BEHAVIOR
    ).AsInteger())
    # Returns: int
    # 0 = None
    # 1 = Wall
    # 2 = Floor
    # 3 = Ceiling
    # 4 = Roof
    # 5 = Face

def place_hosted_element(family_symbol, host, level, point):
    if not family_symbol.IsActive:
        family_symbol.Activate()
    return doc.Create.NewFamilyInstance(
        point,
        family_symbol,
        host,
        level,
        StructuralType.NonStructural
    )
    # host: Element (Wall / Floor / Ceiling)
    # level: Level
    # point: XYZ
    # Returns: FamilyInstance

def get_elements_by_param_value(param_name, param_value):
    param_id = ElementId(BuiltInParameter(param_name))
    return (FilteredElementCollector(doc)
            .WherePasses(ParameterFilterRuleFactory.CreateEqualsRule(
                param_id, param_value))
            .WhereElementIsNotElementType()
            .ToElements())
    # Returns: ICollection[Element]

def get_all_parameters():
    pnames = []
    params = []
    parameter_elements = FilteredElementCollector(doc).OfClass(ParameterElement).ToElements()
    shared_parameters = FilteredElementCollector(doc).OfClass(SharedParameterElement).ToElements()

    for p in shared_parameters:
        name = p.Name
        pnames.append(name)
        params.append(p)
        
    for p in parameter_elements:
        name = p.Name
        pnames.append(name)
        params.append(p)
        
    #built_in_parameters = list(Enum.GetValues(BuiltInParameter.GetType()))
    return pnames, params #+ built_in_parameters
    # Returns: list[ParameterElement / SharedParameterElement / BuiltInParameter]

def get_builtin_parameters():
    enum_type = BuiltInParameter
    names = Enum.GetNames(enum_type)

    return [getattr(BuiltInParameter,name) for name in names]

def get_param_id(element, param_name):
    if isinstance(param_name, BuiltInParameter):
        return ElementId(param_name)

    param = element.LookupParameter(param_name)
    return param.Id if param else None

def by_id(element_id):
    if isinstance(element_id, str):
        return doc.GetElement(element_id)  # UniqueId
    return doc.GetElement(ElementId(element_id))  # numeric ElementId

def get_wall_curve_point(position = 0.5, wall = None):
    if wall is not None:
        return wall.Location.Curve.Evaluate(position, True)

def select_in_view(uidoc, element_list):
    uidoc.Selection.SetElementIds(List[ElementId]([elem.Id for elem in element_list]))
    

"""TransactionManager.Instance.EnsureInTransaction(doc)

TransactionManager.Instance.TransactionTaskDone()"""