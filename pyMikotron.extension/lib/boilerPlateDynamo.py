import clr

# Revit API
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *

# Revit Services
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

# Current document
doc = DocumentManager.Instance.CurrentDBDocument

params = doc.ParameterBindings
# Main
""" 
H1 | GUID: 2c023d71-2ebb-40e6-853f-0e03574630e4 | ID: 3663060
H1 | GUID: 8a562c7c-1987-4701-9332-78702560d450 | ID: 6312358
H2 | GUID: 0448c371-5405-4149-b68b-b6b9c83563d6 | ID: 6312359
  """
        


# Output
OUT = params