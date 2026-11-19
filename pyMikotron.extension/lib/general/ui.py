# -*- coding: utf-8 -*-
"""Shared pyRevit dialogs (generic forms only) and remembered inputs."""
from pyrevit import forms, script

from Autodesk.Revit.DB import FilteredElementCollector, RevitLinkInstance

LOCAL = "Local model"


class Source(object):
    """A document to read from: the local model or a loaded link (with its transform)."""

    def __init__(self, name, doc, transform=None):
        self.name = name
        self.doc = doc
        self.transform = transform          # None = local model (identity)

    @property
    def is_link(self):
        return self.transform is not None


def loaded_links(doc):
    links = []
    for inst in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        link_doc = inst.GetLinkDocument()
        if link_doc is not None:
            links.append(Source(inst.Name, link_doc, inst.GetTotalTransform()))
    return sorted(links, key=lambda s: s.name)


def pick_sources(doc, title, multiselect=True):
    """Local model and/or loaded links. Returns a list of Source (exits on cancel)."""
    sources = [Source(LOCAL, doc)] + loaded_links(doc)
    if len(sources) == 1:
        return sources
    picked = forms.SelectFromList.show([s.name for s in sources], title=title,
                                       multiselect=multiselect, button_name="Select")
    if not picked:
        script.exit()
    picked = picked if multiselect else [picked]
    return [s for s in sources if s.name in picked]


def ask_text(prompt, title, default=""):
    """Text prompt; exits on cancel, returns stripped text (may be empty)."""
    value = forms.ask_for_string(default=default, prompt=prompt, title=title)
    if value is None:
        script.exit()
    return value.strip()


def ask_number(prompt, title, default):
    text = ask_text(prompt, title, str(default))
    try:
        return float(text.replace(",", "."))
    except ValueError:
        forms.alert("'{}' is not a number.".format(text), exitscript=True)


def pick_one(options, title, button="Select"):
    picked = forms.SelectFromList.show(options, title=title, multiselect=False, button_name=button)
    if not picked:
        script.exit()
    return picked


def pick_many(options, title, button="Select"):
    picked = forms.SelectFromList.show(options, title=title, multiselect=True, button_name=button)
    if not picked:
        script.exit()
    return picked


# ---------------------------------------------------------
# Remembered inputs (per tool, pyRevit user config)
# ---------------------------------------------------------
def recall(key, default):
    try:
        return script.get_config().get_option(key, default)
    except Exception:
        return default


def remember(**values):
    try:
        cfg = script.get_config()
        for key, value in values.items():
            setattr(cfg, key, value)
        script.save_config()
    except Exception:
        pass
