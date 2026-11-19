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

TransactionManager.Instance.EnsureInTransaction(doc)

for m in materials:
    name = m.Name
    new_name = "AR" + name
    m.Name = new_name
    mat_names.append(new_name)

TransactionManager.Instance.TransactionTaskDone()


# Output
OUT = params