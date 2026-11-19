# -*- coding: utf-8 -*-
"""Iso 03 - create isometric views, filters and sheet per iso group (step 3 of 3).

For every iso group you pick (model elements of any category with the iso parameter,
default PIP_IsoGroup, equal to the group value):

Views (the ones you tick), cropped to the group's extents + 10":
    ISO_<value>_AA Section (Front)     ISO_<value>_BB Section (Left)
    ISO_<value>_CC Section (Back)      ISO_<value>_DD Section (Right)
    ISO_<value>_Plan View              ISO_<value>_Location View
    ISO_<value>_3D View
  (an existing name gets ' (1)', ' (2)'... added)

View filters (reused if they already exist), added to every created view and hidden:
    Isometrics_Filter_<value>           iso parameter <> value on the element categories
    Isometrics_Sections_Filter_<value>  iso parameter <> value on Sections and Callouts

Sheet:
    number ISO_<value>, name "Isometrics Layout", title block you pick
    <iso parameter> = value, 01_Organisation = A10_DELIVERY, 02_UserType = P9_Isometrics
    created views placed in a grid, schedules with <iso parameter> = value stacked bottom-left

Prerequisites: view types with the isometric view templates, schedules from Iso 01 / Iso 02.
"""
import math

from pyrevit import forms, revit, script
from Autodesk.Revit.DB import (BoundingBoxXYZ, BuiltInCategory, ElementId, ElementParameterFilter,
                               FamilySymbol, FilteredElementCollector, Level, ParameterElement,
                               ParameterFilterElement, ParameterFilterRuleFactory,
                               ParameterFilterUtilities, ScheduleSheetInstance, StorageType,
                               Transaction, TransactionGroup, Transform, View, View3D,
                               ViewFamily, ViewFamilyType, ViewPlan, ViewSchedule, ViewSection,
                               ViewSheet, Viewport, XYZ)
from System.Collections.Generic import List

from general.helpers import element_name, id_value, param_text, set_param
from general.iso import ask_param_and_groups
from general import ui

TITLE = "Iso 03 - Views & Sheet"
OFFSET_FT = 10.0 / 12.0                       # 10 inches around the group
SHEET_NAME = "Isometrics Layout"
SHEET_PARAMS = [("01_Organisation", "A10_DELIVERY"), ("02_UserType", "P9_Isometrics")]
FILTER_PREFIX = "Isometrics_Filter"
SECTIONS_FILTER_PREFIX = "Isometrics_Sections_Filter"

ELEMENT_FILTER_CATS = [BuiltInCategory.OST_PipeCurves, BuiltInCategory.OST_PipeFitting,
                       BuiltInCategory.OST_PipeAccessory, BuiltInCategory.OST_StructuralFraming,
                       BuiltInCategory.OST_StructConnections]
SECTIONS_FILTER_CATS = [BuiltInCategory.OST_Sections, BuiltInCategory.OST_Callouts]

# label, kind, section view direction (BasisZ of the section box)
VIEWS = [
    ("AA Section (Front)", "section", XYZ(0, 1, 0)),
    ("BB Section (Left)",  "section", XYZ(1, 0, 0)),
    ("CC Section (Back)",  "section", XYZ(0, -1, 0)),
    ("DD Section (Right)", "section", XYZ(-1, 0, 0)),
    ("Plan View",          "plan",     None),
    ("Location View",      "location", None),
    ("3D View",            "3d",       None),
]

# kind -> (ViewFamily, default type name, prompt)
VIEW_TYPES = {
    "section":  (ViewFamily.Section,          "Isometrics Building Section", "Section view type"),
    "plan":     (ViewFamily.FloorPlan,        "Isometrics Floor Plan",       "Plan view type"),
    "location": (ViewFamily.FloorPlan,        "Location Plan",               "Location plan view type"),
    "3d":       (ViewFamily.ThreeDimensional, "Isometrics 3D View",          "3D view type"),
}


