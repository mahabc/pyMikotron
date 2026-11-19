# -*- coding: utf-8 -*-
"""OPGen record storage, kept inside the Revit model (Extensible Storage).

One hidden DataStorage element holds a JSON text with:
    {
      "version": 1,
      "offsets": {"pipe": 5.0, "duct": 5.0, "conduit": 5.0, "tray": 5.0},
      "openings": [ {record}, ... ]      # see opgen.Generator.records_from_results
    }

The data travels with the .rvt (Save As, moves, worksharing). In a
workshared model the DataStorage element must be editable (not borrowed by
someone else) when OPGen / OPUpdate save.
"""
import json

import clr
from System import Guid

from Autodesk.Revit.DB import FilteredElementCollector, Transaction
from Autodesk.Revit.DB.ExtensibleStorage import (
    AccessLevel, DataStorage, Entity, Schema, SchemaBuilder,
)

SCHEMA_GUID = Guid("6f0c1a52-3b7e-4c1d-9a51-0b2f6d9e4a17")
SCHEMA_NAME = "pyMikotronOPGen"
FIELD = "Json"
VERSION = 1


def _schema():
    schema = Schema.Lookup(SCHEMA_GUID)
    if schema is not None:
        return schema
    builder = SchemaBuilder(SCHEMA_GUID)
    builder.SetSchemaName(SCHEMA_NAME)
    builder.SetDocumentation("pyMikotron OPGen: openings created for MEP penetrations.")
    builder.SetReadAccessLevel(AccessLevel.Public)
    builder.SetWriteAccessLevel(AccessLevel.Public)
    builder.AddSimpleField(FIELD, clr.GetClrType(str))
    return builder.Finish()


def _find_storage(doc, schema):
    for ds in FilteredElementCollector(doc).OfClass(DataStorage):
        ent = ds.GetEntity(schema)
        if ent is not None and ent.IsValid():
            return ds, ent
    return None, None


def _empty():
    return {"version": VERSION, "offsets": {}, "openings": []}


def load(doc):
    """Stored data as a dict (empty structure if nothing stored yet)."""
    schema = Schema.Lookup(SCHEMA_GUID)
    if schema is None:
        return _empty()
    _, ent = _find_storage(doc, schema)
    if ent is None:
        return _empty()
    text = ent.Get[str](FIELD)
    if not text:
        return _empty()
    try:
        data = json.loads(text)
    except ValueError:
        return _empty()
    data.setdefault("version", VERSION)
    data.setdefault("offsets", {})
    data.setdefault("openings", [])
    return data


def save(doc, data, name="OPGen - Save Opening Records"):
    """Write the data to the model (opens its own transaction)."""
    schema = _schema()
    t = Transaction(doc, name)
    t.Start()
    try:
        ds, _ = _find_storage(doc, schema)
        if ds is None:
            ds = DataStorage.Create(doc)
        ent = Entity(schema)
        ent.Set[str](FIELD, json.dumps(data))
        ds.SetEntity(ent)
        t.Commit()
    except Exception:
        t.RollBack()
        raise


def add_records(doc, records, offsets):
    """Append new records and remember the offsets used."""
    data = load(doc)
    data["openings"].extend(records)
    data["offsets"].update(offsets)
    save(doc, data)
    return data


def count_by_category(data):
    counts = {}
    for rec in data.get("openings", []):
        counts[rec.get("cat")] = counts.get(rec.get("cat"), 0) + 1
    return counts
