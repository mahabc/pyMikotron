# -*- coding: utf-8 -*-
"""OPGen shared logic - used by OPGen (create) and OPUpdate (update) buttons.

Creates openings where pipes, ducts, conduits and cable trays (local or
linked) pass through walls, floors, ceilings and roofs. Hosts are always
elements of the active (local) document.

Shape rule (from the element "Size" value):
    "25"      -> single number -> round element       -> round opening
    "25x25"   -> two numbers   -> rectangular element -> rectangular opening

Opening methods:
    Floors / ceilings / roofs : native Opening, round (circle) or polygon profile
    Walls, rectangular        : native rectangular wall Opening
    Walls, round              : circle added to the wall's profile sketch;
                                walls that cannot have a profile sketch
                                (e.g. curved walls) get a rectangular opening
                                that encloses the circle.

Offset = clearance added on EACH side of the element (default 5 mm).

Nothing here holds a module-level document reference: with pyRevit rocket
mode this module stays loaded between runs, so all document access goes
through a Generator instance created per run.
"""
import datetime
import math
import re

import clr
clr.AddReference("System")
from System.Collections.Generic import List

from pyrevit import forms, HOST_APP

from Autodesk.Revit.DB import (
    Arc, BuiltInCategory, BuiltInParameter, Ceiling, ConnectorType,
    CurveArray, CurveElement, ElementId, ElementMulticategoryFilter,
    BoundingBoxIntersectsFilter, FailureProcessingResult, FailureSeverity,
    FilteredElementCollector, Floor, GeometryInstance, IFailuresPreprocessor,
    Line, LocationCurve, Options, Outline, RevitLinkInstance, RoofBase,
    SketchEditScope, Solid, SolidCurveIntersectionOptions, SpecTypeId,
    Transaction, TransactionStatus, Transform, UnitTypeId, UnitUtils,
    ViewDetailLevel, Wall, WallKind, XYZ,
)
from Autodesk.Revit.DB.Plumbing import Pipe
from Autodesk.Revit.DB.Mechanical import Duct
from Autodesk.Revit.DB.Electrical import Conduit, CableTray


BIP = BuiltInParameter
SHORT_TOL = HOST_APP.app.ShortCurveTolerance
ROUND_SAMPLES = 32
MIN_CROSS_ANGLE_COS = 0.26   # ~75 deg: skip elements running along/inside a host
DEFAULT_OFFSET_MM = 5.0
COMMENT_PREFIX = "OPGen: "


def mm_to_ft(v):
    return UnitUtils.ConvertToInternalUnits(v, UnitTypeId.Millimeters)


def ft_to_mm(v):
    return UnitUtils.ConvertFromInternalUnits(v, UnitTypeId.Millimeters)


def eid_int(eid):
    """ElementId -> plain Python int. Revit 2024+ uses .Value, older .IntegerValue."""
    try:
        return int(eid.Value)
    except AttributeError:
        return int(eid.IntegerValue)


# ---------------------------------------------------------------------------
# MEP definitions
# ---------------------------------------------------------------------------
# key, label, class, round size params, rect (width, height) params
MEP_TYPES = [
    ("pipe", "Pipes", Pipe,
     [BIP.RBS_PIPE_OUTER_DIAMETER, BIP.RBS_PIPE_DIAMETER_PARAM],
     None),
    ("duct", "Ducts", Duct,
     [BIP.RBS_CURVE_DIAMETER_PARAM],
     (BIP.RBS_CURVE_WIDTH_PARAM, BIP.RBS_CURVE_HEIGHT_PARAM)),
    ("conduit", "Conduits", Conduit,
     [BIP.RBS_CONDUIT_OUTER_DIAM_PARAM, BIP.RBS_CONDUIT_DIAMETER_PARAM],
     None),
    ("tray", "Cable Trays", CableTray,
     [],
     (BIP.RBS_CABLETRAY_WIDTH_PARAM, BIP.RBS_CABLETRAY_HEIGHT_PARAM)),
]
MEP_BY_KEY = dict((t[0], t) for t in MEP_TYPES)
CATEGORY_KEYS = [t[0] for t in MEP_TYPES]
CATEGORY_LABELS = dict((t[0], t[1]) for t in MEP_TYPES)
COMMENT_LABELS = {"pipe": "Pipe", "duct": "Duct",
                  "conduit": "Conduit", "tray": "Cable Tray"}


