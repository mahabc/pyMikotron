from pyrevit import revit, forms
from Autodesk.Revit.DB import *
import csv

doc = revit.doc


def get_parameter_value(param):
    if not param:
        return ""

    try:
        if param.StorageType == StorageType.String:
            return param.AsString() or ""

        elif param.StorageType == StorageType.Integer:
            return str(param.AsInteger())

        elif param.StorageType == StorageType.Double:
            return param.AsValueString() or ""

        elif param.StorageType == StorageType.ElementId:
            return param.AsValueString() or ""

    except:
        return ""

    return ""


def set_parameter_value(param, value):
    try:
        if not param or not param.IsShared or param.IsReadOnly:
            return False

        if param.StorageType == StorageType.String:
            current = param.AsString() or ""
            new_value = str(value)

            if current == new_value:
                return None

            param.Set(new_value)
            return True

        elif param.StorageType == StorageType.Integer:
            value_lower = str(value).strip().lower()

            if value_lower in ["true", "yes"]:
                new_value = 1
            elif value_lower in ["false", "no"]:
                new_value = 0
            else:
                new_value = int(float(value))

            if param.AsInteger() == new_value:
                return None

            param.Set(new_value)
            return True

        elif param.StorageType == StorageType.Double:
            if not value:
                return None

            old_value = param.AsDouble()
            param.SetValueString(str(value))
            new_value = param.AsDouble()

            if abs(old_value - new_value) < 0.000001:
                return None

            return True

        elif param.StorageType == StorageType.ElementId:
            return False

    except:
        return False

    return False


def assets_update():

    # -----------------------------------------------------
    # Pick CSV database
    # -----------------------------------------------------

    csv_file = forms.pick_file(file_ext="csv", title="Select Asset Database")

    if not csv_file:
        return


    # -----------------------------------------------------
    # Read CSV
    # -----------------------------------------------------

    assets = []

    try:
        with open(csv_file, "rb") as f:
            reader = csv.DictReader(f)

            for row in reader:
                assets.append(row)

    except:
        forms.alert("Failed to read the CSV database.", title="Asset Update")
        return

    if not assets:
        forms.alert("No asset records found in the CSV.", title="Asset Update")
        return


    # -----------------------------------------------------
    # Validate ASSET_ID
    # -----------------------------------------------------

    if "ASSET_ID" not in assets[0]:
        forms.alert("The CSV does not contain ASSET_ID.", title="Asset Update")
        return


    # -----------------------------------------------------
    # Index database
    # -----------------------------------------------------

    database = {}

    for asset in assets:
        try:
            asset_id = asset.get("ASSET_ID", "").strip()

            if asset_id:
                database[asset_id] = asset

        except:
            continue


    # -----------------------------------------------------
    # Collect Revit elements
    # -----------------------------------------------------

    elements = (
        FilteredElementCollector(doc)
        .WhereElementIsNotElementType()
        .ToElements()
    )


    # -----------------------------------------------------
    # Find matching elements
    # -----------------------------------------------------

    matches = {}

    for element in elements:
        try:
            param_id = element.LookupParameter("ASSET_ID")

            if not param_id:
                continue

            asset_id = get_parameter_value(param_id).strip()

            if not asset_id or asset_id not in database:
                continue

            if asset_id not in matches:
                matches[asset_id] = []

            matches[asset_id].append(element)

        except:
            continue


    # -----------------------------------------------------
    # Nothing matched
    # -----------------------------------------------------

    if not matches:
        forms.alert(
            "No Revit elements matched any ASSET_ID in the selected CSV.",
            title="Asset Update"
        )
        return


    # -----------------------------------------------------
    # Update
    # -----------------------------------------------------

    updated_parameters = 0
    updated_elements = set()
    skipped_nonshared = 0
    skipped_readonly = 0
    failed_parameters = 0

    with revit.Transaction("Update Assets"):

        for asset_id in matches:

            try:
                asset = database[asset_id]

                for element in matches[asset_id]:

                    element_updated = False

                    for column in asset:

                        try:
                            if column == "ASSET_ID":
                                continue

                            value = asset.get(column, "")
                            parameter_name = column

                            if column == "ASSET_KKS":
                                parameter_name = "Element_KKS1"

                            elif column == "ASSET_TYPE":
                                parameter_name = "Element_Instance"

                            param = element.LookupParameter(parameter_name)

                            if not param:
                                continue

                            if not param.IsShared:
                                skipped_nonshared += 1
                                continue

                            if param.IsReadOnly:
                                skipped_readonly += 1
                                continue

                            result = set_parameter_value(param, value)

                            if result is True:
                                updated_parameters += 1
                                updated_elements.add(element.Id.IntegerValue)
                                element_updated = True

                            elif result is False:
                                failed_parameters += 1

                        except:
                            failed_parameters += 1
                            continue


                    # Mark element as updated by Excel

                    if element_updated:

                        try:
                            update_param = element.LookupParameter("ASSET_UPDATE")

                            if (
                                update_param
                                and update_param.IsShared
                                and not update_param.IsReadOnly
                            ):
                                update_param.Set(1)

                        except:
                            pass

            except:
                continue


    # -----------------------------------------------------
    # Result
    # -----------------------------------------------------

    forms.alert(
        "Asset update complete.\n\n"
        "CSV records: {}\n"
        "Assets matched: {}\n"
        "Revit elements actually changed: {}\n"
        "Parameter values changed: {}\n\n"
        "Non-shared skipped: {}\n"
        "Read-only skipped: {}\n"
        "Parameter errors skipped: {}\n\n"
        "Database:\n{}".format(
            len(assets),
            len(matches),
            len(updated_elements),
            updated_parameters,
            skipped_nonshared,
            skipped_readonly,
            failed_parameters,
            csv_file
        ),
        title="Asset Update"
    )