from pyrevit import revit, forms
from Autodesk.Revit.DB import *
import uuid


doc = revit.doc


# ---------------------------------------------------------
# GUID
# ---------------------------------------------------------

def generate_guid():

    return str(uuid.uuid4()).upper()


# ---------------------------------------------------------
# Parameter value
# ---------------------------------------------------------

def get_parameter_value(element, parameter_name):

    param = element.LookupParameter(parameter_name)

    if not param:
        return ""

    try:

        if param.StorageType == StorageType.String:

            value = param.AsString()

            if value is None:
                return ""

            return value

        elif param.StorageType == StorageType.Integer:

            return str(param.AsInteger())

        elif param.StorageType == StorageType.Double:

            value = param.AsValueString()

            if value is None:
                return ""

            return value

        elif param.StorageType == StorageType.ElementId:

            value = param.AsValueString()

            if value:
                return value

            element_id = param.AsElementId()

            if element_id == ElementId.InvalidElementId:
                return ""

            referenced = doc.GetElement(element_id)

            if referenced:

                try:
                    return referenced.Name
                except:
                    return str(element_id.IntegerValue)

            return str(element_id.IntegerValue)

    except:
        return ""

    return ""


# ---------------------------------------------------------
# Pick additional parameters
# ---------------------------------------------------------

def choose_parameters(elements):

    excluded = [
        "ASSET_ID",
        "Element_KKS1",
        "Element_Instance",
        "ASSET_PICK"
    ]

    parameter_names = set()

    for element in elements:

        for param in element.Parameters:

            try:

                name = param.Definition.Name

                if name not in excluded:
                    parameter_names.add(name)

            except:
                pass


    parameter_names = sorted(parameter_names)

    if not parameter_names:
        return []


    selected = forms.SelectFromList.show(
        parameter_names,
        title="Select Additional Parameters",
        button_name="Add Columns",
        multiselect=True
    )

    if not selected:
        return []

    return selected


# ---------------------------------------------------------
# Choose conflicting value
# ---------------------------------------------------------

def choose_conflict(asset_id, parameter_name, values):

    selected = forms.SelectFromList.show(
        values,
        title="Select Value",
        button_name="Use Value",
        multiselect=False
    )

    if not selected:

        forms.alert(
            "No value was selected.\n\n"
            "Asset:\n{}\n\n"
            "Parameter:\n{}".format(
                asset_id,
                parameter_name
            ),
            title="Asset Value Conflict"
        )

        return values[0]

    return selected


# ---------------------------------------------------------
# Resolve values within one asset
# ---------------------------------------------------------

def resolve_value(asset_id, parameter_name, elements):

    values = []

    for element in elements:

        value = get_parameter_value(
            element,
            parameter_name
        )

        if value not in values:
            values.append(value)


    # Remove blanks when a real value exists

    non_empty = [
        value
        for value in values
        if value != ""
    ]


    # All blank

    if len(non_empty) == 0:
        return ""


    # One real value

    if len(non_empty) == 1:
        return non_empty[0]


    # Multiple values = input error

    return choose_conflict(
        asset_id,
        parameter_name,
        non_empty
    )


# ---------------------------------------------------------
# CSV
# ---------------------------------------------------------

def csv_value(value):

    if value is None:
        value = ""

    value = str(value)

    value = value.replace('"', '""')

    return '"' + value + '"'


def csv_split(line):

    values = []

    current = ""
    quoted = False
    i = 0

    while i < len(line):

        char = line[i]

        if char == '"':

            if quoted and i + 1 < len(line) and line[i + 1] == '"':

                current += '"'
                i += 1

            else:

                quoted = not quoted

        elif char == "," and not quoted:

            values.append(current)
            current = ""

        else:

            current += char

        i += 1


    values.append(current)

    return values


