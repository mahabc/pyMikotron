# -*- coding: utf-8 -*-
"""OPUpdate - update openings created by OPGen (Revit 2025).

For the ticked categories (pipes / ducts / conduits / cable trays):
  1. finds every opening OPGen recorded in this model,
  2. deletes it and regenerates it with the new offset, using the MEP
     element's current position and size, in the same host only,
  3. updates the stored records.

Records whose opening was deleted by hand are removed (nothing recreated).
Records whose MEP element can't be found (deleted, link unloaded) are kept
and left untouched. New penetrations are not added here - run OPGen for that.
"""
from collections import OrderedDict

from pyrevit import revit, forms, script

from general import opgen, opgen_store

TITLE = "OPUpdate - Update Openings"


def rec_mep_ref(rec):
    return "{} [{}]".format(rec.get("mep_id"), rec.get("source", "?"))


def rec_host_ref(output, doc, rec):
    host = doc.GetElement(rec["host_uid"])
    if host is None:
        return "{} (deleted)".format(rec.get("host_id"))
    return opgen.host_ref(output, host)


def main():
    doc = revit.doc
    output = script.get_output()

    if doc.IsFamilyDocument:
        forms.alert("Run OPUpdate in a project document.", exitscript=True)

    data = opgen_store.load(doc)
    if not data["openings"]:
        forms.alert("No OPGen opening records in this model.\n"
                    "Run OPGen first to create (and record) openings.", exitscript=True)

    dlg = opgen.OffsetDialog(TITLE, "Tick categories to update - new offset per side (mm)",
                             "Update Openings", opgen.default_offsets(data.get("offsets")),
                             counts=opgen_store.count_by_category(data))
    dlg.show_dialog()
    if not dlg.offsets:
        script.exit()
    selected = set(dlg.selected)
    offsets = dlg.offsets

    gen = opgen.Generator(doc)
    keep, targets = [], []
    for rec in data["openings"]:
        (targets if rec.get("cat") in selected else keep).append(rec)

    # --- check each target record ----------------------------------------
    deleted_by_hand, mep_missing, valid = [], [], []
    items = OrderedDict()          # MEP ident -> MepItem
    for rec in targets:
        if not gen.record_exists(rec):
            deleted_by_hand.append(rec)
            continue
        ident = (rec.get("link_uid") or "", rec["mep_uid"])
        if ident not in items:
            item, reason = gen.item_from_record(rec, offsets[rec["cat"]])
            items[ident] = item or reason
        found = items[ident]
        if isinstance(found, opgen.MepItem):
            valid.append(rec)
        else:
            mep_missing.append((rec, found))

    # --- delete old openings ----------------------------------------------
    remove_failed = gen.remove_records(valid) if valid else []
    failed_ids = set(id(r) for r, _ in remove_failed)
    replaced = [r for r in valid if id(r) not in failed_ids]

    # --- regenerate in the same hosts ------------------------------------
    allowed_hosts = {}
    for rec in replaced:
        ident = (rec.get("link_uid") or "", rec["mep_uid"])
        allowed_hosts.setdefault(ident, set()).add(rec["host_uid"])

    results, failures, skipped = [], [], []
    if replaced:
        regen_items = [items[i] for i in allowed_hosts]
        plans = gen.plan_openings(
            regen_items, skipped, title="OPUpdate",
            allowed=lambda item, host: host.UniqueId in allowed_hosts.get(item.ident, ()))
        if plans is None:
            forms.alert("Cancelled after old openings were removed.\n"
                        "Use Undo to restore them.", exitscript=True)
        results, failures = gen.create_openings(plans, title="OPUpdate")

    new_records = gen.records_from_results(results)
    produced = set((r["link_uid"] or "", r["mep_uid"], r["host_uid"]) for r in new_records)
    lost = [r for r in replaced
            if ((r.get("link_uid") or ""), r["mep_uid"], r["host_uid"]) not in produced]

    # --- save records -----------------------------------------------------
    data["openings"] = (keep
                        + [r for r, _ in mep_missing]
                        + [r for r, _ in remove_failed]
                        + new_records)
    for key in selected:
        data["offsets"][key] = offsets[key]
    try:
        opgen_store.save(doc, data, "OPUpdate - Save Opening Records")
    except Exception as ex:
        forms.alert("Openings were updated, but saving the opening records failed:\n{}"
                    .format(ex))

    # --- report -----------------------------------------------------------
    old_offset = dict(((r.get("link_uid") or "", r["mep_uid"], r["host_uid"]),
                       r.get("offset_mm")) for r in replaced)
    output.print_md("# " + TITLE)
    output.print_md(
        "**Updated:** {}  |  **Failed:** {}  |  **No longer penetrating:** {}  |  "
        "**Deleted by hand:** {}  |  **MEP not found:** {}".format(
            len(results), len(failures) + len(remove_failed), len(lost),
            len(deleted_by_hand), len(mep_missing)))

    if results:
        rows = []
        for plan, op_id in results:
            key = (plan.item.source_uid or "", plan.item.uid, plan.host.UniqueId)
            shape, size = opgen.describe_plan(plan)
            rows.append([plan.item.label, plan.item.describe(output),
                         opgen.host_ref(output, plan.host), shape, size,
                         u"{} → {:g}".format(old_offset.get(key, "?"),
                                                  opgen.ft_to_mm(plan.item.offset)),
                         opgen.opening_ref(output, op_id)])
        output.print_table(rows, columns=["MEP", "Element", "Host", "Shape", "Size",
                                          "Offset mm", "Opening"], title="Updated")
    if failures or remove_failed:
        rows = [[p.item.label, p.item.describe(output), opgen.host_ref(output, p.host), msg]
                for p, msg in failures]
        rows += [[opgen.CATEGORY_LABELS.get(r["cat"], r["cat"]), rec_mep_ref(r),
                  rec_host_ref(output, doc, r), msg] for r, msg in remove_failed]
        output.print_table(rows, columns=["MEP", "Element", "Host", "Reason"],
                           title="Failed (old opening kept where it could not be removed)")
    if lost:
        rows = [[opgen.CATEGORY_LABELS.get(r["cat"], r["cat"]), rec_mep_ref(r),
                 rec_host_ref(output, doc, r)] for r in lost]
        output.print_table(rows, columns=["MEP", "Element", "Host"],
                           title="Old opening removed - element no longer passes through host")
    if deleted_by_hand:
        rows = [[opgen.CATEGORY_LABELS.get(r["cat"], r["cat"]), rec_mep_ref(r),
                 rec_host_ref(output, doc, r)] for r in deleted_by_hand]
        output.print_table(rows, columns=["MEP", "Element", "Host"],
                           title="Opening deleted by hand - record removed")
    if mep_missing:
        rows = [[opgen.CATEGORY_LABELS.get(r["cat"], r["cat"]), rec_mep_ref(r),
                 rec_host_ref(output, doc, r), reason] for r, reason in mep_missing]
        output.print_table(rows, columns=["MEP", "Element", "Host", "Reason"],
                           title="MEP element not found - opening and record kept")
    if skipped:
        output.print_table(opgen.skipped_rows(output, skipped),
                           columns=["MEP", "Element", "Reason"], title="Skipped")


if __name__ == "__main__":
    main()