# ---------------------------------------------------------
# Dialogs
# ---------------------------------------------------------
def first_sorted(names, preferred):
    """Sorted names with the preferred one first (the list cannot preselect)."""
    names = sorted(names)
    if preferred in names:
        names.remove(preferred)
        names.insert(0, preferred)
    return names


def ask_view_types(doc, kinds):
    all_types = list(FilteredElementCollector(doc).OfClass(ViewFamilyType))
    picked = {}
    for kind in ["section", "plan", "location", "3d"]:
        if kind not in kinds:
            continue
        family, default, prompt = VIEW_TYPES[kind]
        by_name = dict((element_name(t), t) for t in all_types if t.ViewFamily == family)
        if not by_name:
            forms.alert("No {} view types in this model.".format(prompt.lower()), title=TITLE, exitscript=True)
        key = "type_" + kind
        name = ui.pick_one(first_sorted(by_name.keys(), ui.recall(key, default)), prompt)
        ui.remember(**{key: name})
        picked[kind] = by_name[name]
    return picked


def ask_titleblock(doc):
    blocks = dict(("{}: {}".format(s.FamilyName, element_name(s)), s) for s in
                  FilteredElementCollector(doc).OfClass(FamilySymbol)
                  .OfCategory(BuiltInCategory.OST_TitleBlocks))
    if not blocks:
        forms.alert("No title blocks loaded.", title=TITLE, exitscript=True)
    name = ui.pick_one(first_sorted(blocks.keys(), ui.recall("titleblock", "TITLEBLOCK_TEMPLATE: Template")),
                       "Title block for the sheets")
    ui.remember(titleblock=name)
    return blocks[name]


# ---------------------------------------------------------
# Geometry
# ---------------------------------------------------------
def extents(elements):
    boxes = [b for b in (e.get_BoundingBox(None) for e in elements) if b is not None]
    if not boxes:
        return None
    o = OFFSET_FT
    return (XYZ(min(b.Min.X for b in boxes) - o, min(b.Min.Y for b in boxes) - o, min(b.Min.Z for b in boxes) - o),
            XYZ(max(b.Max.X for b in boxes) + o, max(b.Max.Y for b in boxes) + o, max(b.Max.Z for b in boxes) + o))


def world_box(lo, hi):
    box = BoundingBoxXYZ()
    box.Min, box.Max = lo, hi
    return box


def section_box(lo, hi, basis_z):
    """Same box as the Dynamo graph: centred on the group, cut plane at the centre,
    far clip at the group's depth along the view direction."""
    basis_y = XYZ(0, 0, 1)
    basis_x = basis_y.CrossProduct(basis_z)
    span = hi - lo
    width = abs(span.DotProduct(basis_x))
    depth = abs(span.DotProduct(basis_z))
    height = span.Z
    t = Transform.Identity
    t.Origin = (lo + hi) / 2.0
    t.BasisX, t.BasisY, t.BasisZ = basis_x, basis_y, basis_z
    box = BoundingBoxXYZ()
    box.Transform = t
    box.Min = XYZ(-width / 2.0, -height / 2.0, 0.0)
    box.Max = XYZ(width / 2.0, height / 2.0, depth)
    return box


def lowest_level(doc, elements, z_hint):
    levels = [doc.GetElement(e.LevelId) for e in elements if e.LevelId != ElementId.InvalidElementId]
    levels = [l for l in levels if isinstance(l, Level)]
    if levels:
        return min(levels, key=lambda l: l.Elevation)
    all_levels = list(FilteredElementCollector(doc).OfClass(Level))
    return min(all_levels, key=lambda l: abs(l.Elevation - z_hint)) if all_levels else None


# ---------------------------------------------------------
# Views
# ---------------------------------------------------------
class Names(object):
    def __init__(self, doc):
        self.used = set(v.Name for v in FilteredElementCollector(doc).OfClass(View))

    def unique(self, base):
        name, i = base, 1
        while name in self.used:
            name = "{} ({})".format(base, i)
            i += 1
        self.used.add(name)
        return name


