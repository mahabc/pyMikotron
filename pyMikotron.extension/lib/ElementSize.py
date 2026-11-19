# -*- coding: utf-8 -*-
"""Write installation sizes to the Element_Size shared parameter (active view).

Units: asked at start - Inches or Millimeters. Sizes are read from each element's
connectors (internal units), so no unit detection on the Size string is needed.

Format per connector end: round = diameter, rectangular/oval = width x height.
Ends are joined with '-' (150-100 -> 6"-4"); if all ends are equal one size is
written (100-100 -> 4"). The suffix entered at start is put after every number
(inches default '"', millimeters default none).

Inches:
  - Pipes and conduits: standard sizes only (from their matrix); non-standard sizes
    are skipped and reported, never calculated.
  - Ducts and cable trays: matrix first, otherwise calculated to whole inches.
Millimeters: rounded to whole mm.

Taps (pipe fittings whose type has Element_Type_Function = Tap) get
'host size x tap size', e.g. 2"x1/2": host = the larger connected element,
tap = the tap's own (smallest) connector.

TODO: pipe 90 mm is treated as steel DN90 (3 1/2"). PVC OD sizes (63/75/90 mm)
may need a material-aware lookup (e.g. via Element_Type_Material) later.
"""
from pyrevit import revit, script, forms
from Autodesk.Revit.DB import (BuiltInCategory, ConnectorProfileType, ConnectorType,
                               ElementMulticategoryFilter, FilteredElementCollector, MEPSystem,
                               StorageType)
from System.Collections.Generic import List

from general.helpers import ft_to_mm, id_value, type_param_text

TARGET_PARAM = "Element_Size"
TAP_PARAM, TAP_VALUE = "Element_Type_Function", "Tap"
INCHES, MILLIMETERS = "Inches", "Millimeters"

# Steel pipe DN (mm) -> nominal inch size. Also used as first lookup for ducts/trays.
PIPE_MATRIX = {
    6: '1/8"', 8: '1/4"', 10: '3/8"', 15: '1/2"', 20: '3/4"', 25: '1"',
    32: '1 1/4"', 40: '1 1/2"', 50: '2"', 65: '2 1/2"', 80: '3"', 90: '3 1/2"',
    100: '4"', 110: '4"', 125: '5"', 150: '6"', 160: '6"', 200: '8"',
    250: '10"', 300: '12"', 350: '14"', 400: '16"', 450: '18"', 500: '20"',
    550: '22"', 600: '24"', 650: '26"', 700: '28"', 750: '30"', 800: '32"',
    850: '34"', 900: '36"', 1000: '40"', 1050: '42"', 1100: '44"', 1200: '48"',
    1300: '52"', 1400: '56"', 1500: '60"', 1600: '64"', 1700: '68"', 1800: '72"',
    1900: '76"', 2000: '80"', 2100: '84"', 2200: '88"', 2300: '92"', 2400: '96"',
    2500: '100"',
}

# PVC conduit OD (mm) -> nominal inch size. TODO: verify against project conduit types.
CONDUIT_MATRIX = {
    20: '1/2"', 25: '3/4"', 32: '1"', 40: '1 1/4"', 50: '1 1/2"', 63: '2"',
    75: '2 1/2"', 90: '3"', 110: '4"', 140: '5"', 160: '6"', 200: '8"',
    250: '10"', 315: '12"',
}

# category -> (size matrix, fallback denominator); denominator None = standard sizes only
CAT_INFO = {
    BuiltInCategory.OST_PipeCurves:       (PIPE_MATRIX,    None),
    BuiltInCategory.OST_PipeFitting:      (PIPE_MATRIX,    None),
    BuiltInCategory.OST_PipeAccessory:    (PIPE_MATRIX,    None),
    BuiltInCategory.OST_FlexPipeCurves:   (PIPE_MATRIX,    None),
    BuiltInCategory.OST_DuctCurves:       (PIPE_MATRIX,    1),
    BuiltInCategory.OST_DuctFitting:      (PIPE_MATRIX,    1),
    BuiltInCategory.OST_DuctAccessory:    (PIPE_MATRIX,    1),
    BuiltInCategory.OST_DuctTerminal:     (PIPE_MATRIX,    1),
    BuiltInCategory.OST_FlexDuctCurves:   (PIPE_MATRIX,    1),
    BuiltInCategory.OST_CableTray:        (PIPE_MATRIX,    1),
    BuiltInCategory.OST_CableTrayFitting: (PIPE_MATRIX,    1),
    BuiltInCategory.OST_Conduit:          (CONDUIT_MATRIX, None),
    BuiltInCategory.OST_ConduitFitting:   (CONDUIT_MATRIX, None),
}

INSULATION_CATS = (int(BuiltInCategory.OST_PipeInsulations), int(BuiltInCategory.OST_DuctInsulations),
                   int(BuiltInCategory.OST_DuctLinings))