def default_offsets(stored=None):
    """Offsets per category (mm), last-used values where available."""
    offsets = dict((k, DEFAULT_OFFSET_MM) for k in CATEGORY_KEYS)
    for k, v in (stored or {}).items():
        if k in offsets:
            try:
                offsets[k] = float(v)
            except (TypeError, ValueError):
                pass
    return offsets


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------
DIALOG_TEMPLATE = u"""
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="%%TITLE%%"
        SizeToContent="WidthAndHeight" ResizeMode="NoResize"
        WindowStartupLocation="CenterScreen" ShowInTaskbar="False">
  <StackPanel Margin="16">
    <TextBlock Text="%%HEADING%%" FontWeight="Bold" Margin="0,0,0,4"/>
    <TextBlock Text="Clearance added around each element on every side."
               Foreground="Gray" Margin="0,0,0,10"/>
    <Grid>
      <Grid.ColumnDefinitions>
        <ColumnDefinition Width="140"/>
        <ColumnDefinition Width="90"/>
      </Grid.ColumnDefinitions>
      <Grid.RowDefinitions>
%%ROWDEFS%%
      </Grid.RowDefinitions>
%%ROWS%%
    </Grid>
    <TextBlock x:Name="tb_error" Foreground="Firebrick" Margin="0,8,0,0"
               TextWrapping="Wrap" MaxWidth="230"/>
    <StackPanel Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,12,0,0">
      <Button Content="%%BUTTON%%" MinWidth="110" Height="26" IsDefault="True"
              Click="ok_click" Margin="0,0,8,0" Padding="8,0"/>
      <Button Content="Cancel" Width="70" Height="26" IsCancel="True"/>
    </StackPanel>
  </StackPanel>
</Window>
"""


def _dialog_xaml(title, heading, button_text, defaults, counts):
    rowdefs, rows = [], []
    for i, key in enumerate(CATEGORY_KEYS):
        rowdefs.append(u'        <RowDefinition Height="30"/>')
        label = CATEGORY_LABELS[key]
        if counts is None:
            rows.append(u'      <TextBlock Grid.Row="{0}" Text="{1}" '
                        u'VerticalAlignment="Center"/>'.format(i, label))
        else:
            n = counts.get(key, 0)
            rows.append(u'      <CheckBox Grid.Row="{0}" x:Name="cb_{1}" '
                        u'Content="{2} ({3})" VerticalAlignment="Center" '
                        u'IsEnabled="{4}"/>'.format(i, key, label, n,
                                                    "True" if n else "False"))
        rows.append(u'      <TextBox Grid.Row="{0}" Grid.Column="1" x:Name="tb_{1}" '
                    u'Text="{2:g}" Height="24"/>'.format(i, key, defaults[key]))
    return (DIALOG_TEMPLATE
            .replace("%%TITLE%%", title)
            .replace("%%HEADING%%", heading)
            .replace("%%BUTTON%%", button_text)
            .replace("%%ROWDEFS%%", u"\n".join(rowdefs))
            .replace("%%ROWS%%", u"\n".join(rows)))


class OffsetDialog(forms.WPFWindow):
    """Offset per category. With `counts`, also a checkbox per category.

    After show_dialog(): .offsets = {key: mm} (None if cancelled),
    .selected = list of ticked keys (all keys when no checkboxes).
    """

    def __init__(self, title, heading, button_text, defaults, counts=None):
        self._with_checks = counts is not None
        forms.WPFWindow.__init__(
            self, _dialog_xaml(title, heading, button_text, defaults, counts),
            literal_string=True)
        self.offsets = None
        self.selected = None

    def ok_click(self, sender, args):
        values = {}
        for key in CATEGORY_KEYS:
            box = getattr(self, "tb_" + key)
            try:
                val = float(box.Text.strip().replace(",", "."))
            except ValueError:
                self.tb_error.Text = "Enter a number for every offset."
                return
            if val < 0:
                self.tb_error.Text = "Offsets cannot be negative."
                return
            values[key] = val
        if self._with_checks:
            selected = [k for k in CATEGORY_KEYS
                        if getattr(self, "cb_" + k).IsChecked]
            if not selected:
                self.tb_error.Text = "Tick at least one category to update."
                return
        else:
            selected = list(CATEGORY_KEYS)
        self.offsets = values
        self.selected = selected
        self.DialogResult = True
        self.Close()


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------
class LenientFailures(IFailuresPreprocessor):
    """Drop warnings; resolve errors (Revit deletes the offending opening)."""

    def __init__(self):
        self.messages = []

    def PreprocessFailures(self, fa):
        result = FailureProcessingResult.Continue
        for f in fa.GetFailureMessages():
            if f.GetSeverity() == FailureSeverity.Warning:
                fa.DeleteWarning(f)
            elif f.HasResolutions():
                self.messages.append(f.GetDescriptionText())
                fa.ResolveFailure(f)
                result = FailureProcessingResult.ProceedWithCommit
        return result


