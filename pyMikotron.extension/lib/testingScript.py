#xxxxxxxxxxxxxxxxxxxxxx
import clr

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *

from pyrevit import revit, script


doc=revit.doc
view=doc.ActiveView


rooms=(
    FilteredElementCollector(doc,view.Id)
    .OfCategory(BuiltInCategory.OST_Rooms)
    .WhereElementIsNotElementType()
    .ToElements()
)


boundary_options=SpatialElementBoundaryOptions()
boundary_options.SpatialElementBoundaryLocation=(
    SpatialElementBoundaryLocation.Finish
)


geometry_options=Options()
geometry_options.ComputeReferences=True
geometry_options.IncludeNonVisibleObjects=True


# ---------------------------------------------------------
# Settings
# ---------------------------------------------------------

tolerance=UnitUtils.ConvertToInternalUnits(
    1.0,
    UnitTypeId.Millimeters
)

dimension_offset=UnitUtils.ConvertToInternalUnits(
    -1000.0,
    UnitTypeId.Millimeters
)


# ---------------------------------------------------------
# Geometry
# ---------------------------------------------------------

def get_solids(geometry):
    # Return all valid solids from element geometry.

    solids=[]

    if geometry is None:
        return solids

    for geo in geometry:

        if isinstance(geo,Solid):

            if geo.Volume>0:
                solids.append(geo)

        elif isinstance(geo,GeometryInstance):

            instance_geometry=geo.GetInstanceGeometry()

            if instance_geometry is not None:
                solids.extend(
                    get_solids(instance_geometry)
                )

    return solids


# ---------------------------------------------------------
# 2D Bounding Box
# ---------------------------------------------------------

def get_2d_bounding_box(boundary_loops):
    # Return the XY bounding box of the room boundary.

    points=[]

    for loop in boundary_loops:

        for segment in loop:

            curve=segment.GetCurve()

            if curve is None:
                continue

            points.append(curve.GetEndPoint(0))
            points.append(curve.GetEndPoint(1))

    if not points:
        return None

    min_x=min(p.X for p in points)
    max_x=max(p.X for p in points)
    min_y=min(p.Y for p in points)
    max_y=max(p.Y for p in points)

    return {
        "min_x":min_x,
        "max_x":max_x,
        "min_y":min_y,
        "max_y":max_y
    }


# ---------------------------------------------------------
# Wall Reference
# ---------------------------------------------------------

def get_wall_reference(segment):
    # Return the wall face reference and its dimension axis.

    element_id=segment.ElementId

    if element_id==ElementId.InvalidElementId:
        return None

    element=doc.GetElement(element_id)

    if element is None:
        return None

    geometry=element.get_Geometry(
        geometry_options
    )

    solids=get_solids(geometry)

    if not solids:
        return None

    midpoint=segment.GetCurve().Evaluate(
        0.5,
        True
    )

    best_reference=None
    best_face=None
    best_distance=None

    for solid in solids:

        for face in solid.Faces:

            if not isinstance(face,PlanarFace):
                continue

            if face.Reference is None:
                continue

            normal=face.FaceNormal

            if abs(normal.Z)>0.1:
                continue

            vector=midpoint.Subtract(
                face.Origin
            )

            distance=abs(
                vector.DotProduct(normal)
            )

            if (
                best_distance is None
                or distance<best_distance
            ):

                best_distance=distance
                best_reference=face.Reference
                best_face=face

    if best_reference is None:
        return None

    normal=best_face.FaceNormal

    if abs(normal.X)>abs(normal.Y):

        axis="X"
        coordinate=best_face.Origin.X

    else:

        axis="Y"
        coordinate=best_face.Origin.Y

    return {
        "reference":best_reference,
        "axis":axis,
        "coordinate":coordinate,
        "element_id":element_id,
        "midpoint":midpoint
    }


# ---------------------------------------------------------
# Room Separator Reference
# ---------------------------------------------------------

def get_separator_reference(segment):
    # Return the Room Separator curve reference.

    element_id=segment.ElementId

    if element_id==ElementId.InvalidElementId:
        return None

    element=doc.GetElement(element_id)

    if element is None:
        return None

    if not isinstance(element,ModelCurve):
        return None

    curve=element.GeometryCurve

    if curve is None:
        return None

    reference=curve.Reference

    if reference is None:
        return None

    midpoint=curve.Evaluate(
        0.5,
        True
    )

    direction=curve.ComputeDerivatives(
        0.5,
        True
    ).BasisX.Normalize()


    # Horizontal separator.
    # Position controlled by Y.

    if abs(direction.X)>abs(direction.Y):

        axis="Y"
        coordinate=midpoint.Y

    # Vertical separator.
    # Position controlled by X.

    else:

        axis="X"
        coordinate=midpoint.X


    return {
        "reference":reference,
        "axis":axis,
        "coordinate":coordinate,
        "element_id":element_id,
        "midpoint":midpoint
    }


# ---------------------------------------------------------
# Boundary References
# ---------------------------------------------------------

def get_boundary_references(boundary_loops):
    # Return all unique wall and separator references.

    references=[]
    used=set()

    for loop in boundary_loops:

        for segment in loop:

            element_id=segment.ElementId

            if element_id==ElementId.InvalidElementId:
                continue

            element=doc.GetElement(element_id)

            if element is None:
                continue

            boundary=None


            # Room Separator.

            if isinstance(element,ModelCurve):

                boundary=get_separator_reference(
                    segment
                )


            # Physical boundary element.

            else:

                boundary=get_wall_reference(
                    segment
                )


            if boundary is None:
                continue


            stable=boundary[
                "reference"
            ].ConvertToStableRepresentation(doc)


            if stable in used:
                continue

            used.add(stable)

            references.append(boundary)


    return references


