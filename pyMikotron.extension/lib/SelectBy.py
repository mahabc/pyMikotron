from pyrevit import revit, forms
from System.Collections.Generic import List

import clr
clr.AddReference("RevitAPI")

from Autodesk.Revit.DB import *

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView
selected = []


def get_elements_of_category(category):
    return (
        FilteredElementCollector(doc, view.Id)
        .OfCategory(category)
        .WhereElementIsNotElementType()
        .ToElements()
    )


def get_all_categories():
    cats = doc.Settings.Categories
    categories = []

    for c in cats:
        try:
            bic = BuiltInCategory(c.Id.IntegerValue)
            categories.append(bic)
        except:
            continue

    return categories


def get_family_name(element):
    if not isinstance(element, FamilyInstance):
        return None

    try:
        symbol = element.Symbol
        if symbol is None:
            return None

        family = symbol.Family
        if family is None:
            return None

        return Element.Name.GetValue(family)

    except:
        return None


def get_elements():
    return (
        FilteredElementCollector(doc, view.Id)
        .WhereElementIsNotElementType()
        .ToElements()
    )


def get_param_names(elements, collection):
    for e in elements:
        for p in e.Parameters:
            if p.Definition:
                collection.add(p.Definition.Name)

    return sorted(collection)


def ask_for_value(param_name):
    value = forms.ask_for_string(
        default="",
        prompt="Enter value:",
        title=param_name
    )

    if value is None:
        return

    return value


def main():

    options = [
        "Parameter",
        "Phrase in Family Name",
        "Category"
    ]

    collection = set()
    selected = []

    option = forms.SelectFromList.show(
        options,
        title="Select By:",
        multiselect=False
    )

    if option == options[0]:

        elems = (FilteredElementCollector(doc, view.Id).OfClass(FamilyInstance).WhereElementIsNotElementType().ToElements())
        param_names = get_param_names(elems,collection)

        param_name = forms.SelectFromList.show(
            param_names,
            title="Select Parameter",
            multiselect=False
        )

        if not param_name:
            return

        value = ask_for_value(param_name)

        if value is None:
            return

        for elem in elems:

            p = elem.LookupParameter(param_name)

            if p is None:
                continue

            if p.StorageType == StorageType.String:
                if p.AsString() == value:
                    selected.append(elem)
            else:
                if p.AsValueString() == value:
                    selected.append(elem)

    elif option == options[1]:

        elems = (
            FilteredElementCollector(doc, view.Id)
            .OfClass(FamilyInstance)
            .WhereElementIsNotElementType()
            .ToElements()
        )
    
        value = ask_for_value("Family Name")
    
        if value is None:
            return
    
        for e in elems:
            name = get_family_name(e)
    
            if name and value in name:
                selected.append(e)

    elif option == options[2]:

        cats = get_all_categories()
    
        cat_names = []
        cat_dict = {}
    
        for cat in cats:
            name = LabelUtils.GetLabelFor(cat)
            cat_names.append(name)
            cat_dict[name] = cat
    
        cat_name = forms.SelectFromList.show(
            cat_names,
            title="Select Category",
            multiselect=False
        )
    
        if not cat_name:
            return
    
        category = cat_dict[cat_name]
    
        selected = get_elements_of_category(category)

    else:
        return

    uidoc.Selection.SetElementIds(
        List[ElementId]([elem.Id for elem in selected])
    )


if __name__ == "__main__":
    main()