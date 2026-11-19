# -*- coding: utf-8 -*-
"""Schedule Import / Export - shared logic.

Flow (see run()):
    pick schedule -> options -> read model data -> preview window
        -> Export: formatted .xlsx (Data sheet + hidden _meta sheet)
        -> Import: read .xlsx, list changes, Apply in one transaction

Editability per column:
    1. ScheduleField.FieldType   Instance -> green, ElementType -> yellow,
                                 anything else (count, formula...) -> red
    2. Project / shared params:  the BindingMap confirms or overrides step 1
    3. Per cell:                 the parameter is read by id/GUID from the
                                 element (or its type); IsReadOnly or an
                                 unsupported storage type -> red cell
Type values are read once per type and cached.
"""
import os
import re
import datetime

import clr
clr.AddReference("System.Data")
clr.AddReference("System.Drawing")

import System
from System.Data import DataTable
from System.Drawing import Color
from System.IO import FileInfo, FileStream, FileMode, FileAccess, FileShare

from Autodesk.Revit.DB import (
    BuiltInParameter, Element, FilteredElementCollector, InstanceBinding,
    ParameterElement, ScheduleFieldType, ScheduleSortOrder,
    SharedParameterElement, SpecTypeId, StorageType, TypeBinding, ViewSchedule,
)

from pyrevit import forms, revit, script

clr.AddReferenceToFileAndPath(os.path.join(os.path.dirname(__file__), "general", "EPPlus.dll"))
from OfficeOpenXml import ExcelPackage, eWorkSheetHidden
from OfficeOpenXml.Style import ExcelFillStyle


TITLE = "Schedule Import / Export"
FORMAT_VERSION = "1"

RO, TYPE, INST = "ro", "type", "inst"
KIND_LABEL = {RO: "Read-only", TYPE: "Type", INST: "Instance"}

# header colour / cell tint / header text colour
HEADER_BG = {RO: "#C0504D", TYPE: "#E6B422", INST: "#4E9A3E"}
HEADER_FG = {RO: "#FFFFFF", TYPE: "#000000", INST: "#FFFFFF"}
CELL_BG = {RO: "#F8D7D5", TYPE: "#FFF2CC", INST: "#E2F0D9"}
GROUP_BG = "#D9D9D9"
ID_BG = "#EDEDED"
ID_HEADER_BG = "#7F7F7F"

YES = set(["yes", "y", "1", "true", "si", u"sí", "x"])
NO = set(["no", "n", "0", "false"])


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def id_value(eid):
    """ElementId -> number (Revit 2024+ uses .Value, older .IntegerValue)."""
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


_NUM = re.compile(r"(\d+)")


def natural_key(text):
    if not text:
        return [(-1, u"")]
    return [(0, int(t)) if t.isdigit() else (1, t.lower())
            for t in _NUM.split(text) if t != u""]


def to_float(text):
    try:
        return float(text.strip().replace(u",", u"."))
    except (ValueError, AttributeError):
        return None


def xml_escape(text):
    text = (text or u"").replace(u"&", u"&amp;").replace(u"<", u"&lt;") \
        .replace(u">", u"&gt;").replace(u'"', u"&quot;")
    if text.startswith(u"{"):
        text = u"{}" + text          # stop XAML reading it as a markup extension
    return text