# ---------------------------------------------------------
# Number formatting
# ---------------------------------------------------------
def _gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def format_inches(inches, denom):
    """6.875 -> 6 7/8 ; 0.5 -> 1/2 ; 7.0 -> 7 (denom=1 -> whole inches). No unit symbol."""
    units = int(round(inches * denom))
    whole, rem = divmod(units, denom)
    if rem == 0:
        return '{}'.format(whole)
    g = _gcd(rem, denom)
    frac = '{}/{}'.format(rem // g, denom // g)
    return '{} {}'.format(whole, frac) if whole else frac


def dim_label(mm, mode, matrix, denom):
    """One dimension in mm -> text without unit symbol, or None if not a standard size."""
    if mode == MILLIMETERS:
        return '{}'.format(int(round(mm)))
    key = int(round(mm))
    if key in matrix:
        return matrix[key].rstrip('"')
    return format_inches(mm / 25.4, denom) if denom else None


# ---------------------------------------------------------
# Connectors
# ---------------------------------------------------------
def connectors(element):
    manager = getattr(element, "ConnectorManager", None)
    if manager is None:
        mep = getattr(element, "MEPModel", None)
        manager = mep.ConnectorManager if mep is not None else None
    return list(manager.Connectors) if manager is not None else []


def end_connectors(element):
    return [c for c in connectors(element) if c.ConnectorType == ConnectorType.End]


def connector_dims_mm(connector):
    if connector.Shape == ConnectorProfileType.Round:
        return [ft_to_mm(connector.Radius * 2.0)]
    return [ft_to_mm(connector.Width), ft_to_mm(connector.Height)]


def largest_round_mm(element):
    sizes = [ft_to_mm(c.Radius * 2.0) for c in end_connectors(element)
             if c.Shape == ConnectorProfileType.Round]
    return max(sizes) if sizes else None


def connected_elements(element):
    found, seen = [], set([id_value(element.Id)])
    for c in connectors(element):
        for ref in c.AllRefs:
            owner = ref.Owner
            if owner is None or isinstance(owner, MEPSystem) or id_value(owner.Id) in seen:
                continue
            if owner.Category is not None and id_value(owner.Category.Id) in INSULATION_CATS:
                continue
            seen.add(id_value(owner.Id))
            found.append(owner)
    return found


# ---------------------------------------------------------
# Size text
# ---------------------------------------------------------
def element_size(element, mode, matrix, denom, suffix):
    """Returns (text, error) for a normal MEP element."""
    ends = end_connectors(element)
    if not ends:
        return None, "no connectors"
    labels = []
    for c in ends:
        dims = connector_dims_mm(c)
        parts = [dim_label(d, mode, matrix, denom) for d in dims]
        if None in parts:
            return None, "non-standard size: {}".format(
                "x".join('{:g} mm'.format(round(d, 1)) for d in dims))
        labels.append("x".join(p + suffix for p in parts))
    if len(set(labels)) == 1:
        return labels[0], None
    return "-".join(labels), None


def tap_size(doc, tap, mode, suffix):
    """Returns ('host x tap', error) for a tap fitting."""
    own = [ft_to_mm(c.Radius * 2.0) for c in end_connectors(tap)
           if c.Shape == ConnectorProfileType.Round]
    if not own:
        return None, "tap without round connectors"
    hosts = [(largest_round_mm(e), e) for e in connected_elements(tap)]
    hosts = [h for h in hosts if h[0] is not None]
    if not hosts:
        return None, "tap: no connected host"
    host_mm = max(hosts, key=lambda h: h[0])[0]
    host = dim_label(host_mm, mode, PIPE_MATRIX, None)
    own_label = dim_label(min(own), mode, PIPE_MATRIX, None)
    if host is None or own_label is None:
        return None, "tap: non-standard size ({:g} x {:g} mm)".format(round(host_mm, 1), round(min(own), 1))
    return "{}{}x{}{}".format(host, suffix, own_label, suffix), None


# ---------------------------------------------------------
# Dialogs
# ---------------------------------------------------------
def ask_mode_and_suffix():
    mode = forms.CommandSwitchWindow.show([INCHES, MILLIMETERS], message="Element_Size units")
    if not mode:
        script.exit()
    suffix = forms.ask_for_string(
        default='"' if mode == INCHES else '',
        prompt='Size suffix after each number (leave empty for none):',
        title='Element_Size')
    if suffix is None:
        script.exit()
    return mode, suffix.strip()


def main():
    doc = revit.doc
    view = doc.ActiveView
    output = script.get_output()

    mode, suffix = ask_mode_and_suffix()
    cat_filter = ElementMulticategoryFilter(List[BuiltInCategory](list(CAT_INFO.keys())))
    elements = (FilteredElementCollector(doc, view.Id)
                .WherePasses(cat_filter)
                .WhereElementIsNotElementType()
                .ToElements())

    updated, taps, skipped = 0, 0, []
    with revit.Transaction("Set Element_Size"):
        for e in elements:
            target = e.LookupParameter(TARGET_PARAM)
            if not target or target.IsReadOnly or target.StorageType != StorageType.String:
                skipped.append((e.Id, "no writable " + TARGET_PARAM))
                continue
            is_tap = (e.Category.BuiltInCategory == BuiltInCategory.OST_PipeFitting
                      and type_param_text(doc, e, TAP_PARAM) == TAP_VALUE)
            if is_tap:
                value, error = tap_size(doc, e, mode, suffix)
            else:
                matrix, denom = CAT_INFO[e.Category.BuiltInCategory]
                value, error = element_size(e, mode, matrix, denom, suffix)
            if value:
                target.Set(value)
                updated += 1
                taps += 1 if is_tap else 0
            else:
                skipped.append((e.Id, error))

    output.print_md("**Units:** {}  |  **Updated:** {} (taps: {})  |  **Skipped:** {}".format(
        mode, updated, taps, len(skipped)))
    for eid, reason in skipped:
        output.print_md(u"{} — {}".format(output.linkify(eid), reason))
