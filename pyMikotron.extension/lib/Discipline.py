from pyrevit import revit, forms, script
from Autodesk.Revit.DB import FilteredElementCollector, StorageType

PARAM_NAME = "Element_Type_RevitModel"

doc = revit.doc


def main():
    model = forms.ask_for_string(
        prompt="Enter the model name to set for all element types:",
        default="ModelName",
        title="Discipline")
    if not model:
        script.exit()

    types = FilteredElementCollector(doc).WhereElementIsElementType().ToElements()

    updated = 0
    skipped = 0
    with revit.Transaction("Set {}".format(PARAM_NAME)):
        for t in types:
            param = t.LookupParameter(PARAM_NAME)
            if not param:
                continue
            if param.IsReadOnly or param.StorageType != StorageType.String:
                skipped += 1
                continue
            if param.Set(model):
                updated += 1
            else:
                skipped += 1

    if updated == 0 and skipped == 0:
        forms.alert("No element types have the parameter '{}'.".format(PARAM_NAME))
    else:
        forms.alert("Updated {} type(s) to '{}'.\nSkipped {} (read-only or not text).".format(
            updated, model, skipped))


if __name__ == "__main__":
    main()
