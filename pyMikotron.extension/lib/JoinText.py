from pyrevit import revit, forms
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI.Selection import ObjectType

def main():
    doc = revit.doc
    uidoc = revit.uidoc

    refs = uidoc.Selection.PickObjects(
        ObjectType.Element,
        "Select text notes in the view"
    )

    spacer = forms.ask_for_string(prompt="Enter a spacer string (optional):",default="\n")

    text_notes = [
        doc.GetElement(r.ElementId)
        for r in refs
        if isinstance(doc.GetElement(r.ElementId), TextNote)
    ]

    def join_text(elements):
        text = ""
        for element in elements:
            text += element.Text + spacer

        with Transaction(doc, "Join Text Notes") as t:
            t.Start()
            elements[0].Text = text
            for element in elements[1:]:
                doc.Delete(element.Id)
            t.Commit()

    join_text(text_notes)

if __name__ == "__main__":
    main()