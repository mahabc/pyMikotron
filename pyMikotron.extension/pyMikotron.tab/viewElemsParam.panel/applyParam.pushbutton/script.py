from pyrevit import revit, forms

import clr
clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import *

doc = revit.doc
view = doc.ActiveView


def main():

    # Collect all elements in active view
    elems = FilteredElementCollector(doc, view.Id)\
        .WhereElementIsNotElementType()\
        .ToElements()

    # Collect unique writable parameter names
    param_names = set()

    for elem in elems:
        for p in elem.Parameters:
            if p.Definition and not p.IsReadOnly:
                param_names.add(p.Definition.Name)

    param_names = sorted(param_names)

    # Select parameter
    param_name = forms.SelectFromList.show(
        param_names,
        title="Select Parameter",
        multiselect=False
    )

    if not param_name:
        return

    # Enter value
    value = forms.ask_for_string(
        default="",
        prompt="Enter value:",
        title=param_name
    )

    if value is None:
        return

    updated = 0
    skipped = 0

    with revit.Transaction("Set Parameter Value"):

        for elem in elems:

            p = elem.LookupParameter(param_name)

            if p is None or p.IsReadOnly:
                skipped += 1
                continue

            try:

                if p.StorageType == StorageType.String:
                    p.Set(value)

                elif p.StorageType == StorageType.Integer:
                    p.Set(int(value))

                elif p.StorageType == StorageType.Double:
                    p.Set(float(value))

                else:
                    skipped += 1
                    continue

                updated += 1

            except:
                skipped += 1

    forms.alert(
        "Updated: {}\nSkipped: {}".format(updated, skipped),
        title="Finished"
    )


if __name__ == "__main__":
    main()