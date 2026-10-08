import os
import sys

from pyrevit import revit

lib_path = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "lib"
    )
)

if lib_path not in sys.path:
    sys.path.append(lib_path)

from ASSET_PICKLIST import use_picklist


use_picklist()