class StrictFailures(IFailuresPreprocessor):
    """Drop warnings; roll back on any error (used for sketch edits)."""

    def __init__(self):
        self.failed = False

    def PreprocessFailures(self, fa):
        for f in fa.GetFailureMessages():
            if f.GetSeverity() == FailureSeverity.Warning:
                fa.DeleteWarning(f)
            else:
                self.failed = True
        if self.failed:
            return FailureProcessingResult.ProceedWithRollBack
        return FailureProcessingResult.Continue


# ---------------------------------------------------------------------------
# MEP element reading
# ---------------------------------------------------------------------------
RECT_RE = re.compile(u"\\d[^\\d]*[x×X][^\\d]*\\d")
NUM_RE = re.compile(u"\\d+(?:[.,]\\d+)?")


def param_value(el, bip):
    p = el.get_Parameter(bip)
    if p and p.HasValue:
        v = p.AsDouble()
        if v > 0:
            return v
    return None


def doc_length_unit(d):
    try:
        return d.GetUnits().GetFormatOptions(SpecTypeId.Length).GetUnitTypeId()
    except Exception:
        return UnitTypeId.Millimeters


def read_shape(el, src_doc, round_bips, rect_bips):
    """Return ('round', d) or ('rect', w, h) in feet, or None.

    Shape comes from the Size string; dimensions come from the element's
    size parameters, falling back to the numbers in the Size string.
    """
    size_p = el.get_Parameter(BIP.RBS_CALCULATED_SIZE)
    size = (size_p.AsString() or u"") if size_p else u""
    nums = [float(n.replace(",", ".")) for n in NUM_RE.findall(size)]
    unit = doc_length_unit(src_doc)

    if size and RECT_RE.search(size):
        w = h = None
        if rect_bips:
            w = param_value(el, rect_bips[0])
            h = param_value(el, rect_bips[1])
        if not (w and h) and len(nums) >= 2:
            w = UnitUtils.ConvertToInternalUnits(nums[0], unit)
            h = UnitUtils.ConvertToInternalUnits(nums[1], unit)
        return ("rect", w, h) if (w and h) else None

    if nums or not size:
        dia = None
        for bip in round_bips:
            dia = param_value(el, bip)
            if dia:
                break
        if not dia and nums:
            dia = UnitUtils.ConvertToInternalUnits(nums[0], unit)
        return ("round", dia) if dia else None
    return None


def cross_axes(el, transform, d):
    """Width axis (u) and height axis (v) of the cross-section, host coords."""
    u = None
    try:
        for c in el.ConnectorManager.Connectors:
            if c.ConnectorType == ConnectorType.End:
                u = transform.OfVector(c.CoordinateSystem.BasisX)
                break
    except Exception:
        u = None
    if u is None or abs(u.DotProduct(d)) > 0.99:
        u = XYZ.BasisX if abs(d.Z) > 0.99 else XYZ.BasisZ.CrossProduct(d)
    u = (u - d.Multiply(u.DotProduct(d))).Normalize()
    v = d.CrossProduct(u).Normalize()
    return u, v


