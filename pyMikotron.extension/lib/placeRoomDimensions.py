import clr

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *

from pyrevit import revit,script


# Current Revit document and active view
doc=revit.doc
view=doc.ActiveView


# Rooms visible in the active view
rooms=FilteredElementCollector(doc,view.Id).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType().ToElements()


# Room boundary settings
boundary_options=SpatialElementBoundaryOptions()
boundary_options.SpatialElementBoundaryLocation=SpatialElementBoundaryLocation.Finish


# Geometry settings used to retrieve wall edge references
geometry_options=Options()
geometry_options.ComputeReferences=True
geometry_options.IncludeNonVisibleObjects=True


# Dimension line offset from each room boundary
offset=UnitUtils.ConvertToInternalUnits(1.0,UnitTypeId.Millimeters)


dimensions=[]
errors=[]
debug=[]


# Returns a flat list of GeometryObjects, including instance geometry
def get_geometry_objects(geometry):

    objects=[]

    if geometry is None:
        return objects

    for obj in geometry:

        objects.append(obj)

        if isinstance(obj,GeometryInstance):

            instance_geometry=obj.GetInstanceGeometry()

            if instance_geometry is not None:
                objects.extend(get_geometry_objects(instance_geometry))

    return objects


# Returns normalized XY direction XYZ or None
def get_vector(start,end):

    vector=end.Subtract(start)
    vector=XYZ(vector.X,vector.Y,0)

    if vector.GetLength()==0:
        return None

    return vector.Normalize()


# Returns normalized perpendicular XY XYZ or None
def get_normal(direction):

    normal=XYZ(-direction.Y,direction.X,0)

    if normal.GetLength()==0:
        return None

    return normal.Normalize()


# Returns midpoint XYZ of a curve
def get_curve_midpoint(curve):

    return curve.Evaluate(0.5,True)


# Returns (start_reference,end_reference), or (None,None)
def get_curve_endpoint_references(curve):

    if curve is None:
        return None,None

    try:

        ref0=curve.GetEndPointReference(0)
        ref1=curve.GetEndPointReference(1)

        if ref0 is not None and ref1 is not None:
            return ref0,ref1

    except:
        pass

    return None,None


# Returns the source Curve of a CurveElement or LocationCurve, or None
def get_source_curve(element):

    if element is None:
        return None

    if isinstance(element,CurveElement):

        try:

            curve=element.GeometryCurve

            if curve is not None:
                return curve

        except:
            pass

    try:

        location=element.Location

        if isinstance(location,LocationCurve):

            curve=location.Curve

            if curve is not None:
                return curve

    except:
        pass

    return None


# Returns shortest perpendicular distance from point to an infinite line
def distance_point_to_line(point,start,direction):

    vector=point.Subtract(start)
    projection=vector.DotProduct(direction)
    projected=start.Add(direction.Multiply(projection))

    return point.DistanceTo(projected)


# Returns True when two normalized vectors are parallel within tolerance
def is_parallel(direction_a,direction_b,tolerance=0.995):

    if direction_a is None or direction_b is None:
        return False

    return abs(direction_a.DotProduct(direction_b))>=tolerance


# Returns (start_reference,end_reference), or (None,None)
def get_edge_endpoint_references(edge):

    if edge is None:
        return None,None

    try:

        ref0=edge.GetEndPointReference(0)
        ref1=edge.GetEndPointReference(1)

        if ref0 is not None and ref1 is not None:
            return ref0,ref1

    except:
        pass

    return None,None


# Returns (start_reference,end_reference,edge), or (None,None,None)
# Finds the wall geometry edge closest and parallel to the room boundary curve
def get_wall_edge_references(element,boundary_curve):

    if element is None:
        return None,None,None

    geometry=element.get_Geometry(geometry_options)

    if geometry is None:
        return None,None,None

    boundary_start=boundary_curve.GetEndPoint(0)
    boundary_end=boundary_curve.GetEndPoint(1)
    boundary_direction=get_vector(boundary_start,boundary_end)

    if boundary_direction is None:
        return None,None,None

    boundary_midpoint=get_curve_midpoint(boundary_curve)
    best_edge=None
    best_score=None

    for obj in get_geometry_objects(geometry):

        if not isinstance(obj,Solid) or obj.Volume<=0:
            continue

        for face in obj.Faces:

            if not isinstance(face,PlanarFace):
                continue

            if abs(face.FaceNormal.Z)>0.1:
                continue

            for loop in face.EdgeLoops:

                for edge in loop:

                    edge_curve=edge.AsCurve()

                    if edge_curve is None:
                        continue

                    try:

                        edge_start=edge_curve.GetEndPoint(0)
                        edge_end=edge_curve.GetEndPoint(1)

                    except:
                        continue

                    edge_direction=get_vector(edge_start,edge_end)

                    if not is_parallel(boundary_direction,edge_direction):
                        continue

                    edge_midpoint=get_curve_midpoint(edge_curve)
                    midpoint_distance=edge_midpoint.DistanceTo(boundary_midpoint)
                    line_distance=distance_point_to_line(boundary_midpoint,edge_start,edge_direction)
                    score=line_distance+midpoint_distance*0.01

                    if best_score is None or score<best_score:
                        best_score=score
                        best_edge=edge

    if best_edge is None:
        return None,None,None

    ref0,ref1=get_edge_endpoint_references(best_edge)

    if ref0 is None or ref1 is None:
        return None,None,None

    edge_curve=best_edge.AsCurve()
    edge_start=edge_curve.GetEndPoint(0)
    edge_end=edge_curve.GetEndPoint(1)

    same=edge_start.DistanceTo(boundary_start)+edge_end.DistanceTo(boundary_end)
    reverse=edge_start.DistanceTo(boundary_end)+edge_end.DistanceTo(boundary_start)

    if reverse<same:
        ref0,ref1=ref1,ref0

    return ref0,ref1,best_edge


