# -*- coding: utf-8 -*-
"""Filter Export - writes the model's view filters to a formatted .xlsx.

First step towards Filter Import: export a real model to see what the format must handle.

Sheets:
    Categories  one category per row, one filter per column, x = the filter uses it
    Rules       one row per parameter rule (filter, logic, group, parameter, operator, value)
    Overrides   one row per filter applied to each picked view / template
    Lists       line patterns, fill patterns, operators (future dropdown sources)
    Issues      everything that does not fit the simple format, so we can decide on it

Notes:
    Logic / Group   Logic is the AND/OR of the group the rule sits in. Group is empty for
                    the top level and "1", "1.2"... for nested groups (Revit allows nesting).
    Value           numbers are written in project units (e.g. 4", 100 mm); RawValue keeps
                    the internal value (feet / ids) so nothing is lost.
    Overrides       empty cell = no override in the view.
"""
import datetime
import os
import re

import clr
clr.AddReference("System.Drawing")
import System
from System.Collections.Generic import List
from System.Drawing import Color as DColor
from System.IO import FileInfo

from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter, Category, ElementId,
                               ElementMulticategoryFilter, FillPatternElement,
                               FilteredElementCollector, LabelUtils, LinePatternElement,
                               ParameterElement,
                               ParameterFilterElement, ParameterFilterUtilities,
                               SelectionFilterElement, SharedParameterElement, SpecTypeId,
                               UnitFormatUtils, View)
from pyrevit import forms, revit, script

from general.helpers import element_name, id_value

clr.AddReferenceToFileAndPath(os.path.join(os.path.dirname(__file__), "general", "EPPlus.dll"))
from OfficeOpenXml import ExcelPackage
from OfficeOpenXml.Style import ExcelFillStyle, ExcelHorizontalAlignment

TITLE = "Filter Export"
FORMAT_VERSION = "1"

STRING_OPS = {
    "FilterStringEquals": "equals", "FilterStringContains": "contains",
    "FilterStringBeginsWith": "begins_with", "FilterStringEndsWith": "ends_with",
    "FilterStringGreater": "greater", "FilterStringGreaterOrEqual": "greater_or_equal",
    "FilterStringLess": "less", "FilterStringLessOrEqual": "less_or_equal",
}
NUMERIC_OPS = {
    "FilterNumericEquals": "equals", "FilterNumericGreater": "greater",
    "FilterNumericGreaterOrEqual": "greater_or_equal", "FilterNumericLess": "less",
    "FilterNumericLessOrEqual": "less_or_equal",
}
INVERSE_OPS = {
    "equals": "not_equals", "contains": "not_contains", "begins_with": "not_begins_with",
    "ends_with": "not_ends_with", "has_value": "has_no_value",
}
OPERATORS = ["equals", "not_equals", "contains", "not_contains", "begins_with",
             "not_begins_with", "ends_with", "not_ends_with", "greater", "greater_or_equal",
             "less", "less_or_equal", "has_value", "has_no_value"]

RULE_HEADERS = ["FilterName", "Logic", "Group", "Parameter", "ParameterLabel",
                "ParameterKind", "SharedGUID", "Operator", "Value", "RawValue"]

# (header, group) - group picks the header colour
OVERRIDE_HEADERS = [
    ("FilterName", "id"), ("Target", "id"), ("TargetType", "id"), ("Order", "id"),
    ("Enabled", "gen"), ("Visible", "gen"), ("Halftone", "gen"), ("Transparency", "gen"),
    ("DetailLevel", "gen"),
    ("ProjLineColor", "proj"), ("ProjLinePattern", "proj"), ("ProjLineWeight", "proj"),
    ("SurfFgPattern", "surf"), ("SurfFgColor", "surf"),
    ("SurfBgPattern", "surf"), ("SurfBgColor", "surf"),
    ("CutLineColor", "cut"), ("CutLinePattern", "cut"), ("CutLineWeight", "cut"),
    ("CutFgPattern", "cut"), ("CutFgColor", "cut"),
    ("CutBgPattern", "cut"), ("CutBgColor", "cut"),
]
GROUP_BG = {"id": "#7F7F7F", "gen": "#595959", "proj": "#2F5597", "surf": "#548235",
            "cut": "#C55A11"}
HEADER_BG = "#404040"
MARK_BG = "#C6EFCE"
ISSUE_BG = {"Warning": "#FCE4D6", "Info": "#DDEBF7"}