class MepItem(object):
    def __init__(self, key, el, source, source_uid, line, shape, u, v, offset):
        self.key = key
        self.label = CATEGORY_LABELS[key]
        self.el_id = el.Id
        self.uid = el.UniqueId
        self.source = source            # "Local" or link instance name
        self.source_uid = source_uid    # None (local) or link instance UniqueId
        self.line = line                # host-document coordinates
        self.d = line.Direction.Normalize()
        self.shape = shape
        self.u = u
        self.v = v
        self.offset = offset            # feet

    @property
    def ident(self):
        return (self.source_uid or "", self.uid)

    @property
    def is_round(self):
        return self.shape[0] == "round"

    @property
    def half_extent(self):
        if self.is_round:
            return self.shape[1] / 2.0 + self.offset
        return math.hypot(self.shape[1], self.shape[2]) / 2.0 + self.offset

    def size_mm(self):
        return [round(ft_to_mm(v), 1) for v in self.shape[1:]]

    def section_points(self, center):
        """Outline of the (offset) cross-section at a point on the axis."""
        pts = []
        if self.is_round:
            r = self.shape[1] / 2.0 + self.offset
            for i in range(ROUND_SAMPLES):
                a = 2.0 * math.pi * i / ROUND_SAMPLES
                pts.append(center + self.u.Multiply(r * math.cos(a))
                           + self.v.Multiply(r * math.sin(a)))
        else:
            hw = self.shape[1] / 2.0 + self.offset
            hh = self.shape[2] / 2.0 + self.offset
            for sw, sh in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
                pts.append(center + self.u.Multiply(sw * hw)
                           + self.v.Multiply(sh * hh))
        return pts

    def describe(self, output):
        if self.source_uid is None:
            return output.linkify(self.el_id)
        return "{} [{}]".format(eid_int(self.el_id), self.source)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
HOST_CATS = List[BuiltInCategory]([
    BuiltInCategory.OST_Walls, BuiltInCategory.OST_Floors,
    BuiltInCategory.OST_Ceilings, BuiltInCategory.OST_Roofs,
])


def host_kind(el):
    if isinstance(el, Wall):
        try:
            if el.WallType.Kind != WallKind.Basic:
                return None     # curtain / stacked parent
        except Exception:
            return None
        return "wall"
    if isinstance(el, Floor):
        return "floor"
    if isinstance(el, Ceiling):
        return "ceiling"
    if isinstance(el, RoofBase):
        return "roof"
    return None


def penetrations(solids, line):
    """Merged (entry, exit) intervals where the axis is inside the host."""
    origin = line.GetEndPoint(0)
    d = line.Direction.Normalize()
    opts = SolidCurveIntersectionOptions()
    spans = []
    for s in solids:
        try:
            res = s.IntersectWithCurve(line, opts)
        except Exception:
            continue
        for i in range(res.SegmentCount):
            seg = res.GetCurveSegment(i)
            t0 = (seg.GetEndPoint(0) - origin).DotProduct(d)
            t1 = (seg.GetEndPoint(1) - origin).DotProduct(d)
            spans.append((min(t0, t1), max(t0, t1)))
    spans.sort()
    merged = []
    gap = mm_to_ft(1.0)
    for a, b in spans:
        if merged and a <= merged[-1][1] + gap:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(origin + d.Multiply(a), origin + d.Multiply(b))
            for a, b in merged if b - a > SHORT_TOL]


def wall_axes(wall, point):
    """Wall normal and horizontal along-wall axis at a point."""
    curve = wall.Location.Curve
    if isinstance(curve, Arc):
        n = point - curve.Center
        n = XYZ(n.X, n.Y, 0).Normalize()
    else:
        n = wall.Orientation
    a = XYZ.BasisZ.CrossProduct(n).Normalize()
    return n, a


def convex_hull(pts):
    pts = sorted(set((round(x, 9), round(y, 9)) for x, y in pts))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    # drop vertices too close to the previous one
    clean = []
    for p in hull:
        if not clean or math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > SHORT_TOL:
            clean.append(p)
    if len(clean) > 1 and math.hypot(clean[0][0] - clean[-1][0],
                                     clean[0][1] - clean[-1][1]) <= SHORT_TOL:
        clean.pop()
    return clean


def circle_arcs(center, radius, xvec, yvec):
    return [Arc.Create(center, radius, 0.0, math.pi, xvec, yvec),
            Arc.Create(center, radius, math.pi, 2.0 * math.pi, xvec, yvec)]


def square_around(center, radius, axis):
    p1 = center - axis.Multiply(radius) - XYZ.BasisZ.Multiply(radius)
    p2 = center + axis.Multiply(radius) + XYZ.BasisZ.Multiply(radius)
    return p1, p2


class Plan(object):
    """One opening to create."""

    def __init__(self, kind, host, item, **data):
        self.kind = kind        # wall_rect | wall_round | slab_round | slab_poly
        self.host = host
        self.item = item
        self.data = data


