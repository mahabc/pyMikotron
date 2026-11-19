# -*- coding: utf-8 -*-
"""OPGen - Opening Generator (Revit 2025).

Creates openings where pipes, ducts, conduits and cable trays (local or
linked) pass through local walls, floors, ceilings and roofs, and records
every created opening in the model (see lib/general/opgen_store.py) so that
OPUpdate can find and resize them later.

Logic lives in lib/general/opgen.py (shared with OPUpdate).
"""
from pyrevit import revit, forms, script

from general import opgen, opgen_store

TITLE = "OPGen - Opening Generator"


def main():
    doc = revit.doc
    output = script.get_output()

    if doc.IsFamilyDocument:
        forms.alert("Run OPGen in a project document.", exitscript=True)

    stored = opgen_store.load(doc)
    dlg = opgen.OffsetDialog(TITLE, "Opening offset per side (mm)", "Create Openings",
                             opgen.default_offsets(stored.get("offsets")))
    dlg.show_dialog()
    if not dlg.offsets:
        script.exit()

    gen = opgen.Generator(doc)
    items, skipped = gen.collect_mep(dlg.offsets)
    if not items:
        forms.alert("No straight pipes, ducts, conduits or cable trays found "
                    "(local or linked).", exitscript=True)

    plans = gen.plan_openings(items, skipped, title="OPGen")
    if plans is None:
        script.exit()
    if not plans:
        opgen.report(output, TITLE, [], [], skipped)
        forms.alert("No penetrations found that need an opening.")
        return

    results, failures = gen.create_openings(plans, title="OPGen")

    if results:
        try:
            opgen_store.add_records(doc, gen.records_from_results(results), dlg.offsets)
        except Exception as ex:
            forms.alert("Openings were created, but saving the opening records failed:\n{}\n\n"
                        "OPUpdate will not recognise these openings.".format(ex))

    opgen.report(output, TITLE, results, failures, skipped)


if __name__ == "__main__":
    main()