# Returns boundary dictionary or None when valid references cannot be resolved
def get_boundary_references(segment):

    boundary_curve=segment.GetCurve()

    if boundary_curve is None:
        return None

    element_id=segment.ElementId

    if element_id==ElementId.InvalidElementId:
        return None

    element=doc.GetElement(element_id)

    if element is None:
        return None

    category_id=None

    if element.Category is not None:
        category_id=element.Category.Id.IntegerValue

    is_separator=category_id==int(BuiltInCategory.OST_RoomSeparationLines)

    ref0=None
    ref1=None
    source=None

    if is_separator:

        source=get_source_curve(element)
        ref0,ref1=get_curve_endpoint_references(source)

    else:

        ref0,ref1,source=get_wall_edge_references(element,boundary_curve)

    if ref0 is None or ref1 is None:
        return None

    return {
        "element":element,
        "element_id":element_id,
        "curve":boundary_curve,
        "source":source,
        "start":boundary_curve.GetEndPoint(0),
        "end":boundary_curve.GetEndPoint(1),
        "start_reference":ref0,
        "end_reference":ref1,
        "is_separator":is_separator
    }


# Returns the outward perpendicular XYZ used to offset a boundary dimension
def get_offset_side(boundary,room_boundaries):

    start=boundary["start"]
    end=boundary["end"]
    direction=get_vector(start,end)

    if direction is None:
        return None

    normal=get_normal(direction)

    if normal is None:
        return None

    midpoint=start.Add(end.Subtract(start).Multiply(0.5))
    positive_count=0
    negative_count=0

    for other in room_boundaries:

        if other is boundary:
            continue

        for point in [other["start"],other["end"]]:

            vector=point.Subtract(midpoint)
            projection=vector.DotProduct(normal)

            if projection>0.001:
                positive_count+=1

            elif projection<-0.001:
                negative_count+=1

    if positive_count>negative_count:
        return normal.Negate()

    return normal


# Returns a dimension Line parallel to the real room boundary curve, or None
def create_dimension_line(boundary,room_boundaries):

    start=boundary["start"]
    end=boundary["end"]
    normal=get_offset_side(boundary,room_boundaries)

    if normal is None:
        return None

    offset_vector=normal.Multiply(offset)
    z=view.GenLevel.Elevation

    dim_start=start.Add(offset_vector)
    dim_end=end.Add(offset_vector)

    dim_start=XYZ(dim_start.X,dim_start.Y,z)
    dim_end=XYZ(dim_end.X,dim_end.Y,z)

    return Line.CreateBound(dim_start,dim_end)


# Returns a created Dimension or None
def place_edge_dimension(boundary,room_boundaries):

    references=ReferenceArray()
    references.Append(boundary["start_reference"])
    references.Append(boundary["end_reference"])

    dimension_line=create_dimension_line(boundary,room_boundaries)

    if dimension_line is None:
        return None

    return doc.Create.NewDimension(view,dimension_line,references)


# Processes every room independently and returns nothing
def place_dimensions():

    with revit.Transaction("Dimension Room Edges"):

        for room in rooms:

            try:

                boundary_loops=room.GetBoundarySegments(boundary_options)

                if boundary_loops is None:
                    continue

                room_boundaries=[]
                room_dimensions=[]

                for loop in boundary_loops:

                    for segment in loop:

                        boundary=get_boundary_references(segment)

                        if boundary is not None:
                            room_boundaries.append(boundary)

                for boundary in room_boundaries:

                    try:

                        dimension=place_edge_dimension(boundary,room_boundaries)

                        if dimension is not None:
                            dimensions.append(dimension)
                            room_dimensions.append(dimension)

                    except Exception as ex:

                        errors.append("{} | {} : {}".format(room.Id,boundary["element_id"],ex))

                debug.append({
                    "room":room,
                    "boundaries":room_boundaries,
                    "dimensions":room_dimensions
                })

            except Exception as ex:

                errors.append("{} : {}".format(room.Id,ex))


place_dimensions()


output=script.get_output()

print("Dimensions created: {}".format(len(dimensions)))
print("Rooms with errors: {}".format(len(errors)))

if errors:

    print("\nERRORS:")

    for error in errors:
        print(error)