def create_view(doc, kind, basis_z, vtype, elements, lo, hi):
    if kind == "section":
        return ViewSection.CreateSection(doc, vtype.Id, section_box(lo, hi, basis_z))
    if kind == "3d":
        view = View3D.CreateIsometric(doc, vtype.Id)
        view.SetSectionBox(world_box(lo, hi))
        return view
    level = lowest_level(doc, elements, (lo.Z + hi.Z) / 2.0)
    if level is None:
        raise Exception("no level found")
    view = ViewPlan.Create(doc, vtype.Id, level.Id)
    view.CropBox = world_box(lo, hi)
    view.CropBoxActive = True
    view.CropBoxVisible = True
    return view


# ---------------------------------------------------------
# Filters
# ---------------------------------------------------------
def parameter_id(doc, name):
    for pe in FilteredElementCollector(doc).OfClass(ParameterElement):
        definition = pe.GetDefinition()
        if definition is not None and definition.Name == name:
            return pe.Id
    return None


def not_equals_rule(param_id, value, storage):
    if storage == StorageType.Integer:
        return ParameterFilterRuleFactory.CreateNotEqualsRule(param_id, int(value))
    if storage == StorageType.Double:
        return ParameterFilterRuleFactory.CreateNotEqualsRule(param_id, float(value), 1e-6)
    try:
        return ParameterFilterRuleFactory.CreateNotEqualsRule(param_id, value)
    except TypeError:
        return ParameterFilterRuleFactory.CreateNotEqualsRule(param_id, value, False)


def filterable_categories(doc, cat_ids, param_id):
    ok = List[ElementId]()
    filterable = set(id_value(c) for c in ParameterFilterUtilities.GetAllFilterableCategories())
    for cid in cat_ids:
        if id_value(cid) not in filterable:
            continue
        common = ParameterFilterUtilities.GetFilterableParametersInCommon(doc, List[ElementId]([cid]))
        if any(id_value(p) == id_value(param_id) for p in common):
            ok.Add(cid)
    return ok


def get_or_create_filter(doc, name, cat_ids, param_id, value, storage, notes):
    for f in FilteredElementCollector(doc).OfClass(ParameterFilterElement):
        if f.Name == name:
            return f
    cats = filterable_categories(doc, cat_ids, param_id)
    if cats.Count == 0:
        notes.append("{}: no category accepts the iso parameter - filter not created".format(name))
        return None
    rule_filter = ElementParameterFilter(not_equals_rule(param_id, value, storage))
    return ParameterFilterElement.Create(doc, name, cats, rule_filter)


def apply_filters(views, filters, notes):
    for view in views:
        for f in filters:
            try:
                if not view.IsFilterApplied(f.Id):
                    view.AddFilter(f.Id)
                view.SetFilterVisibility(f.Id, False)
            except Exception as ex:
                notes.append("{} on {}: {}".format(f.Name, view.Name, ex))


# ---------------------------------------------------------
# Sheet
# ---------------------------------------------------------
def create_sheet(doc, titleblock, param_name, value, notes):
    sheet = ViewSheet.Create(doc, titleblock.Id)
    number = "ISO_{}".format(value)
    try:
        sheet.SheetNumber = number
    except Exception:
        notes.append("sheet number '{}' already used - kept {}".format(number, sheet.SheetNumber))
    sheet.Name = SHEET_NAME
    set_param(sheet, param_name, value)
    for pname, pvalue in SHEET_PARAMS:
        set_param(sheet, pname, pvalue)
    return sheet


