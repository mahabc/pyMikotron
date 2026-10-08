import os
import sys

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

from ASSET_EXPORT import export_assets

export_assets()