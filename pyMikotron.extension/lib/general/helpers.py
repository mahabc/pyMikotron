# -*- coding: utf-8 -*-
"""Shared, tool-independent helpers (parameters, ids, units, geometry)."""
from Autodesk.Revit.DB import (BuiltInParameter, CategoryType, Element, GeometryInstance,
                               Options, Solid, SolidUtils, StorageType, UnitTypeId, UnitUtils)


# ---------------------------------------------------------
# Ids and names
# ---------------------------------------------------------
def id_value(eid):
    """ElementId -> int (Revit 2024+ .Value, older .IntegerValue)."""
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


def element_name(element):
    """Name that also works for types in IronPython (Element.Name can fail)."""
    try:
        return Element.Name.GetValue(element)
    except Exception:
        p = element.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        return p.AsString() if p else ""


def is_model_element(element):
    cat = element.Category
    return cat is not None and cat.CategoryType == CategoryType.Model


# ---------------------------------------------------------
# Parameters
# ---------------------------------------------------------
def is_writable(param, storage=None):
    return (param is not None and not param.IsReadOnly
            and (storage is None or param.StorageType == storage))


def param_text(param):
    """Parameter value as text ('' when missing or empty)."""
    if param is None or not param.HasValue:
        return ""
    if param.StorageType == StorageType.String:
        return param.AsString() or ""
    if param.StorageType == StorageType.Integer:
        return str(param.AsInteger())
    return param.AsValueString() or ""


def set_param(element, name, value):
    """Set a parameter by name if it exists and is writable. Returns True on success."""
    p = element.LookupParameter(name)
    if p is None or p.IsReadOnly:
        return False
    try:
        if p.StorageType == StorageType.Integer:
            return p.Set(int(value))
        if p.StorageType == StorageType.Double:
            return p.Set(float(value))
        return p.Set("" if value is None else str(value))
    except Exception:
        return False


def type_param_text(doc, element, name):
    etype = doc.GetElement(element.GetTypeId())
    return param_text(etype.LookupParameter(name)) if etype else ""


# ---------------------------------------------------------
# Units
# ---------------------------------------------------------
def mm_to_ft(mm):
    return UnitUtils.ConvertToInternalUnits(mm, UnitTypeId.Millimeters)


def ft_to_mm(ft):
    return UnitUtils.ConvertFromInternalUnits(ft, UnitTypeId.Millimeters)


# ---------------------------------------------------------
# Geometry
# ---------------------------------------------------------
def element_solids(element, transform=None):
    """Solids with volume of an element, optionally transformed (e.g. link -> host)."""
    solids = []
    geom = element.get_Geometry(Options())
    if geom is None:
        return solids
    for g in geom:
        items = g.GetInstanceGeometry() if isinstance(g, GeometryInstance) else [g]
        for s in items:
            if isinstance(s, Solid) and s.Volume > 0:
                solids.append(SolidUtils.CreateTransformed(s, transform) if transform else s)
    return solids