# ---------------------------------------------------------
# Small helpers
# ---------------------------------------------------------
def natural_key(text):
    return [(0, int(t)) if t.isdigit() else (1, t.lower())
            for t in re.split(r"(\d+)", text or u"") if t != u""]


def enum_name(enum_type, value):
    try:
        return System.Enum.ToObject(enum_type, int(value)).ToString()
    except Exception:
        return str(value)


def yes_no(flag):
    return "yes" if flag else "no"


def hex_color(color):
    try:
        if color is not None and color.IsValid:
            return "{:02X}{:02X}{:02X}".format(color.Red, color.Green, color.Blue)
    except Exception:
        pass
    return ""


def xl_color(hex_code):
    h = hex_code.lstrip("#")
    return DColor.FromArgb(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def fill(rng, hex_code):
    rng.Style.Fill.PatternType = ExcelFillStyle.Solid
    rng.Style.Fill.BackgroundColor.SetColor(xl_color(hex_code))


def is_invalid(eid):
    return eid is None or eid == ElementId.InvalidElementId


class Issues(object):
    def __init__(self):
        self.rows = []

    def warn(self, sheet, filter_name, text, target=""):
        self.rows.append(("Warning", sheet, filter_name, target, text))

    def info(self, sheet, filter_name, text, target=""):
        self.rows.append(("Info", sheet, filter_name, target, text))


# ---------------------------------------------------------
# Categories
# ---------------------------------------------------------
def category_label(doc, cid):
    key = id_value(cid)
    bic = enum_name(BuiltInCategory, key) if key < 0 else ""
    cat = Category.GetCategory(doc, cid)
    if cat is not None:
        return cat.Name, bic
    try:
        return LabelUtils.GetLabelFor(System.Enum.ToObject(BuiltInCategory, int(key))), bic
    except Exception:
        return bic or str(key), bic


def collect_categories(doc, filters):
    """All filterable categories (+ any a filter uses), sorted by display name."""
    ids = {}
    for cid in ParameterFilterUtilities.GetAllFilterableCategories():
        ids[id_value(cid)] = cid
    for f in filters:
        for cid in f.GetCategories():
            ids.setdefault(id_value(cid), cid)
    rows = []
    for key, cid in ids.items():
        name, bic = category_label(doc, cid)
        rows.append((name, bic, key))
    rows.sort(key=lambda r: natural_key(r[0]))
    return rows


# ---------------------------------------------------------
# Parameters
# ---------------------------------------------------------
class ParamInfo(object):
    def __init__(self, ident, label, kind, guid="", spec=None):
        self.ident, self.label, self.kind, self.guid, self.spec = ident, label, kind, guid, spec


class Params(object):
    def __init__(self, doc):
        self.doc = doc
        self.cache = {}
        self.name_count = {}
        for pe in FilteredElementCollector(doc).OfClass(ParameterElement):
            d = pe.GetDefinition()
            if d is not None:
                self.name_count[d.Name] = self.name_count.get(d.Name, 0) + 1

    def get(self, pid, cat_ids):
        key = id_value(pid)
        if key in self.cache:
            return self.cache[key]
        if key < 0:
            info = self._builtin(key, cat_ids)
        else:
            info = self._project(pid, key)
        self.cache[key] = info
        return info

    def _builtin(self, key, cat_ids):
        bip = System.Enum.ToObject(BuiltInParameter, int(key))
        ident = bip.ToString()
        try:
            label = LabelUtils.GetLabelFor(bip)
        except Exception:
            label = ident
        return ParamInfo(ident, label, "BuiltIn", spec=self._builtin_spec(bip, cat_ids))

    def _builtin_spec(self, bip, cat_ids):
        """Built-in parameters have no definition element: read the spec from an element."""
        if not cat_ids:
            return None
        try:
            collector = FilteredElementCollector(self.doc).WherePasses(
                ElementMulticategoryFilter(List[ElementId](cat_ids)))
        except Exception:
            return None
        for i, e in enumerate(collector):
            if i > 200:
                break
            for el in (e, self.doc.GetElement(e.GetTypeId())):
                if el is None:
                    continue
                p = el.get_Parameter(bip)
                if p is not None:
                    try:
                        return p.Definition.GetDataType()
                    except Exception:
                        return None
        return None

    def _project(self, pid, key):
        pe = self.doc.GetElement(pid)
        if pe is None:
            return ParamInfo("<missing id {}>".format(key), "", "Missing")
        d = pe.GetDefinition()
        guid, kind = "", "Project"
        if isinstance(pe, SharedParameterElement):
            kind, guid = "Shared", str(pe.GuidValue)
        try:
            spec = d.GetDataType()
        except Exception:
            spec = None
        return ParamInfo(d.Name, d.Name, kind, guid, spec)


# ---------------------------------------------------------
# Rules
# ---------------------------------------------------------
def format_number(doc, spec, value):
    if spec is None:
        return None
    try:
        return UnitFormatUtils.Format(doc.GetUnits(), spec, value, True)
    except Exception:
        return None


def is_yes_no(spec):
    try:
        return spec is not None and spec == SpecTypeId.Boolean.YesNo
    except Exception:
        return False


def describe_rule(doc, rule, info, fname, issues):
    """-> (operator, value text, raw value)"""
    tname = rule.GetType().Name
    inverted = False
    if tname == "FilterInverseRule":
        rule = rule.GetInnerRule()
        tname = rule.GetType().Name
        inverted = True

    op, value, raw = None, "", ""
    if tname == "FilterStringRule":
        op = STRING_OPS.get(rule.GetEvaluator().GetType().Name)
        value = raw = rule.RuleString
    elif tname in ("FilterIntegerRule", "FilterDoubleRule", "FilterElementIdRule"):
        op = NUMERIC_OPS.get(rule.GetEvaluator().GetType().Name)
        if tname == "FilterIntegerRule":
            raw = rule.RuleValue
            value = yes_no(raw == 1) if is_yes_no(info.spec) else str(raw)
        elif tname == "FilterDoubleRule":
            raw = rule.RuleValue
            value = format_number(doc, info.spec, raw)
            if value is None:
                value = repr(raw)
                issues.warn("Rules", fname, u"{}: unit unknown, value written in internal "
                            u"units (feet)".format(info.label))
        else:
            eid = rule.RuleValue
            raw = id_value(eid)
            el = doc.GetElement(eid) if not is_invalid(eid) else None
            if el is not None:
                value = element_name(el) or getattr(el, "Name", "")
            elif raw < 0:
                cat = Category.GetCategory(doc, eid)
                value = cat.Name if cat else str(raw)
            else:
                value = "<none>" if is_invalid(eid) else str(raw)
                if not is_invalid(eid):
                    issues.warn("Rules", fname, u"{}: rule points to element {} which no "
                                u"longer exists".format(info.label, raw))
    elif tname == "HasValueFilterRule":
        op = "has_value"
    elif tname == "HasNoValueFilterRule":
        op = "has_no_value"
    elif tname == "SharedParameterApplicableRule":
        op = "parameter_exists"
        value = raw = rule.ParameterName
        issues.warn("Rules", fname, "'parameter exists' rule - not in the planned format")
    else:
        issues.warn("Rules", fname, "unsupported rule type {}".format(tname))
        return tname, "", ""

    if op is None:
        issues.warn("Rules", fname, "unknown evaluator in {}".format(tname))
        op = "?"
    if inverted:
        new_op = INVERSE_OPS.get(op)
        if new_op is None:
            new_op = "not_" + op
            issues.warn("Rules", fname, "inverted '{}' has no planned operator".format(op))
        op = new_op
    return op, value, raw


def rule_param_id(rule):
    try:
        return rule.GetRuleParameter()
    except Exception:
        try:
            return rule.GetInnerRule().GetRuleParameter()
        except Exception:
            return None


def collect_rules(doc, f, params, issues):
    fname = f.Name
    cat_ids = list(f.GetCategories())
    rows = []

    def emit(rule, logic, path, epf_inverted):
        pid = rule_param_id(rule)
        if pid is None:
            info = ParamInfo("", "", "")
        else:
            info = params.get(pid, cat_ids)
            if info.kind == "Missing":
                issues.warn("Rules", fname, "rule uses a deleted parameter ({})".format(info.ident))
            elif info.kind != "BuiltIn" and params.name_count.get(info.ident, 0) > 1:
                issues.warn("Rules", fname, u"parameter name '{}' is used by more than one "
                            u"parameter - import must use the GUID".format(info.ident))
        op, value, raw = describe_rule(doc, rule, info, fname, issues)
        if epf_inverted:
            op = "NOT " + op
            issues.warn("Rules", fname, "inverted parameter filter (NOT) on {}".format(info.label))
        rows.append([fname, logic, ".".join(str(p) for p in path), info.ident, info.label,
                     info.kind, info.guid, op, value, raw])

    def walk(efilter, path):
        tname = efilter.GetType().Name
        logic = "OR" if tname == "LogicalOrFilter" else "AND"
        if path:
            issues.warn("Rules", fname, "nested {} group {}".format(logic, ".".join(str(p) for p in path)))
        if tname in ("LogicalAndFilter", "LogicalOrFilter"):
            children = list(efilter.GetFilters())
        else:
            children = [efilter]
        sub = 0
        for child in children:
            cname = child.GetType().Name
            if cname in ("LogicalAndFilter", "LogicalOrFilter"):
                sub += 1
                walk(child, path + [sub])
            elif cname == "ElementParameterFilter":
                rules = list(child.GetRules())
                if len(rules) > 1 and logic == "OR":
                    issues.warn("Rules", fname, "{} rules joined by AND inside an OR group"
                                .format(len(rules)))
                for rule in rules:
                    emit(rule, logic, path, child.Inverted)
            else:
                issues.warn("Rules", fname, "unsupported filter part {}".format(cname))

    efilter = f.GetElementFilter()
    if efilter is None:
        issues.info("Rules", fname, "no rules (category-only filter)")
    else:
        walk(efilter, [])
    return rows


# ---------------------------------------------------------
# Overrides
# ---------------------------------------------------------
class Patterns(object):
    def __init__(self, doc):
        self.doc = doc
        self.solid_line = id_value(LinePatternElement.GetSolidPatternId())
        self.names = {}

    def name(self, eid):
        if is_invalid(eid):
            return ""
        key = id_value(eid)
        if key == self.solid_line:
            return "Solid"
        if key not in self.names:
            el = self.doc.GetElement(eid)
            self.names[key] = el.Name if el is not None else "<missing {}>".format(key)
        return self.names[key]


def weight(value):
    return value if value is not None and value > 0 else ""


def filters_from_template(doc, view):
    """True when the view's filters are controlled by its template."""
    tid = view.ViewTemplateId
    if is_invalid(tid):
        return False
    template = doc.GetElement(tid)
    if template is None:
        return False
    try:
        free = set(id_value(i) for i in template.GetNonControlledTemplateParameterIds())
        return int(BuiltInParameter.VIS_GRAPHICS_FILTERS) not in free
    except Exception:
        return True


def ask_targets(doc, issues):
    templates, views, skipped = [], [], 0
    for v in FilteredElementCollector(doc).OfClass(View):
        try:
            if not v.AreGraphicsOverridesAllowed() or v.GetFilters().Count == 0:
                continue
        except Exception:
            continue
        if v.IsTemplate:
            templates.append(v)
        elif filters_from_template(doc, v):
            skipped += 1
        else:
            views.append(v)
    if skipped:
        issues.info("Overrides", "", "{} views not listed: their filters come from their "
                    "template".format(skipped))

    labels = {}
    for v in sorted(templates, key=lambda x: natural_key(x.Name)):
        labels["[Template] " + v.Name] = v
    for v in sorted(views, key=lambda x: natural_key(x.Name)):
        labels[u"[{}] {}".format(v.ViewType, v.Name)] = v
    if not labels:
        return []
    order = [k for k in labels if k.startswith("[Template]")]
    order += sorted([k for k in labels if not k.startswith("[Template]")], key=natural_key)
    picked = forms.SelectFromList.show(order, title="Overrides: pick views / templates "
                                       "(cancel = skip overrides)", multiselect=True,
                                       button_name="Export")
    return [labels[k] for k in (picked or [])]


def collect_overrides(doc, targets, rule_ids, issues):
    pats = Patterns(doc)
    rows, color_cells = [], []
    seen_names = {}
    for v in targets:
        seen_names.setdefault(v.Name, []).append(v)
    for name, vs in seen_names.items():
        if len(vs) > 1:
            issues.warn("Overrides", "", "{} picked views share this name - Target alone is "
                        "not unique".format(len(vs)), target=name)

    for v in targets:
        ttype = "Template" if v.IsTemplate else str(v.ViewType)
        try:
            ordered = list(v.GetOrderedFilters())
        except Exception:
            ordered = list(v.GetFilters())
        for i, fid in enumerate(ordered):
            f = doc.GetElement(fid)
            if f is None:
                continue
            if id_value(fid) not in rule_ids:
                issues.info("Overrides", f.Name, "selection filter - overrides not exported",
                            target=v.Name)
                continue
            o = v.GetFilterOverrides(fid)
            try:
                enabled = yes_no(v.GetIsFilterEnabled(fid))
            except Exception:
                enabled = ""
            detail = str(o.DetailLevel)
            row = [f.Name, v.Name, ttype, i + 1, enabled, yes_no(v.GetFilterVisibility(fid)),
                   "yes" if o.Halftone else "", o.Transparency or "",
                   "" if detail == "Undefined" else detail,
                   hex_color(o.ProjectionLineColor), pats.name(o.ProjectionLinePatternId),
                   weight(o.ProjectionLineWeight),
                   pats.name(o.SurfaceForegroundPatternId), hex_color(o.SurfaceForegroundPatternColor),
                   pats.name(o.SurfaceBackgroundPatternId), hex_color(o.SurfaceBackgroundPatternColor),
                   hex_color(o.CutLineColor), pats.name(o.CutLinePatternId), weight(o.CutLineWeight),
                   pats.name(o.CutForegroundPatternId), hex_color(o.CutForegroundPatternColor),
                   pats.name(o.CutBackgroundPatternId), hex_color(o.CutBackgroundPatternColor)]
            rows.append(row)
    return rows


# ---------------------------------------------------------
# Lists
# ---------------------------------------------------------
def collect_lists(doc):
    line = ["Solid"] + sorted(set(p.Name for p in FilteredElementCollector(doc)
                                  .OfClass(LinePatternElement)), key=natural_key)
    fills = sorted(set(u"{}|{}".format(p.Name, p.GetFillPattern().Target)
                       for p in FilteredElementCollector(doc).OfClass(FillPatternElement)),
                   key=natural_key)
    return [("LinePatterns", line),
            ("FillPatterns", [x.split("|")[0] for x in fills]),
            ("FillTarget", [x.split("|")[1] for x in fills]),
            ("Operators", OPERATORS),
            ("Logic", ["AND", "OR"]),
            ("DetailLevel", ["Coarse", "Medium", "Fine"])]


# ---------------------------------------------------------
# Excel
# ---------------------------------------------------------
def style_header(ws, ncol, bg=HEADER_BG):
    head = ws.Cells[1, 1, 1, ncol]
    head.Style.Font.Bold = True
    head.Style.Font.Color.SetColor(xl_color("#FFFFFF"))
    fill(head, bg)


def write_table(ws, headers, rows, freeze_cols=1):
    for j, h in enumerate(headers):
        ws.Cells[1, j + 1].Value = h
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            if value != "" and value is not None:
                ws.Cells[i + 2, j + 1].Value = value
    ncol, last = len(headers), max(len(rows) + 1, 1)
    style_header(ws, ncol)
    ws.View.FreezePanes(2, freeze_cols + 1)
    ws.Cells[1, 1, last, ncol].AutoFilter = True
    try:
        ws.Cells[1, 1, last, ncol].AutoFitColumns(8, 60)
    except Exception:
        pass
    return last


def write_categories(ws, categories, filters):
    ws.Cells[1, 1].Value = "Category"
    ws.Cells[1, 2].Value = "BuiltInCategory"
    row_of = dict((key, i + 2) for i, (_, _, key) in enumerate(categories))
    for i, (name, bic, _) in enumerate(categories):
        ws.Cells[i + 2, 1].Value = name
        ws.Cells[i + 2, 2].Value = bic
    for j, f in enumerate(filters):
        col = j + 3
        ws.Cells[1, col].Value = f.Name
        for cid in f.GetCategories():
            r = row_of.get(id_value(cid))
            if r:
                cell = ws.Cells[r, col]
                cell.Value = "x"
                fill(cell, MARK_BG)
    ncol, last = 2 + len(filters), len(categories) + 1
    style_header(ws, ncol)
    if filters:
        head = ws.Cells[1, 3, 1, ncol]
        head.Style.TextRotation = 90
        head.Style.HorizontalAlignment = ExcelHorizontalAlignment.Center
        ws.Cells[2, 3, last, ncol].Style.HorizontalAlignment = ExcelHorizontalAlignment.Center
        for j in range(len(filters)):
            ws.Column(j + 3).Width = 4
        longest = max(len(f.Name) for f in filters)
        ws.Row(1).Height = min(409, 7 * longest + 12)
    ws.View.FreezePanes(2, 3)
    ws.Cells[1, 1, last, ncol].AutoFilter = True
    ws.Column(1).Width = 34
    ws.Column(2).Width = 34


def write_overrides(ws, rows):
    headers = [h for h, _ in OVERRIDE_HEADERS]
    last = write_table(ws, headers, rows, freeze_cols=2)
    for j, (h, group) in enumerate(OVERRIDE_HEADERS):
        fill(ws.Cells[1, j + 1], GROUP_BG[group])
        if h.endswith("Color"):
            for i, row in enumerate(rows):
                code = row[j]
                if code:
                    cell = ws.Cells[i + 2, j + 1]
                    fill(cell, code)
                    c = xl_color(code)
                    dark = (0.299 * c.R + 0.587 * c.G + 0.114 * c.B) < 140
                    cell.Style.Font.Color.SetColor(xl_color("#FFFFFF" if dark else "#000000"))
    return last


def write_lists(ws, lists):
    for j, (name, values) in enumerate(lists):
        ws.Cells[1, j + 1].Value = name
        for i, v in enumerate(values):
            ws.Cells[i + 2, j + 1].Value = v
    style_header(ws, len(lists))
    ws.View.FreezePanes(2, 1)
    try:
        ws.Cells.AutoFitColumns(8, 50)
    except Exception:
        pass


def write_issues(ws, issues, doc):
    rows = sorted(issues.rows, key=lambda r: (r[0] != "Warning", r[1], natural_key(r[2])))
    write_table(ws, ["Severity", "Sheet", "Filter", "Target", "Issue"], rows)
    for i, row in enumerate(rows):
        fill(ws.Cells[i + 2, 1, i + 2, 5], ISSUE_BG[row[0]])
    meta = len(rows) + 3
    for k, (label, value) in enumerate([
            ("format", FORMAT_VERSION), ("document", doc.Title),
            ("exported", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))]):
        ws.Cells[meta + k, 1].Value = label
        ws.Cells[meta + k, 2].Value = value


