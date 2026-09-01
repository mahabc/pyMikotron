import clr
import os
import re

clr.AddReference("System.Drawing")
clr.AddReference("RevitAPI")

from System.Drawing import Size
from System.Drawing.Imaging import ImageFormat
from Autodesk.Revit.DB import *

from pyrevit import revit, forms, script

doc = revit.doc


def get_preview_image(ssymbols,path):
    for symbol in ssymbols:

        if symbol is None:
            continue

        try:
            # FamilySymbol.Name can fail in IronPython
            name = Element.Name.GetValue(symbol)
            fam = doc.GetElement(symbol.Family.Id)
            name = "{} - {}".format(fam.Name, name)

            # Make name safe for Windows filename
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', name)

            # Get preview
            image = symbol.GetPreviewImage(Size(300, 300))

            if image is None:
                print("No preview image: {}".format(name))
                continue

            output_path = os.path.join(
                path,
                safe_name + ".png"
            )

            # Remove existing file
            if os.path.exists(output_path):
                os.remove(output_path)

            # Save
            image.Save(
                output_path,
                ImageFormat.Png
            )

            image.Dispose()

            print("Saved: {}".format(output_path))

        except Exception as ex:
            print(
                "Failed for symbol {}: {}".format(
                    symbol.Id,
                    ex
                )
            )

def get_categories():
    categories = []
    for category in doc.Settings.Categories:

        try:
            if category.AllowsBoundParameters:
                categories.append(category)
        except:
            pass


    # Sort by category name
    categories = sorted(
        categories,
        key=lambda x: x.Name
    )


    selected_categories = forms.SelectFromList.show(
        categories,
        title="Select categories to export previews",
        button_name="Export Previews",
        multiselect=True,
        name_attr="Name"
    )


    if not selected_categories:
        script.exit()

    return selected_categories

def collect_symbols(categories):
    symbols = []
    for category in categories:
        collector = FilteredElementCollector(doc).OfCategoryId(category.Id).OfClass(FamilySymbol)
        symbols.extend(collector.ToElements())
    return symbols


path = forms.pick_folder(
    title="Select output folder for family previews"
)
# Output folder
desktop = path

if not os.path.exists(desktop):
    os.makedirs(desktop)

categories = get_categories()
symbols = collect_symbols(categories)
names = []
for s in symbols:
    fname = doc.GetElement(s.Family.Id)
    tname = Element.Name.GetValue(s)
    name = "{} - {}".format(fname.Name, tname)
    names.append(name)
    print("{}\n".format(name))

print(desktop)

get_preview_image(symbols,desktop)