def place_on_sheet(doc, sheet, views, schedules, notes):
    outline = sheet.Outline
    min_u, min_v, max_u, max_v = outline.Min.U, outline.Min.V, outline.Max.U, outline.Max.V
    if views:
        cols = int(math.ceil(math.sqrt(len(views))))
        rows = int(math.ceil(len(views) / float(cols)))
        w, h = (max_u - min_u) / cols, (max_v - min_v) / rows
        for i, view in enumerate(views):
            r, c = divmod(i, cols)
            point = XYZ(min_u + (c + 0.5) * w, max_v - (r + 0.5) * h, 0)
            if Viewport.CanAddViewToSheet(doc, sheet.Id, view.Id):
                Viewport.Create(doc, sheet.Id, view.Id, point)
            else:
                notes.append("{} could not be placed on the sheet".format(view.Name))
    for i, schedule in enumerate(schedules):
        ScheduleSheetInstance.Create(doc, sheet.Id, schedule.Id, XYZ(min_u + 0.1, min_v + 0.1 + i * 0.3, 0))


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------
def process_group(doc, value, elements, param_name, param_id, picked_views, view_types,
                  titleblock, names, notes):
    bounds = extents(elements)
    if bounds is None:
        notes.append("no element extents")
        return []
    lo, hi = bounds
    storage = elements[0].LookupParameter(param_name).StorageType

    created = []
    for label, kind, basis_z in VIEWS:
        if label not in picked_views:
            continue
        try:
            view = create_view(doc, kind, basis_z, view_types[kind], elements, lo, hi)
            view.Name = names.unique("ISO_{}_{}".format(value, label))
            created.append(view)
        except Exception as ex:
            notes.append("{}: {}".format(label, ex))

    group_cats = []
    for e in elements:
        if all(id_value(e.Category.Id) != id_value(c) for c in group_cats):
            group_cats.append(e.Category.Id)
    element_cats = [ElementId(b) for b in ELEMENT_FILTER_CATS]
    element_cats += [c for c in group_cats if all(id_value(c) != id_value(x) for x in element_cats)]
    filters = [f for f in (
        get_or_create_filter(doc, "{}_{}".format(FILTER_PREFIX, value), element_cats,
                             param_id, value, storage, notes),
        get_or_create_filter(doc, "{}_{}".format(SECTIONS_FILTER_PREFIX, value),
                             [ElementId(b) for b in SECTIONS_FILTER_CATS],
                             param_id, value, storage, notes)) if f is not None]
    apply_filters(created, filters, notes)

    if not titleblock.IsActive:
        titleblock.Activate()
    sheet = create_sheet(doc, titleblock, param_name, value, notes)
    doc.Regenerate()
    schedules = [s for s in FilteredElementCollector(doc).OfClass(ViewSchedule)
                 if not s.IsTemplate and param_text(s.LookupParameter(param_name)) == value]
    place_on_sheet(doc, sheet, created, schedules, notes)
    return [sheet] + created


def main():
    doc = revit.doc
    output = script.get_output()

    param_name, groups = ask_param_and_groups(doc, TITLE)
    param_id = parameter_id(doc, param_name)
    if param_id is None:
        forms.alert("'{}' is not a project or shared parameter, so view filters "
                    "cannot use it.".format(param_name), title=TITLE, exitscript=True)
    picked_views = ui.pick_many([v[0] for v in VIEWS], "Views to create", "Create")
    view_types = ask_view_types(doc, set(k for label, k, _ in VIEWS if label in picked_views))
    titleblock = ask_titleblock(doc)

    names = Names(doc)
    results = []
    group = TransactionGroup(doc, "Iso 03 - Views & Sheets")
    group.Start()
    for value, elements in groups.items():
        notes = []
        t = Transaction(doc, "Iso 03 - {}".format(value))
        t.Start()
        try:
            made = process_group(doc, value, elements, param_name, param_id, picked_views,
                                 view_types, titleblock, names, notes)
            t.Commit()
        except Exception as ex:
            t.RollBack()
            made, notes = [], notes + ["FAILED, nothing created: {}".format(ex)]
        results.append((value, made, notes))
    group.Assimilate()

    output.print_md("## " + TITLE)
    for value, made, notes in results:
        output.print_md("### {} ({} elements)".format(value, len(groups[value])))
        for v in made:
            output.print_md("- {} {}".format(output.linkify(v.Id), v.Name if not isinstance(v, ViewSheet)
                                             else "Sheet {} - {}".format(v.SheetNumber, v.Name)))
        for n in notes:
            output.print_md("- **Note:** {}".format(n))