# ---------------------------------------------------------
# Find Bounding Box Extreme References
# ---------------------------------------------------------

def get_extreme_references(boundaries,bbox):
    # Return one reference for each bounding-box extreme.

    min_x=None
    max_x=None
    min_y=None
    max_y=None

    min_x_distance=None
    max_x_distance=None
    min_y_distance=None
    max_y_distance=None


    for boundary in boundaries:

        axis=boundary["axis"]
        coordinate=boundary["coordinate"]


        if axis=="X":

            distance_min=abs(
                coordinate-bbox["min_x"]
            )

            distance_max=abs(
                coordinate-bbox["max_x"]
            )


            if (
                distance_min<=tolerance
                and (
                    min_x_distance is None
                    or distance_min<min_x_distance
                )
            ):

                min_x=boundary
                min_x_distance=distance_min


            if (
                distance_max<=tolerance
                and (
                    max_x_distance is None
                    or distance_max<max_x_distance
                )
            ):

                max_x=boundary
                max_x_distance=distance_max


        elif axis=="Y":

            distance_min=abs(
                coordinate-bbox["min_y"]
            )

            distance_max=abs(
                coordinate-bbox["max_y"]
            )


            if (
                distance_min<=tolerance
                and (
                    min_y_distance is None
                    or distance_min<min_y_distance
                )
            ):

                min_y=boundary
                min_y_distance=distance_min


            if (
                distance_max<=tolerance
                and (
                    max_y_distance is None
                    or distance_max<max_y_distance
                )
            ):

                max_y=boundary
                max_y_distance=distance_max


    return {
        "min_x":min_x,
        "max_x":max_x,
        "min_y":min_y,
        "max_y":max_y
    }


# ---------------------------------------------------------
# Create X Dimension
# ---------------------------------------------------------

def create_x_dimension(min_ref,max_ref,bbox):
    # Create horizontal dimension between MIN X and MAX X.

    if min_ref is None or max_ref is None:
        return None

    reference_array=ReferenceArray()

    reference_array.Append(
        min_ref["reference"]
    )

    reference_array.Append(
        max_ref["reference"]
    )


    y=bbox["min_y"]-dimension_offset

    x1=bbox["min_x"]
    x2=bbox["max_x"]


    line=Line.CreateBound(
        XYZ(x1,y,view.GenLevel.Elevation),
        XYZ(x2,y,view.GenLevel.Elevation)
    )


    return doc.Create.NewDimension(
        view,
        line,
        reference_array
    )


# ---------------------------------------------------------
# Create Y Dimension
# ---------------------------------------------------------

def create_y_dimension(min_ref,max_ref,bbox):
    # Create vertical dimension between MIN Y and MAX Y.

    if min_ref is None or max_ref is None:
        return None

    reference_array=ReferenceArray()

    reference_array.Append(
        min_ref["reference"]
    )

    reference_array.Append(
        max_ref["reference"]
    )


    x=bbox["max_x"]+dimension_offset

    y1=bbox["min_y"]
    y2=bbox["max_y"]


    line=Line.CreateBound(
        XYZ(x,y1,view.GenLevel.Elevation),
        XYZ(x,y2,view.GenLevel.Elevation)
    )


    return doc.Create.NewDimension(
        view,
        line,
        reference_array
    )


# ---------------------------------------------------------
# Place Dimensions
# ---------------------------------------------------------

def place_dimensions():
    # Analyze rooms and prepare dimension data.

    dimensions_to_create=[]
    rooms_with_errors=0


    # -----------------------------------------------------
    # Analysis only - no transaction
    # -----------------------------------------------------

    for room in rooms:

        try:

            boundary_loops=room.GetBoundarySegments(
                boundary_options
            )

            if boundary_loops is None:
                continue


            bbox=get_2d_bounding_box(
                boundary_loops
            )

            if bbox is None:
                continue


            boundaries=get_boundary_references(
                boundary_loops
            )


            extremes=get_extreme_references(
                boundaries,
                bbox
            )


            # Store X dimension data.

            if (
                extremes["min_x"] is not None
                and extremes["max_x"] is not None
            ):

                dimensions_to_create.append(
                    (
                        "X",
                        extremes["min_x"],
                        extremes["max_x"],
                        bbox
                    )
                )


            # Store Y dimension data.

            if (
                extremes["min_y"] is not None
                and extremes["max_y"] is not None
            ):

                dimensions_to_create.append(
                    (
                        "Y",
                        extremes["min_y"],
                        extremes["max_y"],
                        bbox
                    )
                )


        except Exception as ex:

            rooms_with_errors+=1

            print(
                "ROOM {} ERROR: {}".format(
                    room.Id,
                    ex
                )
            )


    # -----------------------------------------------------
    # Placement only - transaction
    # -----------------------------------------------------

    dimensions_created=0

    with revit.Transaction(
        "Room Dimensions"
    ):

        for dimension_data in dimensions_to_create:

            axis=dimension_data[0]
            min_ref=dimension_data[1]
            max_ref=dimension_data[2]
            bbox=dimension_data[3]


            if axis=="X":

                dimension=create_x_dimension(
                    min_ref,
                    max_ref,
                    bbox
                )

            else:

                dimension=create_y_dimension(
                    min_ref,
                    max_ref,
                    bbox
                )


            if dimension is not None:
                dimensions_created+=1


    print(
        "Dimensions created: {}".format(
            dimensions_created
        )
    )

    print(
        "Rooms with errors: {}".format(
            rooms_with_errors
        )
    )