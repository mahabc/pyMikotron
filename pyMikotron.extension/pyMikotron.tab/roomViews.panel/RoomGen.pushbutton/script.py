from pyrevit import revit, script
from Autodesk.Revit.DB import *


doc = revit.doc


def create_room_views():

    rooms = (
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Rooms)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    # Find Floor Plan ViewFamilyType
    view_type = None

    for vft in FilteredElementCollector(doc).OfClass(ViewFamilyType):
        if vft.ViewFamily == ViewFamily.FloorPlan:
            view_type = vft
            break

    if not view_type:
        print("No Floor Plan ViewFamilyType found.")
        return

    # Existing view names
    existing_names = set()

    for v in FilteredElementCollector(doc).OfClass(View):
        try:
            existing_names.add(v.Name)
        except:
            pass

    created = 0
    skipped = 0
    errors = 0

    with revit.Transaction("Create Room Views"):

        for room in rooms:

            if room.Area <= 0:
                skipped += 1
                continue

            # Get the level belonging to THIS room
            level = room.Level

            if not level:
                skipped += 1
                print(
                    "SKIPPED | Room {} | No level".format(
                        room.Number
                    )
                )
                continue

            room_number = room.Number

            # Get room name using LookupParameter
            name_param = room.LookupParameter("Name")
            room_name = name_param.AsString() if name_param else ""

            view_name = "Room Plan {} - {}".format(
                room_number,
                room_name
            )

            if view_name in existing_names:
                skipped += 1
                continue

            try:

                # Create plan using THIS ROOM'S LEVEL
                view = ViewPlan.Create(
                    doc,
                    view_type.Id,
                    level.Id
                )

                view.Name = view_name

                # Room bounding box
                bbox = room.get_BoundingBox(None)

                if bbox:

                    offset = UnitUtils.ConvertToInternalUnits(
                        300,
                        UnitTypeId.Millimeters
                    )

                    crop = BoundingBoxXYZ()

                    crop.Min = XYZ(
                        bbox.Min.X - offset,
                        bbox.Min.Y - offset,
                        bbox.Min.Z
                    )

                    crop.Max = XYZ(
                        bbox.Max.X + offset,
                        bbox.Max.Y + offset,
                        bbox.Max.Z
                    )

                    view.CropBox = crop
                    view.CropBoxActive = True
                    view.CropBoxVisible = True

                existing_names.add(view_name)
                created += 1

                print(
                    "CREATED | {} | Level: {}".format(
                        view_name,
                        level.Name
                    )
                )

            except Exception as e:

                errors += 1

                print(
                    "ERROR | Room {} | Level {} | {}".format(
                        room_number,
                        level.Name,
                        str(e)
                    )
                )

    print("Views created: {}".format(created))
    print("Rooms skipped: {}".format(skipped))
    print("Errors: {}".format(errors))


create_room_views()