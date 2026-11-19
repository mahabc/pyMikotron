# -*- coding: utf-8 -*-
"""Mark Embedded - set PIP_isEmbedded on horizontal pipes and pipe fittings inside floors.

1. PIP_isEmbedded is reset to 0 on all pipes and pipe fittings (accessories are ignored).
2. Pipes count as horizontal when their Slope has a value between 0 and the drop-off
   limit (in project slope units). Vertical pipes have no slope value
   ("Not calculated") and are left at 0.
3. Horizontal pipes and all pipe fittings that intersect a floor get 1. Floors can come
   from the local model and/or loaded links (the link position is applied).
"""
import re

from pyrevit import revit, script
from Autodesk.Revit.DB import (BoundingBoxIntersectsFilter, BuiltInCategory, BuiltInParameter,
                               ElementId, ElementIntersectsSolidFilter, FilteredElementCollector,
                               LabelUtils, Outline, SpecTypeId, StorageType, UnitUtils, XYZ)
from System.Collections.Generic import List

from general.helpers import element_solids, id_value, is_writable
from general import ui

TITLE = "Mark Embedded"
TARGET_PARAM = "PIP_isEmbedded"
DIGIT_RE = re.compile(r"\d")


def collect(doc, bic):
    return list(FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType())


def slope_value(pipe, slope_unit):
    """Slope in project units, or None for vertical pipes (no usable value)."""
    p = pipe.get_Parameter(BuiltInParameter.RBS_PIPE_SLOPE)
    if p is None or not p.HasValue or not DIGIT_RE.search(p.AsValueString() or ""):
        return None
    return UnitUtils.ConvertFromInternalUnits(p.AsDouble(), slope_unit)


def solid_outline(solid):
    """World-aligned outline of a solid (all 8 box corners, so rotated links work)."""
    bb = solid.GetBoundingBox()
    t = bb.Transform
    pts = [t.OfPoint(XYZ(x, y, z)) for x in (bb.Min.X, bb.Max.X)
           for y in (bb.Min.Y, bb.Max.Y) for z in (bb.Min.Z, bb.Max.Z)]
    return Outline(XYZ(min(p.X for p in pts), min(p.Y for p in pts), min(p.Z for p in pts)),
                   XYZ(max(p.X for p in pts), max(p.Y for p in pts), max(p.Z for p in pts)))


def floor_solids(sources):
    solids = []
    for src in sources:
        for floor in collect(src.doc, BuiltInCategory.OST_Floors):
            solids.extend(element_solids(floor, src.transform))
    return solids


def main():
    doc = revit.doc
    output = script.get_output()

    slope_unit = doc.GetUnits().GetFormatOptions(SpecTypeId.Slope).GetUnitTypeId()
    limit = ui.ask_number(
        "Drop-off slope limit ({}).\nPipes with a slope from 0 up to this value count as horizontal:"
        .format(LabelUtils.GetLabelForUnit(slope_unit)),
        TITLE, ui.recall("slope_limit", 100))
    sources = ui.pick_sources(doc, "Floors from (local model and/or links)")
    ui.remember(slope_limit=limit)

    pipes = collect(doc, BuiltInCategory.OST_PipeCurves)
    fittings = collect(doc, BuiltInCategory.OST_PipeFitting)
    horizontal = []
    for pipe in pipes:
        value = slope_value(pipe, slope_unit)
        if value is not None and 0 <= value <= limit:
            horizontal.append(pipe)
    candidates = horizontal + fittings

    solids = floor_solids(sources)
    embedded = set()
    if candidates and solids:
        candidate_ids = List[ElementId]([e.Id for e in candidates])
        for solid in solids:
            hits = (FilteredElementCollector(doc, candidate_ids)
                    .WherePasses(BoundingBoxIntersectsFilter(solid_outline(solid)))
                    .WherePasses(ElementIntersectsSolidFilter(solid))
                    .ToElementIds())
            for eid in hits:
                embedded.add(id_value(eid))

    no_param = []
    with revit.Transaction("Mark " + TARGET_PARAM):
        for e in pipes + fittings:
            p = e.LookupParameter(TARGET_PARAM)
            if not is_writable(p, StorageType.Integer):
                no_param.append(e)
                continue
            p.Set(1 if id_value(e.Id) in embedded else 0)

    output.print_md("## " + TITLE)
    output.print_md("Floors from: {} ({} floor solids)".format(
        ", ".join(s.name for s in sources), len(solids)))
    output.print_md("**Pipes:** {} ({} horizontal) | **Fittings:** {} | **Embedded:** {}".format(
        len(pipes), len(horizontal), len(fittings), len(embedded)))
    if no_param:
        output.print_md("### No writable {} (Yes/No) on {} element(s)".format(TARGET_PARAM, len(no_param)))
        output.print_md(", ".join(output.linkify(e.Id) for e in no_param[:200]))