# ---------------------------------------------------------------------------
# Generator - everything that touches the document
# ---------------------------------------------------------------------------
class Generator(object):

    def __init__(self, doc):
        self.doc = doc
        self._solids = {}

    def clear_cache(self):
        """Forget cached host geometry (call after openings were deleted)."""
        self._solids = {}

    # ---- MEP -------------------------------------------------------------
    def make_item(self, el, src_doc, transform, source, source_uid, key, offset_mm):
        """Build a MepItem. Returns (item, None) or (None, reason)."""
        _, _, cls, round_bips, rect_bips = MEP_BY_KEY[key]
        loc = el.Location
        if not isinstance(loc, LocationCurve) or not isinstance(loc.Curve, Line):
            return None, "not a straight element"
        p0 = transform.OfPoint(loc.Curve.GetEndPoint(0))
        p1 = transform.OfPoint(loc.Curve.GetEndPoint(1))
        if p0.DistanceTo(p1) < SHORT_TOL:
            return None, "too short"
        shape = read_shape(el, src_doc, round_bips, rect_bips)
        if not shape:
            return None, "size could not be read"
        line = Line.CreateBound(p0, p1)
        u, v = cross_axes(el, transform, line.Direction.Normalize())
        return MepItem(key, el, source, source_uid, line, shape, u, v,
                       mm_to_ft(offset_mm)), None

    def _collect_from(self, src_doc, transform, source, source_uid, offsets,
                      items, skipped):
        for key, label, cls, _, _ in MEP_TYPES:
            for el in FilteredElementCollector(src_doc).OfClass(cls) \
                    .WhereElementIsNotElementType():
                item, reason = self.make_item(el, src_doc, transform, source,
                                              source_uid, key, offsets[key])
                if item:
                    items.append(item)
                elif reason == "size could not be read":
                    skipped.append((label, el.Id, source, source_uid, reason))

    def collect_mep(self, offsets):
        """All straight MEP curves, local and from loaded links."""
        items, skipped = [], []
        self._collect_from(self.doc, Transform.Identity, "Local", None,
                           offsets, items, skipped)
        for link in FilteredElementCollector(self.doc).OfClass(RevitLinkInstance):
            link_doc = link.GetLinkDocument()
            if link_doc is None:
                continue    # unloaded link
            self._collect_from(link_doc, link.GetTotalTransform(), link.Name,
                               link.UniqueId, offsets, items, skipped)
        return items, skipped

    def item_from_record(self, rec, offset_mm):
        """Find the MEP element a record points to. (item, None) or (None, reason)."""
        link_uid = rec.get("link_uid")
        if link_uid:
            link = self.doc.GetElement(link_uid)
            if not isinstance(link, RevitLinkInstance):
                return None, "link instance not found"
            src_doc = link.GetLinkDocument()
            if src_doc is None:
                return None, "link not loaded"
            transform = link.GetTotalTransform()
            source = link.Name
        else:
            src_doc, transform, source = self.doc, Transform.Identity, "Local"
        el = src_doc.GetElement(rec["mep_uid"])
        if el is None:
            return None, "MEP element not found"
        return self.make_item(el, src_doc, transform, source, link_uid or None,
                              rec["cat"], offset_mm)

    # ---- hosts -----------------------------------------------------------
    def host_solids(self, el):
        key = eid_int(el.Id)
        if key in self._solids:
            return self._solids[key]
        opts = Options()
        opts.DetailLevel = ViewDetailLevel.Fine
        opts.ComputeReferences = False
        solids = []

        def walk(geo):
            for g in geo:
                if isinstance(g, Solid) and g.Volume > 1e-9:
                    solids.append(g)
                elif isinstance(g, GeometryInstance):
                    walk(g.GetInstanceGeometry())

        geo = el.get_Geometry(opts)
        if geo:
            walk(geo)
        self._solids[key] = solids
        return solids

    def candidate_hosts(self, item):
        p0, p1 = item.line.GetEndPoint(0), item.line.GetEndPoint(1)
        e = item.half_extent
        outline = Outline(
            XYZ(min(p0.X, p1.X) - e, min(p0.Y, p1.Y) - e, min(p0.Z, p1.Z) - e),
            XYZ(max(p0.X, p1.X) + e, max(p0.Y, p1.Y) + e, max(p0.Z, p1.Z) + e))
        return (FilteredElementCollector(self.doc)
                .WherePasses(ElementMulticategoryFilter(HOST_CATS))
                .WhereElementIsNotElementType()
                .WherePasses(BoundingBoxIntersectsFilter(outline)))

    # ---- planning --------------------------------------------------------
    def plan_openings(self, items, skipped, allowed=None, title="OPGen"):
        """Plans for every penetration. `allowed(item, host)` can restrict hosts.

        Returns None if the user cancelled.
        """
        plans = []
        with forms.ProgressBar(
                title=title + ": finding penetrations ({value} of {max_value})",
                cancellable=True) as pb:
            for idx, item in enumerate(items):
                if pb.cancelled:
                    return None
                pb.update_progress(idx + 1, len(items))
                for host in self.candidate_hosts(item):
                    kind = host_kind(host)
                    if not kind:
                        continue
                    if allowed is not None and not allowed(item, host):
                        continue
                    self._plan_host(item, host, kind, plans, skipped)
        return plans

    def _plan_host(self, item, host, kind, plans, skipped):
        for p0, p1 in penetrations(self.host_solids(host), item.line):
            mid = (p0 + p1).Multiply(0.5)
            pts = item.section_points(p0) + item.section_points(p1)

            if kind == "wall":
                n, a = wall_axes(host, mid)
                if abs(item.d.DotProduct(n)) < MIN_CROSS_ANGLE_COS:
                    skipped.append((item.label, item.el_id, item.source, item.source_uid,
                                    "runs along wall {}".format(eid_int(host.Id))))
                    continue
                coords = [((p - mid).DotProduct(a), p.Z) for p in pts]
                if item.is_round:
                    r = max(math.hypot(s, z - mid.Z) for s, z in coords)
                    plans.append(Plan("wall_round", host, item,
                                      center=mid, radius=r, axis=a))
                else:
                    smin = min(c[0] for c in coords)
                    smax = max(c[0] for c in coords)
                    zmin = min(c[1] for c in coords)
                    zmax = max(c[1] for c in coords)
                    plans.append(Plan("wall_rect", host, item,
                                      p1=XYZ(mid.X + a.X * smin, mid.Y + a.Y * smin, zmin),
                                      p2=XYZ(mid.X + a.X * smax, mid.Y + a.Y * smax, zmax)))
            else:
                if kind in ("floor", "ceiling") and abs(item.d.Z) < MIN_CROSS_ANGLE_COS:
                    skipped.append((item.label, item.el_id, item.source, item.source_uid,
                                    "runs along {} {}".format(kind, eid_int(host.Id))))
                    continue
                if item.is_round:
                    r = max(math.hypot(p.X - mid.X, p.Y - mid.Y) for p in pts)
                    plans.append(Plan("slab_round", host, item, center=mid, radius=r))
                else:
                    hull = convex_hull([(p.X, p.Y) for p in pts])
                    if len(hull) < 3:
                        continue
                    plans.append(Plan("slab_poly", host, item, pts=hull, z=mid.Z))

    # ---- creation --------------------------------------------------------
    def _create_native(self, plan):
        host = plan.host
        data = plan.data
        if plan.kind == "wall_rect":
            return self.doc.Create.NewOpening(host, data["p1"], data["p2"])
        profile = CurveArray()
        if plan.kind == "slab_round":
            for arc in circle_arcs(data["center"], data["radius"],
                                   XYZ.BasisX, XYZ.BasisY):
                profile.Append(arc)
        else:
            z = data["z"]
            pts = [XYZ(x, y, z) for x, y in data["pts"]]
            for i in range(len(pts)):
                profile.Append(Line.CreateBound(pts[i], pts[(i + 1) % len(pts)]))
        return self.doc.Create.NewOpening(host, profile, False)

    def _edit_sketch(self, sketch, action, name):
        """Run action(sketch) inside a SketchEditScope. True on success."""
        ses = SketchEditScope(self.doc, name)
        handler = StrictFailures()
        t = None
        try:
            ses.Start(sketch.Id)
            t = Transaction(self.doc, name)
            t.Start()
            action(sketch)
            t.Commit()
            ses.Commit(handler)
        except Exception:
            handler.failed = True
            if t is not None and t.GetStatus() == TransactionStatus.Started:
                t.RollBack()
        finally:
            if ses.IsActive:          # property, not a method
                ses.Cancel()
        return not handler.failed

    def _add_wall_circle(self, wall, plan):
        """Add a circle to the wall's profile sketch. True on success."""
        sketch = self.doc.GetElement(wall.SketchId)
        if sketch is None:
            return False
        plane = sketch.SketchPlane.GetPlane()
        c = plan.data["center"]
        c = c - plane.Normal.Multiply((c - plane.Origin).DotProduct(plane.Normal))
        radius = plan.data["radius"]

        def action(sk):
            for arc in circle_arcs(c, radius, plane.XVec, plane.YVec):
                self.doc.Create.NewModelCurve(arc, sk.SketchPlane)

        ok = self._edit_sketch(sketch, action, "OPGen - Round Wall Opening")
        if ok:
            plan.data["sketch_center"] = c
        return ok

    def _run_transaction(self, name, plans, results, failures):
        if not plans:
            return
        t = Transaction(self.doc, name)
        handler = LenientFailures()
        opts = t.GetFailureHandlingOptions()
        opts.SetFailuresPreprocessor(handler)
        opts.SetClearAfterRollback(True)
        t.SetFailureHandlingOptions(opts)
        t.Start()
        created = []
        for plan in plans:
            try:
                op = self._create_native(plan)
            except Exception as ex:
                failures.append((plan, str(ex)))
                continue
            created.append((plan, op.Id))
            comment = op.get_Parameter(BIP.ALL_MODEL_INSTANCE_COMMENTS)
            if comment and not comment.IsReadOnly:
                comment.Set(COMMENT_PREFIX + COMMENT_LABELS[plan.item.key])
        t.Commit()
        for plan, op_id in created:
            if self.doc.GetElement(op_id) is not None:
                results.append((plan, op_id))
            else:
                failures.append((plan, "removed by Revit (invalid opening)"))
        for msg in handler.messages:
            print("Revit: {}".format(msg))

    def create_openings(self, plans, title="OPGen"):
        """Create all planned openings. Returns (results, failures).

        results:  [(plan, opening ElementId or None for wall-profile circles)]
        failures: [(plan, reason)]
        """
        results, failures = [], []
        native = [p for p in plans if p.kind != "wall_round"]
        wall_round = [p for p in plans if p.kind == "wall_round"]

        # Walls that need a profile sketch for round openings
        fallback = []
        need_sketch = {}
        for p in wall_round:
            wall = p.host
            if wall.SketchId != ElementId.InvalidElementId:
                continue
            if wall.CanHaveProfileSketch():
                need_sketch[eid_int(wall.Id)] = wall
            else:
                fallback.append(p)
        wall_round = [p for p in wall_round if p not in fallback]

        if need_sketch:
            t = Transaction(self.doc, title + " - Prepare Wall Profiles")
            t.Start()
            for wall in need_sketch.values():
                try:
                    wall.CreateProfileSketch()
                except Exception:
                    pass
            t.Commit()

        self._run_transaction(title + " - Create Openings", native, results, failures)

        if wall_round:
            with forms.ProgressBar(
                    title=title + ": round wall openings ({value} of {max_value})") as pb:
                for idx, p in enumerate(wall_round):
                    pb.update_progress(idx + 1, len(wall_round))
                    if self._add_wall_circle(p.host, p):
                        results.append((p, None))
                    else:
                        fallback.append(p)

        # Round wall openings that could not go into a profile sketch
        rect_fallback = []
        for p in fallback:
            p1, p2 = square_around(p.data["center"], p.data["radius"], p.data["axis"])
            fp = Plan("wall_rect", p.host, p.item, p1=p1, p2=p2, fallback=True)
            rect_fallback.append(fp)
        self._run_transaction(title + " - Fallback Wall Openings", rect_fallback,
                              results, failures)
        return results, failures

    # ---- records ---------------------------------------------------------
    def records_from_results(self, results):
        """Turn creation results into storable records (plain dicts)."""
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        records = []
        for plan, op_id in results:
            item = plan.item
            rec = {
                "cat": item.key,
                "kind": plan.kind,
                "fallback": bool(plan.data.get("fallback")),
                "opening_uid": None,
                "host_uid": plan.host.UniqueId,
                "host_id": eid_int(plan.host.Id),
                "mep_uid": item.uid,
                "mep_id": eid_int(item.el_id),
                "link_uid": item.source_uid,
                "source": item.source,
                "shape": item.shape[0],
                "size_mm": item.size_mm(),
                "offset_mm": round(ft_to_mm(item.offset), 3),
                "created": stamp,
            }
            if op_id is not None:
                rec["opening_uid"] = self.doc.GetElement(op_id).UniqueId
            else:
                c = plan.data["sketch_center"]
                rec["circle"] = {"center": [c.X, c.Y, c.Z],
                                 "radius": plan.data["radius"]}
            records.append(rec)
        return records

    def _circle_curve_ids(self, wall, recs):
        """Sketch curve ids of the wall that match the recorded circles."""
        if wall is None or wall.SketchId == ElementId.InvalidElementId:
            return []
        sketch = self.doc.GetElement(wall.SketchId)
        if sketch is None:
            return []
        tol_c, tol_r = mm_to_ft(1.0), mm_to_ft(0.5)
        circles = [(XYZ(*r["circle"]["center"]), r["circle"]["radius"]) for r in recs]
        ids = []
        for eid in sketch.GetAllElements():
            el = self.doc.GetElement(eid)
            if not isinstance(el, CurveElement):
                continue
            crv = el.GeometryCurve
            if not isinstance(crv, Arc):
                continue
            for center, radius in circles:
                if crv.Center.DistanceTo(center) < tol_c and abs(crv.Radius - radius) < tol_r:
                    ids.append(eid)
                    break
        return ids

    def record_exists(self, rec):
        """Does the opening a record points to still exist in the model?"""
        if rec["kind"] == "wall_round":
            wall = self.doc.GetElement(rec["host_uid"])
            return bool(self._circle_curve_ids(wall, [rec]))
        uid = rec.get("opening_uid")
        return bool(uid) and self.doc.GetElement(uid) is not None

    def remove_records(self, recs, title="OPUpdate"):
        """Delete the openings of the given records. Returns [(rec, reason)] failures."""
        failed = []
        native = [r for r in recs if r["kind"] != "wall_round"]
        circles = {}
        for r in recs:
            if r["kind"] == "wall_round":
                circles.setdefault(r["host_uid"], []).append(r)

        if native:
            t = Transaction(self.doc, title + " - Remove Old Openings")
            handler = LenientFailures()
            opts = t.GetFailureHandlingOptions()
            opts.SetFailuresPreprocessor(handler)
            t.SetFailureHandlingOptions(opts)
            t.Start()
            for r in native:
                el = self.doc.GetElement(r["opening_uid"])
                try:
                    self.doc.Delete(el.Id)
                except Exception as ex:
                    failed.append((r, "could not delete opening: {}".format(ex)))
            t.Commit()

        for host_uid, wall_recs in circles.items():
            wall = self.doc.GetElement(host_uid)
            ids = self._circle_curve_ids(wall, wall_recs)
            if not ids:
                failed.extend((r, "circle not found in wall sketch") for r in wall_recs)
                continue
            id_list = List[ElementId](ids)

            def action(sk, id_list=id_list):
                self.doc.Delete(id_list)

            sketch = self.doc.GetElement(wall.SketchId)
            if not self._edit_sketch(sketch, action, title + " - Remove Wall Circles"):
                failed.extend((r, "could not edit wall profile") for r in wall_recs)

        self.clear_cache()
        return failed


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------
def describe_plan(plan):
    if plan.kind in ("wall_round", "slab_round"):
        return "Round", u"Ø{:.0f}".format(ft_to_mm(plan.data["radius"] * 2))
    if plan.data.get("fallback"):
        return "Rectangular (round fallback)", ""
    return "Rectangular", ""


