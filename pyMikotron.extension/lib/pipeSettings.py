import clr
import os

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Plumbing import PipeSegment, PipeScheduleType

from pyrevit import revit, DB, forms, script

# ---------------------------------------------------------
# Load EPPlus
# ---------------------------------------------------------

lib_path=os.path.dirname(os.path.abspath(__file__))

clr.AddReferenceToFileAndPath(
    os.path.join(lib_path,"EPPlus.dll")
)

from OfficeOpenXml import ExcelPackage
from System.IO import FileInfo
from System.Collections.Generic import List


doc=revit.doc
view=doc.ActiveView


# ---------------------------------------------------------
# Measurement System
# ---------------------------------------------------------

def get_measurement_system():

    measurement_system=forms.SelectFromList.show(
        ["Metric","Feet","Inches"],
        title="Select Measurement System"
    )

    if not measurement_system:
        return None

    return measurement_system


def mm_to_ft(value,measurement_system):

    value=float(value)

    if measurement_system == "Feet":
        return value

    elif measurement_system == "Inches":
        return value / 12.0

    return value / 304.8


# ---------------------------------------------------------
# Excel
# ---------------------------------------------------------

def get_excel_data():

    path=forms.pick_file(
        file_ext="xlsx",
        title="Select Excel File"
    )

    if not path:
        print "No file selected"
        return None

    package=ExcelPackage(FileInfo(path))
    sheets=package.Workbook.Worksheets

    sheet=forms.SelectFromList.show(
        sheets,
        name_attr="Name",
        title="Select Excel Sheet"
    )

    if not sheet:
        package.Dispose()
        print "No sheet selected"
        return None

    print "Selected sheet:",sheet.Name

    rows=sheet.Dimension.End.Row
    data=[]

    for row in range(2,rows+1):

        nominal=sheet.Cells[row,1].Value
        inner=sheet.Cells[row,2].Value
        outer=sheet.Cells[row,3].Value

        if nominal is None:
            continue

        data.append({
            "nominal":float(nominal),
            "inner":float(inner),
            "outer":float(outer)
        })

    segment_name=sheet.Name

    package.Dispose()

    return segment_name,data


# ---------------------------------------------------------
# Material
# ---------------------------------------------------------

def select_material(document):

    materials=(
        FilteredElementCollector(document)
        .OfClass(Material)
        .ToElements()
    )

    names=[]

    for material in materials:
        names.append(material.Name)

    names.sort()

    name=forms.SelectFromList.show(
        names,
        title="Select Material"
    )

    if not name:
        return None

    for material in materials:

        if material.Name == name:
            return material

    return None


# ---------------------------------------------------------
# Pipe Schedule
# ---------------------------------------------------------

def get_schedule(document,name):

    schedules=(
        FilteredElementCollector(document)
        .OfClass(PipeScheduleType)
        .ToElements()
    )

    for schedule in schedules:

        try:
            schedule_name=Element.Name.GetValue(schedule)
        except:
            continue

        if schedule_name == name:
            return schedule

    return None


def get_or_create_schedule(document,name):

    schedule=get_schedule(
        document,
        name
    )

    if schedule:
        return schedule

    return PipeScheduleType.Create(
        document,
        name
    )


# ---------------------------------------------------------
# MEP Sizes
# ---------------------------------------------------------

def create_collection(data,measurement_system):

    sizes=List[MEPSize]()

    for row in data:

        size=MEPSize(
            mm_to_ft(
                row["nominal"],
                measurement_system
            ),
            mm_to_ft(
                row["inner"],
                measurement_system
            ),
            mm_to_ft(
                row["outer"],
                measurement_system
            ),
            True,
            True
        )

        sizes.Add(size)

    return sizes


# ---------------------------------------------------------
# Pipe Segment
# ---------------------------------------------------------

def create_segment(
    document,
    material_id,
    schedule_id,
    sizes,
    segment_name
):

    segment=PipeSegment.Create(
        document,
        material_id,
        schedule_id,
        sizes
    )

    segment.Name=segment_name

    return segment


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def import_pipe_segments():

    print "START import_pipe_segments"

    # Measurement system
    measurement_system=get_measurement_system()

    print "Measurement system:"
    print measurement_system

    if not measurement_system:
        print "No measurement system selected"
        return

    # Excel
    excel_result=get_excel_data()

    if not excel_result:
        print "No Excel data found"
        return

    segment_name,data=excel_result

    print "Segment name:"
    print segment_name

    print "Excel data rows:"
    print len(data)

    if not data:
        print "No Excel data found"
        return

    # Material
    material=select_material(doc)

    if not material:
        print "No material selected"
        return

    print "Material:"
    print material.Name

    # Schedule name
    schedule_name=forms.ask_for_string(
        default="",
        prompt="Enter Pipe Schedule Name",
        title="Pipe Schedule"
    )

    if not schedule_name:
        print "No schedule name entered"
        return

    print "Schedule name:"
    print schedule_name

    # Create sizes
    sizes=create_collection(
        data,
        measurement_system
    )

    print "MEP sizes:"
    print sizes.Count

    # Create schedule if needed and create segment
    with revit.Transaction("Create Pipe Segment"):

        schedule=get_or_create_schedule(
            doc,
            schedule_name
        )

        segment=create_segment(
            doc,
            material.Id,
            schedule.Id,
            sizes,
            segment_name
        )

    print "Created Pipe Segment:"
    print segment.Name

    return segment