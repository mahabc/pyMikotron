from pyrevit import revit, forms, script
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
            name_attr="Name", title="Select filters", multiselect=True
        )

    def get_views():
        return forms.SelectFromList.show(
            [v for v in FilteredElementCollector(doc).OfClass(View).ToElements()
             if not v.IsTemplate and v.AreGraphicsOverridesAllowed()],
            name_attr="Name", title="Select views", multiselect=True
        )

    def get_templates():
        return forms.SelectFromList.show(
            [v for v in FilteredElementCollector(doc).OfClass(View).ToElements()
             if v.IsTemplate and v.AreGraphicsOverridesAllowed()],
            name_attr="Name", title="Select templates", multiselect=True
        )

    def select_element(elements, title):
        return forms.SelectFromList.show(
            elements, name_attr="Name", title=title, multiselect=False
        )

    def get_override(set_properties):
        override = OverrideGraphicSettings()

        if set_properties in ["Activate", "Desactivate"]:
            return None

        elif set_properties == "Line Color":
            color = forms.ask_for_color()
            if not color:
                return None

            color = color.lstrip("#")[-6:]
            override.SetProjectionLineColor(
                Color(
                    int(color[0:2], 16),
                    int(color[2:4], 16),
                    int(color[4:6], 16)
                )
            )

        elif set_properties == "Line Pattern":
            patterns = FilteredElementCollector(doc).OfClass(LinePatternElement).ToElements()
            pattern = select_element(patterns, "Select line pattern")
            if not pattern:
                return None
            override.SetProjectionLinePatternId(pattern.Id)

        elif set_properties in ["Surface Pattern", "Cut Pattern"]:
            patterns = [
                p for p in FilteredElementCollector(doc).OfClass(FillPatternElement).ToElements()
                if p.GetFillPattern().Target == FillPatternTarget.Drafting
            ]
            pattern = select_element(patterns, "Select fill pattern")
            if not pattern:
                return None

            if set_properties == "Surface Pattern":
                override.SetSurfaceForegroundPatternId(pattern.Id)
            else:
                override.SetCutForegroundPatternId(pattern.Id)

        elif set_properties == "Transparency":
            value = forms.ask_for_string(
                default="50", prompt="Enter transparency (0-100)", title="Transparency"
            )
            if value is None:
                return None
            try:
                value = int(value)
                if not 0 <= value <= 100:
                    raise ValueError
            except ValueError:
                forms.alert("Enter a value between 0 and 100.", exitscript=True)
            override.SetSurfaceTransparency(value)

        elif set_properties == "Halftone On":
            override.SetHalftone(True)

        elif set_properties == "Halftone Off":
            override.SetHalftone(False)

        return override


    if view_or_template == "views":
        views = get_views()
    elif view_or_template == "templates":
        views = get_templates()
    else:
        raise Exception("Please select views or templates.")

    if not views:
        script.exit()

    filters = get_filters()
    if not filters:
        script.exit()

    set_properties = forms.CommandSwitchWindow.show(
        ["Activate", "Desactivate", "On", "Off", "Line Color",
         "Line Pattern", "Surface Pattern", "Cut Pattern",
         "Transparency", "Halftone On", "Halftone Off"],
        message="Select filter property"
    )

    if not set_properties:
        script.exit()

    override = get_override(set_properties)

    if override is None and set_properties not in ["Activate", "Desactivate"]:
        script.exit()

    added = []

    with revit.Transaction("Set Filter Properties"):
        for v in views:
            for f in filters:
                if not v.IsFilterApplied(f.Id):
                    v.AddFilter(f.Id)

                if set_properties == "Activate":
                    v.SetIsFilterEnabled(f.Id, True)
                elif set_properties == "Desactivate":
                    v.SetIsFilterEnabled(f.Id, False)
                elif set_properties == "On":
                    v.SetFilterVisibility(f.Id, True)
                elif set_properties == "Off":
                    v.SetFilterVisibility(f.Id, False)
                else:
                    # Apply the selected graphic override
                    current_override = v.GetFilterOverrides(f.Id)
                    if current_override is not None:
                        current_override = OverrideGraphicSettings(current_override)
                        # Apply the selected property to existing overrides instead
                        # of resetting unrelated settings.
                        if set_properties == "Line Color":
                            current_override.SetProjectionLineColor(
                                override.ProjectionLineColor
                            )
                        elif set_properties == "Line Pattern":
                            current_override.SetProjectionLinePatternId(
                                override.ProjectionLinePatternId
                            )
                        elif set_properties == "Surface Pattern":
                            current_override.SetSurfaceForegroundPatternId(
                                override.SurfaceForegroundPatternId
                            )
                        elif set_properties == "Cut Pattern":
                            current_override.SetCutForegroundPatternId(
                                override.CutForegroundPatternId
                            )
                        elif set_properties == "Transparency":
                            current_override.SetSurfaceTransparency(
                                override.SurfaceTransparency
                            )
                        elif set_properties == "Halftone On":
                            current_override.SetHalftone(True)
                        elif set_properties == "Halftone Off":
                            current_override.SetHalftone(False)

                        v.SetFilterOverrides(f.Id, current_override)

                added.append((v.Name, f.Name))