def host_ref(output, host):
    return "{} {}".format(host.Category.Name, output.linkify(host.Id))


def opening_ref(output, op_id):
    return "wall profile" if op_id is None else output.linkify(op_id)


def skipped_rows(output, skipped):
    return [[label, output.linkify(eid) if src_uid is None
             else "{} [{}]".format(eid_int(eid), src), reason]
            for label, eid, src, src_uid, reason in skipped]


def report(output, title, results, failures, skipped):
    output.print_md("# " + title)
    output.print_md("**Openings created:** {}  |  **Failed:** {}  |  **Skipped elements:** {}"
                    .format(len(results), len(failures), len(skipped)))
    if results:
        rows = []
        for plan, op_id in results:
            shape, size = describe_plan(plan)
            rows.append([plan.item.label, plan.item.describe(output),
                         host_ref(output, plan.host), shape, size,
                         opening_ref(output, op_id)])
        output.print_table(rows, columns=["MEP", "Element", "Host", "Shape", "Size", "Opening"],
                           title="Created")
    if failures:
        rows = [[p.item.label, p.item.describe(output), host_ref(output, p.host), msg]
                for p, msg in failures]
        output.print_table(rows, columns=["MEP", "Element", "Host", "Reason"], title="Failed")
    if skipped:
        output.print_table(skipped_rows(output, skipped),
                           columns=["MEP", "Element", "Reason"], title="Skipped")