def xl_color(hex_code):
    h = hex_code.lstrip("#")
    return Color.FromArgb(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def is_yesno(param):
    try:
        return param.Definition.GetDataType() == SpecTypeId.Boolean.YesNo
    except Exception:
        return False


def is_writable(param):
    if param is None or param.IsReadOnly:
        return False
    try:
        if not param.UserModifiable:
            return False
    except Exception:
        pass
    return param.StorageType in (StorageType.String, StorageType.Double, StorageType.Integer)


def read_param(param):
    """-> (display text, sort key)."""
    st = param.StorageType
    if st == StorageType.String:
        text = param.AsString() or u""
        return text, (1, natural_key(text))
    if is_yesno(param):
        if not param.HasValue:
            return u"", (-1,)
        val = param.AsInteger()
        return (u"Yes" if val == 1 else u"No"), (0, val)
    if st == StorageType.Double:
        text = param.AsValueString() if param.HasValue else u""
        return text or u"", ((0, param.AsDouble()) if param.HasValue else (-1,))
    if st == StorageType.Integer:
        text = param.AsValueString() if param.HasValue else u""
        if text is None:
            text = str(param.AsInteger())
        return text, ((0, param.AsInteger()) if param.HasValue else (-1,))
    if st == StorageType.ElementId:
        text = param.AsValueString() or u""
        return text, (1, natural_key(text))
    return u"", (-1,)


def write_param(param, text):
    """Set a parameter from text. -> (ok, message)."""
    st = param.StorageType
    if st == StorageType.String:
        return bool(param.Set(text)), u""
    if is_yesno(param):
        low = text.strip().lower()
        if low in YES:
            return bool(param.Set(1)), u""
        if low in NO:
            return bool(param.Set(0)), u""
        return False, u"Not a Yes/No value"
    if st in (StorageType.Double, StorageType.Integer):
        if not text.strip():
            return False, u"A number cannot be cleared"
        candidates = [text]
        if u"," in text:
            candidates.append(text.replace(u",", u"."))
        elif u"." in text:
            candidates.append(text.replace(u".", u","))
        for cand in candidates:
            try:
                if param.SetValueString(cand):
                    return True, u""
            except Exception:
                pass
        if st == StorageType.Integer:
            try:
                return bool(param.Set(int(text.strip()))), u""
            except (ValueError, Exception):
                pass
        return False, u"Revit could not read the value"
    return False, u"Unsupported parameter type"


# ---------------------------------------------------------------------------
# Model data
# ---------------------------------------------------------------------------
class Cell(object):
    __slots__ = ("text", "sort", "src", "owner_id", "editable")

    def __init__(self, text=u"", sort=(-1,), src=None, owner_id=None, editable=False):
        self.text = text
        self.sort = sort
        self.src = src            # "I" (instance) / "T" (type) / None
        self.owner_id = owner_id  # ElementId the value lives on
        self.editable = editable


EMPTY = Cell()


class Column(object):
    def __init__(self, doc, field, index, binding_cache):
        self.index = index
        self.field_id = id_value(field.FieldId)
        self.name = field.GetName()
        self.heading = field.ColumnHeading or self.name
        self.hidden = field.IsHidden
        self.field_type = field.FieldType
        self.bip = self.guid = self.defn = None

        pid = field.ParameterId
        pval = id_value(pid)
        if pval < -1:
            self.bip = System.Enum.ToObject(BuiltInParameter, int(pval))
            self.key = u"bip:{}".format(self.bip)
        elif pval > 0:
            pe = doc.GetElement(pid)
            if isinstance(pe, SharedParameterElement):
                self.guid = pe.GuidValue
                self.defn = pe.GetDefinition()
                self.key = u"guid:{}".format(self.guid)
            elif isinstance(pe, ParameterElement):
                self.defn = pe.GetDefinition()
                self.key = u"pid:{}".format(pval)
            else:
                self.key = u"pid:{}".format(pval)
        else:
            self.key = u"field:{}:{}".format(self.field_type, self.name)

        self.kind = self._classify(doc, binding_cache)

    def _classify(self, doc, binding_cache):
        if self.field_type == ScheduleFieldType.Instance:
            kind = INST
        elif self.field_type == ScheduleFieldType.ElementType:
            kind = TYPE
        else:
            return RO
        if self.bip is None and self.guid is None and self.defn is None:
            return RO
        if self.defn is not None:
            key = self.key
            if key not in binding_cache:
                binding = None
                try:
                    binding = doc.ParameterBindings.get_Item(self.defn)
                except Exception:
                    pass
                binding_cache[key] = binding
            binding = binding_cache[key]
            if isinstance(binding, InstanceBinding):
                kind = INST
            elif isinstance(binding, TypeBinding):
                kind = TYPE
        return kind

    @property
    def reads_params(self):
        return self.field_type in (ScheduleFieldType.Instance, ScheduleFieldType.ElementType)

    def get_param(self, owner):
        if owner is None:
            return None
        if self.bip is not None:
            return owner.get_Parameter(self.bip)
        if self.guid is not None:
            return owner.get_Parameter(self.guid)
        if self.defn is not None:
            return owner.get_Parameter(self.defn)
        return None


class Row(object):
    __slots__ = ("element", "etype", "uid", "eid", "cells")

    def __init__(self, element, etype):
        self.element = element
        self.etype = etype
        self.uid = element.UniqueId
        self.eid = id_value(element.Id)
        self.cells = {}


class GroupRow(object):
    __slots__ = ("level", "text")

    def __init__(self, level, text):
        self.level = level
        self.text = text


class ScheduleData(object):
    def __init__(self, doc, schedule, include_hidden, keep_grouping):
        self.doc = doc
        self.schedule = schedule
        self.include_hidden = include_hidden
        self.keep_grouping = keep_grouping
        self._type_cache = {}

        definition = schedule.Definition
        binding_cache = {}
        self.columns = []
        for i, fid in enumerate(definition.GetFieldOrder()):
            self.columns.append(Column(doc, definition.GetField(fid), i, binding_cache))
        self.by_field = dict((c.field_id, c) for c in self.columns)
        self.by_key = dict((c.key, c) for c in self.columns)
        self.display = [c for c in self.columns if include_hidden or not c.hidden]

        self.sort_levels = []      # (column, descending, show_header)
        if keep_grouping:
            for i in range(definition.GetSortGroupFieldCount()):
                sg = definition.GetSortGroupField(i)
                col = self.by_field.get(id_value(sg.FieldId))
                if col is not None:
                    self.sort_levels.append(
                        (col, sg.SortOrder == ScheduleSortOrder.Descending, sg.ShowHeader))

        self.rows = []
        self.items = []
        self.by_uid = {}

    # -- reading -----------------------------------------------------------
    def load(self):
        elements = list(FilteredElementCollector(self.doc, self.schedule.Id).ToElements())
        needed = list(self.display)
        for col, _, _ in self.sort_levels:
            if col not in needed:
                needed.append(col)

        total = len(elements)
        with forms.ProgressBar(title="Reading schedule ({value} of {max_value})") as pb:
            for n, el in enumerate(elements):
                tid = el.GetTypeId()
                etype = self.doc.GetElement(tid) if id_value(tid) > 0 else None
                row = Row(el, etype)
                for col in needed:
                    self.cell(row, col)
                self.rows.append(row)
                self.by_uid[row.uid] = row
                if n % 100 == 0:
                    pb.update_progress(n, total)

        # a column with no editable cell at all is shown as read-only
        for col in self.display:
            if col.kind != RO and not any(r.cells[col.index].editable for r in self.rows):
                col.kind = RO

        self._sort_and_group()

    def cell(self, row, col):
        """Cell for row/column, computed once (type values cached per type)."""
        cached = row.cells.get(col.index)
        if cached is not None:
            return cached

        if col.field_type == ScheduleFieldType.Count:
            result = Cell(u"1", (0, 1))
        elif not col.reads_params:
            result = EMPTY
        else:
            result = None
            owners = [(row.element, "I"), (row.etype, "T")]
            if col.kind == TYPE:
                owners.reverse()
            for owner, src in owners:
                if owner is None:
                    continue
                if src == "T":
                    key = (id_value(owner.Id), col.index)
                    if key in self._type_cache:
                        result = self._type_cache[key]
                        if result is not None:
                            break
                        continue
                param = col.get_param(owner)
                if param is None:
                    if src == "T":
                        self._type_cache[(id_value(owner.Id), col.index)] = None
                    continue
                text, sort = read_param(param)
                result = Cell(text, sort, src, owner.Id,
                              col.kind != RO and is_writable(param))
                if src == "T":
                    self._type_cache[(id_value(owner.Id), col.index)] = result
                break
            if result is None:
                result = EMPTY
        row.cells[col.index] = result
        return result

    def _sort_and_group(self):
        rows = list(self.rows)
        if not self.sort_levels:
            rows.sort(key=lambda r: r.eid)
            self.items = rows
            return
        # stable sort, least significant level first
        rows.sort(key=lambda r: r.eid)
        for col, desc, _ in reversed(self.sort_levels):
            rows.sort(key=lambda r, c=col: r.cells[c.index].sort, reverse=desc)

        items = []
        previous = [None] * len(self.sort_levels)
        for row in rows:
            for lvl, (col, _, show_header) in enumerate(self.sort_levels):
                key = tuple(row.cells[c.index].text for c, _, _ in self.sort_levels[:lvl + 1])
                if key != previous[lvl]:
                    previous[lvl] = key
                    if show_header:
                        value = row.cells[col.index].text or u"(blank)"
                        items.append(GroupRow(lvl, u"{}{}: {}".format(u"    " * lvl, col.heading, value)))
            items.append(row)
        self.items = items


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------
def _fill(rng, hex_code):
    rng.Style.Fill.PatternType = ExcelFillStyle.Solid
    rng.Style.Fill.BackgroundColor.SetColor(xl_color(hex_code))


def export_xlsx(data, path):
    cols = data.display
    ncol = 2 + len(cols)
    pkg = ExcelPackage()
    try:
        ws = pkg.Workbook.Worksheets.Add("Data")
        ws.Cells[1, 1].Value = "UniqueId"
        ws.Cells[1, 2].Value = "ElementId"
        for j, col in enumerate(cols):
            ws.Cells[1, 3 + j].Value = col.heading

        r = 2
        group_rows, red_cells = [], []
        for item in data.items:
            if isinstance(item, GroupRow):
                ws.Cells[r, 3].Value = item.text
                group_rows.append(r)
            else:
                ws.Cells[r, 1].Value = item.uid
                ws.Cells[r, 2].Value = item.eid
                for j, col in enumerate(cols):
                    cell = item.cells[col.index]
                    if cell.text:
                        ws.Cells[r, 3 + j].Value = cell.text
                    if col.kind != RO and not cell.editable:
                        red_cells.append((r, 3 + j))
            r += 1
        last = max(r - 1, 1)

        # header
        head = ws.Cells[1, 1, 1, ncol]
        head.Style.Font.Bold = True
        _fill(ws.Cells[1, 1, 1, 2], ID_HEADER_BG)
        ws.Cells[1, 1, 1, 2].Style.Font.Color.SetColor(xl_color("#FFFFFF"))
        for j, col in enumerate(cols):
            c = ws.Cells[1, 3 + j]
            _fill(c, HEADER_BG[col.kind])
            c.Style.Font.Color.SetColor(xl_color(HEADER_FG[col.kind]))

        # body: whole columns first, exceptions after
        if last >= 2:
            _fill(ws.Cells[2, 1, last, 2], ID_BG)
            for j, col in enumerate(cols):
                rng = ws.Cells[2, 3 + j, last, 3 + j]
                _fill(rng, CELL_BG[col.kind])
                if col.kind != RO:
                    rng.Style.Locked = False
            for (rr, cc) in red_cells:
                c = ws.Cells[rr, cc]
                _fill(c, CELL_BG[RO])
                c.Style.Locked = True
            for gr in group_rows:
                rng = ws.Cells[gr, 1, gr, ncol]
                _fill(rng, GROUP_BG)
                rng.Style.Font.Bold = True
                rng.Style.Locked = True

        ws.View.FreezePanes(2, 3)
        ws.Cells[1, 1, last, ncol].AutoFilter = True
        if last <= 5000:
            try:
                ws.Cells[1, 1, last, ncol].AutoFitColumns(8, 60)
            except Exception:
                pass
        ws.Column(1).Width = 14
        ws.Column(2).Width = 11

        prot = ws.Protection
        prot.IsProtected = True
        prot.AllowAutoFilter = True
        prot.AllowFormatColumns = True
        prot.AllowFormatRows = True
        prot.AllowSelectLockedCells = True
        prot.AllowSelectUnlockedCells = True

        # hidden meta sheet: maps Excel columns to parameters
        meta = pkg.Workbook.Worksheets.Add("_meta")
        info = [
            ("format", FORMAT_VERSION),
            ("schedule_uid", data.schedule.UniqueId),
            ("schedule_name", data.schedule.Name),
            ("document", data.doc.Title),
            ("exported", datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
        ]
        for i, (k, v) in enumerate(info):
            meta.Cells[i + 1, 1].Value = k
            meta.Cells[i + 1, 2].Value = v
        hr = len(info) + 2
        for j, h in enumerate(("excel_col", "key", "heading", "kind")):
            meta.Cells[hr, 1 + j].Value = h
        for j, col in enumerate(cols):
            meta.Cells[hr + 1 + j, 1].Value = 3 + j
            meta.Cells[hr + 1 + j, 2].Value = col.key
            meta.Cells[hr + 1 + j, 3].Value = col.heading
            meta.Cells[hr + 1 + j, 4].Value = col.kind
        meta.Hidden = eWorkSheetHidden.Hidden

        pkg.SaveAs(FileInfo(path))
    finally:
        pkg.Dispose()


# ---------------------------------------------------------------------------
# Excel import
# ---------------------------------------------------------------------------
def xl_text(value):
    if value is None:
        return u""
    if isinstance(value, bool):
        return u"Yes" if value else u"No"
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e15:
            return str(int(value))
        return (u"%.10f" % value).rstrip(u"0").rstrip(u".")
    if isinstance(value, System.DateTime):
        return value.ToString("yyyy-MM-dd")
    return str(value)


def read_xlsx(path):
    """-> (meta dict, {excel_col: key}, [(uid, {key: text})])."""
    stream = FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite)
    try:
        pkg = ExcelPackage(stream)
        try:
            wb = pkg.Workbook
            ws = wb.Worksheets["Data"]
            meta_ws = wb.Worksheets["_meta"]
            if ws is None or meta_ws is None:
                raise ValueError("This file was not exported by Schedule Import / Export "
                                 "(missing 'Data' or '_meta' sheet).")
            meta, colmap = {}, {}
            end = meta_ws.Dimension.End.Row if meta_ws.Dimension else 0
            in_cols = False
            for r in range(1, end + 1):
                a = xl_text(meta_ws.Cells[r, 1].Value)
                b = xl_text(meta_ws.Cells[r, 2].Value)
                if a == u"excel_col":
                    in_cols = True
                    continue
                if not a:
                    continue
                if in_cols:
                    colmap[int(float(a))] = b
                else:
                    meta[a] = b

            rows = []
            end = ws.Dimension.End.Row if ws.Dimension else 0
            for r in range(2, end + 1):
                uid = xl_text(ws.Cells[r, 1].Value).strip()
                if not uid:
                    continue            # group header rows / blank rows
                vals = {}
                for c, key in colmap.items():
                    vals[key] = xl_text(ws.Cells[r, c].Value)
                rows.append((uid, vals))
            return meta, colmap, rows
        finally:
            pkg.Dispose()
    finally:
        stream.Close()


class Change(object):
    def __init__(self, row, col, cell, old, new):
        self.row = row
        self.col = col
        self.cell = cell
        self.old = old
        self.new = new
        self.status = u"OK"
        self.apply = True
        self.result = None

    def skip(self, reason):
        self.status = reason
        self.apply = False


def element_label(doc, row):
    el = row.element
    cat = el.Category.Name if el.Category is not None else u""
    name = u""
    try:
        name = el.Name or u""
    except Exception:
        pass
    if row.etype is not None:
        try:
            fam = row.etype.FamilyName or u""
        except Exception:
            fam = u""
        try:
            tname = Element.Name.GetValue(row.etype) or u""
        except Exception:
            tname = u""
        name = u"{} : {}".format(fam, tname) if fam else (tname or name)
    return u"{} | {} [{}]".format(cat, name, row.eid).strip(u" |")


def build_changes(data, file_rows):
    changes, not_found, unknown_cols = [], 0, set()
    by_type = {}
    for uid, vals in file_rows:
        row = data.by_uid.get(uid)
        if row is None:
            not_found += 1
            continue
        for key, new in vals.items():
            col = data.by_key.get(key)
            if col is None:
                unknown_cols.add(key)
                continue
            cell = data.cell(row, col)
            new = new.strip()
            old = cell.text or u""
            if new == old.strip():
                continue
            if col.kind == RO and not cell.editable:
                if new or old:
                    ch = Change(row, col, cell, old, new)
                    ch.skip(u"Read-only column")
                    changes.append(ch)
                continue
            fnew, fold = to_float(new), to_float(old)
            if fnew is not None and fold is not None and fnew == fold:
                continue
            ch = Change(row, col, cell, old, new)
            if not cell.editable:
                ch.skip(u"Read-only for this element")
            elif cell.src == "T":
                by_type.setdefault((id_value(cell.owner_id), col.index), []).append(ch)
            changes.append(ch)

    # type values: one write per type; rows that disagree are a conflict
    for group in by_type.values():
        values = set(c.new for c in group)
        if len(values) > 1:
            for c in group:
                c.skip(u"Conflict: rows of this type have different values ({})".format(
                    u" / ".join(sorted(values))))
        else:
            for c in group[1:]:
                c.apply = False
                c.status = u"Same type, written once"
    return changes, not_found, unknown_cols


def apply_changes(doc, changes, schedule_name):
    todo = [c for c in changes if c.apply]
    ok = failed = 0
    with revit.Transaction(u"Schedule Import: {}".format(schedule_name), doc=doc):
        for ch in todo:
            owner = doc.GetElement(ch.cell.owner_id)
            param = ch.col.get_param(owner)
            if param is None or not is_writable(param):
                ch.result, ch.status = False, u"Parameter not writable"
                failed += 1
                continue
            try:
                success, msg = write_param(param, ch.new)
            except Exception as ex:
                success, msg = False, str(ex)
            ch.result = success
            if success:
                ch.status = u"Updated"
                ok += 1
            else:
                ch.status = msg or u"Revit refused the value"
                failed += 1
    return ok, failed


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------
OPTIONS_XAML = u"""
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="%%TITLE%%" SizeToContent="WidthAndHeight" ResizeMode="NoResize"
        WindowStartupLocation="CenterScreen" ShowInTaskbar="False">
  <StackPanel Margin="16" MinWidth="280">
    <TextBlock Text="%%NAME%%" FontWeight="Bold" Margin="0,0,0,10" TextWrapping="Wrap" MaxWidth="360"/>
    <CheckBox x:Name="cb_hidden" Content="Include hidden fields" Margin="0,0,0,6"/>
    <CheckBox x:Name="cb_group" Content="Keep sorting and grouping" IsChecked="True"/>
    <StackPanel Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,14,0,0">
      <Button Content="Open" Width="80" Height="26" IsDefault="True" Click="ok_click" Margin="0,0,8,0"/>
      <Button Content="Cancel" Width="70" Height="26" IsCancel="True"/>
    </StackPanel>
  </StackPanel>
</Window>
"""


class OptionsDialog(forms.WPFWindow):
    def __init__(self, schedule_name):
        xaml = OPTIONS_XAML.replace("%%TITLE%%", TITLE) \
            .replace("%%NAME%%", xml_escape(schedule_name))
        forms.WPFWindow.__init__(self, xaml, literal_string=True)
        self.result = None

    def ok_click(self, sender, args):
        self.result = (bool(self.cb_hidden.IsChecked), bool(self.cb_group.IsChecked))
        self.Close()


LEGEND_XAML = u"""
      <StackPanel Orientation="Horizontal" Margin="0,6,0,0">
        <Border Width="14" Height="14" Background="%%G%%" Margin="0,0,4,0"/>
        <TextBlock Text="Instance" Margin="0,0,14,0"/>
        <Border Width="14" Height="14" Background="%%Y%%" Margin="0,0,4,0"/>
        <TextBlock Text="Type (applies to every instance of the type)" Margin="0,0,14,0"/>
        <Border Width="14" Height="14" Background="%%R%%" Margin="0,0,4,0"/>
        <TextBlock Text="Read-only"/>
      </StackPanel>
"""

PREVIEW_XAML = u"""
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="%%TITLE%%" Width="1150" Height="680"
        WindowStartupLocation="CenterScreen" ShowInTaskbar="False">
  <DockPanel Margin="10">
    <StackPanel DockPanel.Dock="Top" Margin="0,0,0,8">
      <TextBlock x:Name="tb_title" FontWeight="Bold" FontSize="14"/>
      <TextBlock x:Name="tb_info" Foreground="Gray"/>
%%LEGEND%%
    </StackPanel>
    <StackPanel DockPanel.Dock="Bottom" Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,8,0,0">
      <Button Content="Export to Excel..." Height="28" Padding="12,0" Click="export_click" Margin="0,0,8,0"/>
      <Button Content="Import from Excel..." Height="28" Padding="12,0" Click="import_click" Margin="0,0,8,0"/>
      <Button Content="Close" Width="80" Height="28" IsCancel="True"/>
    </StackPanel>
    <DataGrid x:Name="grid" AutoGenerateColumns="False" IsReadOnly="True"
              CanUserSortColumns="False" CanUserReorderColumns="False"
              HeadersVisibility="Column" FontSize="12" GridLinesVisibility="All"
              HorizontalGridLinesBrush="#DDDDDD" VerticalGridLinesBrush="#DDDDDD"
              EnableRowVirtualization="True" EnableColumnVirtualization="True"
              FrozenColumnCount="1">
      <DataGrid.Columns>
%%COLUMNS%%
      </DataGrid.Columns>
    </DataGrid>
  </DockPanel>
</Window>
"""

COLUMN_XAML = u"""
        <DataGridTextColumn Header="%%HEADER%%" Binding="{Binding %%FIELD%%}">
          <DataGridTextColumn.HeaderStyle>
            <Style TargetType="DataGridColumnHeader">
              <Setter Property="Background" Value="%%HBG%%"/>
              <Setter Property="Foreground" Value="%%HFG%%"/>
              <Setter Property="FontWeight" Value="Bold"/>
              <Setter Property="Padding" Value="6,4"/>
              <Setter Property="BorderBrush" Value="#FFFFFF"/>
              <Setter Property="BorderThickness" Value="0,0,1,0"/>
            </Style>
          </DataGridTextColumn.HeaderStyle>
          <DataGridTextColumn.CellStyle>
            <Style TargetType="DataGridCell">
              <Setter Property="Background" Value="%%CBG%%"/>
              <Setter Property="Foreground" Value="#000000"/>
              <Setter Property="BorderThickness" Value="0"/>
              <Style.Triggers>
%%TRIGGERS%%
                <DataTrigger Binding="{Binding _g}" Value="1">
                  <Setter Property="Background" Value="%%GBG%%"/>
                  <Setter Property="FontWeight" Value="Bold"/>
                </DataTrigger>
              </Style.Triggers>
            </Style>
          </DataGridTextColumn.CellStyle>
        </DataGridTextColumn>
"""

RED_TRIGGER = u"""
                <DataTrigger Binding="{Binding %%EFIELD%%}" Value="0">
                  <Setter Property="Background" Value="%%RBG%%"/>
                </DataTrigger>
"""


def _column_xaml(header, field, hbg, hfg, cbg, red_field=None):
    triggers = u""
    if red_field:
        triggers = RED_TRIGGER.replace("%%EFIELD%%", red_field).replace("%%RBG%%", CELL_BG[RO])
    return (COLUMN_XAML.replace("%%HEADER%%", xml_escape(header))
            .replace("%%FIELD%%", field).replace("%%HBG%%", hbg).replace("%%HFG%%", hfg)
            .replace("%%CBG%%", cbg).replace("%%GBG%%", GROUP_BG)
            .replace("%%TRIGGERS%%", triggers))


def _legend():
    return LEGEND_XAML.replace("%%G%%", HEADER_BG[INST]).replace("%%Y%%", HEADER_BG[TYPE]) \
        .replace("%%R%%", HEADER_BG[RO])


class PreviewWindow(forms.WPFWindow):
    def __init__(self, data):
        cols = data.display
        parts = [_column_xaml(u"ElementId", "eid", ID_HEADER_BG, "#FFFFFF", ID_BG)]
        for i, col in enumerate(cols):
            parts.append(_column_xaml(col.heading, "c%d" % i, HEADER_BG[col.kind],
                                      HEADER_FG[col.kind], CELL_BG[col.kind],
                                      None if col.kind == RO else "e%d" % i))
        xaml = (PREVIEW_XAML.replace("%%TITLE%%", TITLE).replace("%%LEGEND%%", _legend())
                .replace("%%COLUMNS%%", u"".join(parts)))
        forms.WPFWindow.__init__(self, xaml, literal_string=True)
        self.action = None

        counts = {RO: 0, TYPE: 0, INST: 0}
        for col in cols:
            counts[col.kind] += 1
        self.tb_title.Text = data.schedule.Name
        self.tb_info.Text = (u"{} elements  |  {} columns: {} instance, {} type, {} read-only"
                             .format(len(data.rows), len(cols), counts[INST], counts[TYPE], counts[RO]))
        self.grid.ItemsSource = self._table(data).DefaultView

    @staticmethod
    def _table(data):
        cols = data.display
        table = DataTable()
        names = ["eid", "_g"]
        for i in range(len(cols)):
            names.extend(["c%d" % i, "e%d" % i])
        for name in names:
            table.Columns.Add(name)
        table.BeginLoadData()
        for item in data.items:
            if isinstance(item, GroupRow):
                values = [u"", u"1"]
                for i in range(len(cols)):
                    values.extend([item.text if i == 0 else u"", u"1"])
            else:
                values = [str(item.eid), u"0"]
                for col in cols:
                    cell = item.cells[col.index]
                    values.extend([cell.text, u"1" if cell.editable else u"0"])
            table.Rows.Add(System.Array[System.Object](values))
        table.EndLoadData()
        return table

    def export_click(self, sender, args):
        self.action = "export"
        self.Close()

    def import_click(self, sender, args):
        self.action = "import"
        self.Close()


CHANGES_XAML = u"""
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="%%TITLE%%" Width="1050" Height="600"
        WindowStartupLocation="CenterScreen" ShowInTaskbar="False">
  <DockPanel Margin="10">
    <StackPanel DockPanel.Dock="Top" Margin="0,0,0,8">
      <TextBlock x:Name="tb_title" FontWeight="Bold" FontSize="14"/>
      <TextBlock x:Name="tb_info" Foreground="Gray" TextWrapping="Wrap"/>
%%LEGEND%%
    </StackPanel>
    <StackPanel DockPanel.Dock="Bottom" Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,8,0,0">
      <Button x:Name="bt_apply" Height="28" Padding="12,0" Click="apply_click" Margin="0,0,8,0" IsDefault="True"/>
      <Button Content="Cancel" Width="80" Height="28" IsCancel="True"/>
    </StackPanel>
    <DataGrid x:Name="grid" AutoGenerateColumns="False" IsReadOnly="True"
              HeadersVisibility="Column" FontSize="12" GridLinesVisibility="Horizontal"
              HorizontalGridLinesBrush="#DDDDDD" EnableRowVirtualization="True">
      <DataGrid.RowStyle>
        <Style TargetType="DataGridRow">
          <Style.Triggers>
            <DataTrigger Binding="{Binding k}" Value="skip">
              <Setter Property="Background" Value="%%RBG%%"/>
            </DataTrigger>
            <DataTrigger Binding="{Binding k}" Value="type">
              <Setter Property="Background" Value="%%YBG%%"/>
            </DataTrigger>
            <DataTrigger Binding="{Binding k}" Value="inst">
              <Setter Property="Background" Value="%%GBG%%"/>
            </DataTrigger>
          </Style.Triggers>
        </Style>
      </DataGrid.RowStyle>
      <DataGrid.Columns>
        <DataGridTextColumn Header="Element" Binding="{Binding el}" Width="260"/>
        <DataGridTextColumn Header="Parameter" Binding="{Binding p}" Width="160"/>
        <DataGridTextColumn Header="On" Binding="{Binding on}" Width="70"/>
        <DataGridTextColumn Header="Current value" Binding="{Binding old}" Width="150"/>
        <DataGridTextColumn Header="New value" Binding="{Binding new}" Width="150"/>
        <DataGridTextColumn Header="Status" Binding="{Binding st}" Width="*"/>
      </DataGrid.Columns>
    </DataGrid>
  </DockPanel>
</Window>
"""


class ChangesWindow(forms.WPFWindow):
    def __init__(self, doc, schedule_name, changes, info):
        xaml = (CHANGES_XAML.replace("%%TITLE%%", TITLE).replace("%%LEGEND%%", _legend())
                .replace("%%RBG%%", CELL_BG[RO]).replace("%%YBG%%", CELL_BG[TYPE])
                .replace("%%GBG%%", CELL_BG[INST]))
        forms.WPFWindow.__init__(self, xaml, literal_string=True)
        self.confirmed = False
        n_apply = len([c for c in changes if c.apply])
        self.tb_title.Text = u"Import into: {}".format(schedule_name)
        self.tb_info.Text = info
        self.bt_apply.Content = u"Apply {} change{}".format(n_apply, u"" if n_apply == 1 else u"s")
        self.bt_apply.IsEnabled = n_apply > 0

        table = DataTable()
        for name in ("el", "p", "on", "old", "new", "st", "k"):
            table.Columns.Add(name)
        labels = {}
        table.BeginLoadData()
        for ch in changes:
            if ch.row.eid not in labels:
                labels[ch.row.eid] = element_label(doc, ch.row)
            on = {"I": u"Instance", "T": u"Type"}.get(ch.cell.src, u"")
            if not ch.apply and ch.status != u"Same type, written once":
                kind = "skip"
            else:
                kind = "type" if ch.cell.src == "T" else "inst"
            table.Rows.Add(System.Array[System.Object](
                [labels[ch.row.eid], ch.col.heading, on, ch.old, ch.new, ch.status, kind]))
        table.EndLoadData()
        self.grid.ItemsSource = table.DefaultView

    def apply_click(self, sender, args):
        self.confirmed = True
        self.Close()


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------
class _ScheduleItem(forms.TemplateListItem):
    @property
    def name(self):
        return self.item.Name


def get_schedules(doc):
    result = []
    for vs in FilteredElementCollector(doc).OfClass(ViewSchedule):
        if vs.IsTemplate or getattr(vs, "IsTitleblockRevisionSchedule", False) \
                or getattr(vs, "IsInternalKeynoteSchedule", False):
            continue
        try:
            if vs.Definition.IsMaterialTakeoff:
                continue
        except Exception:
            continue
        result.append(vs)
    return sorted(result, key=lambda v: v.Name.lower())


def safe_filename(name):
    return re.sub(r'[\\/:*?"<>|]+', u"_", name).strip() or u"Schedule"


def do_export(data):
    path = forms.save_file(file_ext="xlsx", default_name=safe_filename(data.schedule.Name),
                           title="Export schedule to Excel")
    if not path:
        return
    if not path.lower().endswith(".xlsx"):
        path += ".xlsx"
    try:
        export_xlsx(data, path)
    except Exception as ex:
        forms.alert(u"Export failed. If the file is open in Excel, close it and try again.\n\n{}"
                    .format(ex), title=TITLE)
        return
    if forms.alert(u"Exported {} elements to:\n{}\n\nOpen it now?".format(len(data.rows), path),
                   title=TITLE, yes=True, no=True):
        os.startfile(path)


def do_import(doc, data):
    path = forms.pick_file(file_ext="xlsx", title="Import schedule from Excel")
    if not path:
        return
    try:
        meta, colmap, file_rows = read_xlsx(path)
    except Exception as ex:
        forms.alert(u"Could not read the file.\n\n{}".format(ex), title=TITLE)
        return

    if meta.get("schedule_uid") != data.schedule.UniqueId:
        if not forms.alert(u"This file was exported from the schedule '{}', not '{}'.\n\n"
                           u"Rows are matched by UniqueId and columns by parameter, so it can "
                           u"still work. Continue?".format(meta.get("schedule_name", "?"),
                                                           data.schedule.Name),
                           title=TITLE, yes=True, no=True):
            return

    changes, not_found, unknown_cols = build_changes(data, file_rows)
    info = [u"{} rows read from {}.".format(len(file_rows), os.path.basename(path))]
    if not_found:
        info.append(u"{} rows have a UniqueId that is not in this schedule (skipped).".format(not_found))
    if unknown_cols:
        info.append(u"{} columns are not in the schedule (skipped).".format(len(unknown_cols)))
    if not changes:
        forms.alert(u"No changes found.\n\n" + u"\n".join(info), title=TITLE)
        return

    win = ChangesWindow(doc, data.schedule.Name, changes, u" ".join(info))
    win.show_dialog()
    if not win.confirmed:
        return

    ok, failed = apply_changes(doc, changes, data.schedule.Name)
    report(doc, data, changes, ok, failed, info)


def report(doc, data, changes, ok, failed, info):
    output = script.get_output()
    output.set_title(TITLE)
    output.print_md(u"## Import into {}".format(data.schedule.Name))
    output.print_md(u"**{}** updated, **{}** failed, **{}** skipped.".format(
        ok, failed, len([c for c in changes if c.result is None and c.status != u"Same type, written once"])))
    for line in info:
        output.print_md(line)

    rows = []
    for ch in changes:
        if ch.status == u"Same type, written once":
            continue
        rows.append([output.linkify(ch.row.element.Id), ch.col.heading,
                     {"I": u"Instance", "T": u"Type"}.get(ch.cell.src, u""),
                     ch.old, ch.new, ch.status])
    if rows:
        output.print_table(rows[:2000], columns=["Element", "Parameter", "On", "Old", "New", "Status"])
        if len(rows) > 2000:
            output.print_md(u"... {} more rows not shown.".format(len(rows) - 2000))


def run(doc):
    if doc.IsFamilyDocument:
        forms.alert("Run this in a project document.", title=TITLE, exitscript=True)

    schedules = get_schedules(doc)
    if not schedules:
        forms.alert("No schedules found in this model.", title=TITLE, exitscript=True)

    picked = forms.SelectFromList.show([_ScheduleItem(s) for s in schedules],
                                       title="Pick a schedule", multiselect=False,
                                       button_name="Select")
    if not picked:
        return
    schedule = picked.item if isinstance(picked, forms.TemplateListItem) else picked

    opts = OptionsDialog(schedule.Name)
    opts.show_dialog()
    if not opts.result:
        return
    include_hidden, keep_grouping = opts.result

    data = ScheduleData(doc, schedule, include_hidden, keep_grouping)
    data.load()
    if not data.rows:
        forms.alert(u"The schedule '{}' has no elements.".format(schedule.Name), title=TITLE)
        return

    win = PreviewWindow(data)
    win.show_dialog()
    if win.action == "export":
        do_export(data)
    elif win.action == "import":
        do_import(doc, data)


def main():
    run(revit.doc)
