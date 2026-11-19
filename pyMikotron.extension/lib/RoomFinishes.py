# -*- coding: utf-8 -*-
"""Room Finishes - finish floors, ceilings and walls from room finish parameters.

Rooms come from the local model or one loaded link (its position is applied) and can be
filtered by a parameter value (e.g. Comments = DO). Per room:
  - Floor Finish   -> floor of that type on the room outline, top at level + floor thickness
  - Ceiling Finish -> ceiling of that type on the room outline, at room height - ceiling thickness
  - Wall Finish    -> wall of that type along every boundary segment, offset half its width
                      into the room, room height tall, not room-bounding
Finish values are matched to type names in the local model; rooms whose finish has no
matching type are reported. Structural columns already shape the room boundary, so the
wall finishes wrap around them.
"""
from pyrevit import forms, revit, script
from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter, Ceiling, CeilingType, CurveLoop,
                               FilteredElementCollector, Floor, FloorType, Level,
                               SpatialElementBoundaryLocation, SpatialElementBoundaryOptions,
                               Wall, WallKind, WallType, XYZ)
from System.Collections.Generic import List

from general.helpers import element_name, param_text
from general import ui

TITLE = "Room Finishes"


def types_by_name(doc, cls):
    return dict((element_name(t), t) for t in FilteredElementCollector(doc).OfClass(cls))


def double_param(element, bip, default=0.0):
    p = element.get_Parameter(bip)
    return p.AsDouble() if p is not None and p.HasValue else default


class LevelMatcher(object):
    """Maps a room's level (local or linked) to a local level plus an offset."""

    def __init__(self, doc):
        self.levels = list(FilteredElementCollector(doc).OfClass(Level))

    def match(self, room, src):
        if not src.is_link:
            return room.LevelId, 0.0
        link_level = src.doc.GetElement(room.LevelId)
        z = src.transform.OfPoint(XYZ(0, 0, link_level.ProjectElevation)).Z
        host = min(self.levels, key=lambda l: abs(l.ProjectElevation - z))
        return host.Id, z - host.ProjectElevation


def boundary(room, src, options):
    """List of boundary loops (lists of curves) in local coordinates."""
    loops = []
    for seg_loop in room.GetBoundarySegments(options) or []:
        curves = [s.GetCurve() for s in seg_loop]
        if src.is_link:
            curves = [c.CreateTransformed(src.transform) for c in curves]
        if curves:
            loops.append(curves)
    return loops


def curve_loops(loops):
    result = List[CurveLoop]()
    for curves in loops:
        loop = CurveLoop()
        for c in curves:
            loop.Append(c)
        result.Add(loop)
    return result


def make_floor(doc, loops, ftype, level_id, offset):
    floor = Floor.Create(doc, curve_loops(loops), ftype.Id, level_id)
    thickness = double_param(ftype, BuiltInParameter.FLOOR_ATTR_DEFAULT_THICKNESS_PARAM)
    floor.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM).Set(offset + thickness)
    return floor


def make_ceiling(doc, loops, ctype, level_id, offset, height):
    ceiling = Ceiling.Create(doc, curve_loops(loops), ctype.Id, level_id)
    thickness = double_param(ctype, BuiltInParameter.CEILING_THICKNESS)
    ceiling.get_Parameter(BuiltInParameter.CEILING_HEIGHTABOVELEVEL_PARAM).Set(offset + height - thickness)
    return ceiling


def make_walls(doc, loops, wtype, level_id, offset, height, errors, room_label):
    walls = []
    half = wtype.Width / 2.0
    for curves in loops:
        for curve in curves:
            try:
                wall = Wall.Create(doc, curve.CreateOffset(-half, XYZ.BasisZ), wtype.Id, level_id,
                                   height, offset, False, False)
                wall.get_Parameter(BuiltInParameter.WALL_ATTR_ROOM_BOUNDING).Set(0)
                walls.append(wall)
            except Exception as ex:
                errors.append((room_label, "wall segment", str(ex)))
    return walls


def main():
    doc = revit.doc
    output = script.get_output()

    src = ui.pick_sources(doc, "Rooms from", multiselect=False)[0]
    filter_param = ui.ask_text("Filter rooms by parameter (leave empty for all rooms):",
                               TITLE, ui.recall("filter_param", "Comments"))
    filter_value = ""
    if filter_param:
        filter_value = ui.ask_text("Value of '{}':".format(filter_param), TITLE,
                                   ui.recall("filter_value", "DO"))
    ui.remember(filter_param=filter_param, filter_value=filter_value)

    rooms = [r for r in FilteredElementCollector(src.doc).OfCategory(BuiltInCategory.OST_Rooms)
             .WhereElementIsNotElementType()
             if r.Area > 0 and (not filter_param
                                or param_text(r.LookupParameter(filter_param)) == filter_value)]
    if not rooms:
        forms.alert("No placed rooms match the filter.", title=TITLE, exitscript=True)

    floor_types = types_by_name(doc, FloorType)
    ceiling_types = types_by_name(doc, CeilingType)
    wall_types = dict((n, t) for n, t in types_by_name(doc, WallType).items() if t.Kind == WallKind.Basic)

    options = SpatialElementBoundaryOptions()
    options.SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish
    levels = LevelMatcher(doc)

    counts = {"floors": 0, "ceilings": 0, "walls": 0}
    missing, errors = [], []
    with revit.Transaction("Room Finishes"):
        for room in rooms:
            label = u"{} {}".format(room.Number, param_text(room.get_Parameter(BuiltInParameter.ROOM_NAME)))
            try:
                loops = boundary(room, src, options)
                level_id, offset = levels.match(room, src)
            except Exception as ex:
                errors.append((label, "boundary / level", str(ex)))
                continue
            if not loops:
                errors.append((label, "boundary", "room has no boundary"))
                continue
            height = double_param(room, BuiltInParameter.ROOM_HEIGHT)

            for kind, bip, types in (("floor", BuiltInParameter.ROOM_FINISH_FLOOR, floor_types),
                                     ("ceiling", BuiltInParameter.ROOM_FINISH_CEILING, ceiling_types),
                                     ("wall", BuiltInParameter.ROOM_FINISH_WALL, wall_types)):
                finish = param_text(room.get_Parameter(bip))
                if not finish:
                    continue
                ftype = types.get(finish)
                if ftype is None:
                    missing.append((label, kind, finish))
                    continue
                try:
                    if kind == "floor":
                        make_floor(doc, loops, ftype, level_id, offset)
                        counts["floors"] += 1
                    elif kind == "ceiling":
                        make_ceiling(doc, loops, ftype, level_id, offset, height)
                        counts["ceilings"] += 1
                    else:
                        counts["walls"] += len(make_walls(doc, loops, ftype, level_id, offset,
                                                          height, errors, label))
                except Exception as ex:
                    errors.append((label, kind, str(ex)))

    output.print_md("## " + TITLE)
    output.print_md("Rooms from **{}**: {} | **Floors:** {} | **Ceilings:** {} | **Walls:** {}".format(
        src.name, len(rooms), counts["floors"], counts["ceilings"], counts["walls"]))
    if missing:
        output.print_table([list(m) for m in missing], columns=["Room", "Finish", "No type named"],
                           title="Finish without matching type")
    if errors:
        output.print_table([list(e) for e in errors], columns=["Room", "Step", "Error"], title="Errors")
