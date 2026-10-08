from pyrevit import revit, forms
import csv


doc = revit.doc


def use_picklist():

    # -----------------------------------------------------
    # Pick CSV
    # -----------------------------------------------------

    csv_file = forms.pick_file(
        file_ext="csv",
        title="Select Asset CSV"
    )

    if not csv_file:
        return


    # -----------------------------------------------------
    # Read CSV
    # -----------------------------------------------------

    assets = []

    with open(csv_file, "rb") as f:

        reader = csv.DictReader(f)

        for row in reader:

            assets.append({
                "ASSET_ID": row.get("ASSET_ID", ""),
                "ASSET_KKS": row.get("ASSET_KKS", ""),
                "ASSET_TYPE": row.get("ASSET_TYPE", "")
            })


    if not assets:

        forms.alert(
            "No asset records found in the CSV.",
            exitscript=True
        )


    # -----------------------------------------------------
    # Asset list
    # -----------------------------------------------------

    asset_names = []

    for asset in assets:

        asset_names.append(
            "{} | {}".format(
                asset["ASSET_KKS"],
                asset["ASSET_TYPE"]
            )
        )


    # -----------------------------------------------------
    # Continuous asset assignment
    # -----------------------------------------------------

    while True:

        selected_name = forms.SelectFromList.show(
            asset_names,
            title="Select Asset",
            button_name="Select",
            multiselect=False
        )

        # Cancel = finish
        if not selected_name:
            break


        selected_index = asset_names.index(selected_name)
        asset = assets[selected_index]


        # -------------------------------------------------
        # Pick Revit element
        # -------------------------------------------------

        element = revit.pick_element()

        if not element:
            continue


        # -------------------------------------------------
        # Get parameters
        # -------------------------------------------------

        param_id = element.LookupParameter("ASSET_ID")
        param_kks = element.LookupParameter("Element_KKS1")
        param_type = element.LookupParameter("Element_Instance")
        param_pick = element.LookupParameter("ASSET_PICK")


        missing = []

        if not param_id:
            missing.append("ASSET_ID")

        if not param_kks:
            missing.append("Element_KKS1")

        if not param_type:
            missing.append("Element_Instance")

        if not param_pick:
            missing.append("ASSET_PICK")


        if missing:

            forms.alert(
                "The selected element is missing:\n\n" +
                "\n".join(missing),
                title="Missing Parameters"
            )

            continue


        # -------------------------------------------------
        # Write parameters
        # -------------------------------------------------

        with revit.Transaction("Assign Asset"):

            if not param_id.IsReadOnly:
                param_id.Set(asset["ASSET_ID"])

            if not param_kks.IsReadOnly:
                param_kks.Set(asset["ASSET_KKS"])

            if not param_type.IsReadOnly:
                param_type.Set(asset["ASSET_TYPE"])

            if not param_pick.IsReadOnly:
                param_pick.Set(1)


    # -----------------------------------------------------
    # Finished
    # -----------------------------------------------------

    return