def export_xlsx(path, doc, categories, filters, rules, overrides, lists, issues):
    pkg = ExcelPackage()
    try:
        book = pkg.Workbook
        write_categories(book.Worksheets.Add("Categories"), categories, filters)
        write_table(book.Worksheets.Add("Rules"), RULE_HEADERS, rules)
        write_overrides(book.Worksheets.Add("Overrides"), overrides)
        write_lists(book.Worksheets.Add("Lists"), lists)
        write_issues(book.Worksheets.Add("Issues"), issues, doc)
        pkg.SaveAs(FileInfo(path))
    finally:
        pkg.Dispose()


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------
def main():
    doc = revit.doc
    issues = Issues()

    filters = sorted(FilteredElementCollector(doc).OfClass(ParameterFilterElement),
                     key=lambda f: natural_key(f.Name))
    selection = list(FilteredElementCollector(doc).OfClass(SelectionFilterElement))
    if not filters:
        forms.alert("No rule-based filters in this model.", title=TITLE, exitscript=True)
    for s in selection:
        issues.info("Categories", s.Name, "selection filter (element list) - not exported")

    used = set()
    for v in FilteredElementCollector(doc).OfClass(View):
        try:
            if v.AreGraphicsOverridesAllowed():
                used.update(id_value(i) for i in v.GetFilters())
        except Exception:
            pass
    for f in filters:
        if id_value(f.Id) not in used:
            issues.info("Categories", f.Name, "not applied to any view or template")

    targets = ask_targets(doc, issues)

    path = forms.save_file(file_ext="xlsx", title="Export filters to Excel",
                           default_name=re.sub(r'[\\/:*?"<>|]+', "_", "Filters_" + doc.Title))
    if not path:
        script.exit()
    if not path.lower().endswith(".xlsx"):
        path += ".xlsx"

    params = Params(doc)
    categories = collect_categories(doc, filters)
    rules = []
    for f in filters:
        rules.extend(collect_rules(doc, f, params, issues))
    rule_ids = set(id_value(f.Id) for f in filters)
    overrides = collect_overrides(doc, targets, rule_ids, issues)
    lists = collect_lists(doc)

    try:
        export_xlsx(path, doc, categories, filters, rules, overrides, lists, issues)
    except Exception as ex:
        forms.alert(u"Export failed. If the file is open in Excel, close it and try again.\n\n{}"
                    .format(ex), title=TITLE)
        return

    warnings = sum(1 for r in issues.rows if r[0] == "Warning")
    msg = (u"{} filters, {} rules, {} override rows exported to:\n{}\n\n{} warnings, {} notes "
           u"(see the Issues sheet).\n\nOpen it now?").format(
        len(filters), len(rules), len(overrides), path, warnings, len(issues.rows) - warnings)
    if forms.alert(msg, title=TITLE, yes=True, no=True):
        os.startfile(path)
