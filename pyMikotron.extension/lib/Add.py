from pyrevit import revit, forms
from Autodesk.Revit.DB import *

def main():
    doc = revit.doc

    view_or_template = forms.CommandSwitchWindow.show(
        ["views", "templates"],
        message="Select views or templates"
    )

    def get_filters():
        return forms.SelectFromList.show(
            FilteredElementCollector(doc).OfClass(ParameterFilterElement).ToElements(),
            name_attr="Name",
            title="Select filters to add",
            multiselect=True
        )

    def get_views():
        return forms.SelectFromList.show(
            [v for v in FilteredElementCollector(doc).OfClass(View).ToElements()
             if not v.IsTemplate and v.AreGraphicsOverridesAllowed()],
            name_attr="Name",
            title="Select views",
            multiselect=True
        )

    def get_templates():
        return forms.SelectFromList.show(
            [v for v in FilteredElementCollector(doc).OfClass(View).ToElements()
             if v.IsTemplate and v.AreGraphicsOverridesAllowed()],
            name_attr="Name",
            title="Select templates",
            multiselect=True
        )

    if view_or_template == "views":
        views = get_views()
    elif view_or_template == "templates":
        views = get_templates()
    else:
        raise Exception("Please select either views or templates.")

    added = []
    filters = get_filters()

    if views and filters:
        with revit.Transaction("Add Filters to Views/Templates"):
            for v in views:
                for f in filters:
                    if not v.IsFilterApplied(f.Id):
                        v.AddFilter(f.Id)
                        added.append((v.Name, f.Name))