def read_csv_database(csv_file):

    rows = []

    with open(csv_file, "rb") as f:

        lines = f.readlines()


    if not lines:
        return [], []


    headers = csv_split(
        lines[0].decode("utf-8-sig")
        .rstrip("\r\n")
    )


    for line in lines[1:]:

        line = line.decode("utf-8-sig").rstrip("\r\n")

        if not line:
            continue

        values = csv_split(line)

        row = {}

        for i, header in enumerate(headers):

            if i < len(values):
                row[header] = values[i]

            else:
                row[header] = ""


        rows.append(row)


    return headers, rows


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def export_assets():

    # -----------------------------------------------------
    # Pick existing CSV database
    # -----------------------------------------------------

    csv_file = forms.pick_file(
        file_ext="csv",
        title="Select Asset Database"
    )

    if not csv_file:
        return


    # -----------------------------------------------------
    # Read existing database
    # -----------------------------------------------------

    database_headers, database_rows = read_csv_database(
        csv_file
    )


    # -----------------------------------------------------
    # Collect picked Revit elements
    # -----------------------------------------------------

    elements = []

    all_elements = (
        FilteredElementCollector(doc)
        .WhereElementIsNotElementType()
        .ToElements()
    )


    for element in all_elements:

        param_pick = element.LookupParameter(
            "ASSET_PICK"
        )

        if not param_pick:
            continue


        try:

            if param_pick.StorageType == StorageType.Integer:

                if param_pick.AsInteger() == 1:
                    elements.append(element)

        except:
            pass


    if not elements:

        forms.alert(
            "No Revit elements have ASSET_PICK checked.",
            title="Asset Export"
        )

        return


    # -----------------------------------------------------
    # Generate missing ASSET_ID values
    # -----------------------------------------------------

    new_ids = []

    with revit.Transaction("Generate Asset IDs"):

        for element in elements:

            param_id = element.LookupParameter(
                "ASSET_ID"
            )

            if not param_id:
                continue

            value = get_parameter_value(
                element,
                "ASSET_ID"
            )


            if not value:

                new_id = generate_guid()

                if not param_id.IsReadOnly:

                    param_id.Set(new_id)

                    new_ids.append(new_id)


    # -----------------------------------------------------
    # Group Revit elements by ASSET_ID
    # -----------------------------------------------------

    asset_groups = {}


    for element in elements:

        param_id = element.LookupParameter(
            "ASSET_ID"
        )

        if not param_id:
            continue


        asset_id = get_parameter_value(
            element,
            "ASSET_ID"
        )


        if not asset_id:
            continue


        if asset_id not in asset_groups:

            asset_groups[asset_id] = []


        asset_groups[asset_id].append(element)


    if not asset_groups:

        forms.alert(
            "No valid ASSET_ID values were found.",
            title="Asset Export"
        )

        return


    # -----------------------------------------------------
    # Select additional Revit parameters
    # -----------------------------------------------------

    additional_columns = choose_parameters(
        elements
    )


    # -----------------------------------------------------
    # Ensure database columns exist
    # -----------------------------------------------------

    columns = []

    for column in database_headers:

        if column not in columns:
            columns.append(column)


    for column in [
        "ASSET_ID",
        "ASSET_KKS",
        "ASSET_TYPE"
    ]:

        if column not in columns:
            columns.append(column)


    for column in additional_columns:

        if column not in columns:
            columns.append(column)


    # -----------------------------------------------------
    # Index existing database by ASSET_ID
    # -----------------------------------------------------

    database_index = {}

    for row in database_rows:

        asset_id = row.get(
            "ASSET_ID",
            ""
        )

        if asset_id:

            database_index[asset_id] = row


    # -----------------------------------------------------
    # Update / add assets
    # -----------------------------------------------------

    for asset_id in asset_groups:

        asset_elements = asset_groups[
            asset_id
        ]


        # Existing row

        if asset_id in database_index:

            row = database_index[asset_id]

        # New row

        else:

            row = {
                column: ""
                for column in columns
            }

            row["ASSET_ID"] = asset_id

            database_rows.append(row)

            database_index[asset_id] = row


        # -------------------------------------------------
        # Core values
        # -------------------------------------------------

        row["ASSET_ID"] = asset_id

        row["ASSET_KKS"] = resolve_value(
            asset_id,
            "Element_KKS1",
            asset_elements
        )

        row["ASSET_TYPE"] = resolve_value(
            asset_id,
            "Element_Instance",
            asset_elements
        )


        # -------------------------------------------------
        # Additional parameters
        # -------------------------------------------------

        for parameter_name in additional_columns:

            row[parameter_name] = resolve_value(
                asset_id,
                parameter_name,
                asset_elements
            )


    # -----------------------------------------------------
    # Overwrite selected CSV database
    # -----------------------------------------------------

    with open(csv_file, "w") as f:

        f.write(
            ",".join(
                [
                    csv_value(column)
                    for column in columns
                ]
            ) + "\n"
        )


        for row in database_rows:

            values = []

            for column in columns:

                values.append(
                    csv_value(
                        row.get(column, "")
                    )
                )


            f.write(
                ",".join(values) + "\n"
            )


    # -----------------------------------------------------
    # Finished
    # -----------------------------------------------------

    forms.alert(
        "Asset database updated.\n\n"
        "Assets in database: {}\n"
        "Revit asset groups exported: {}\n"
        "Revit elements: {}\n"
        "New ASSET_ID values: {}\n\n"
        "Database:\n{}".format(
            len(database_rows),
            len(asset_groups),
            len(elements),
            len(new_ids),
            csv_file
        ),
        title="Asset Export"
    )