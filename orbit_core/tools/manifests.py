"""Write the three widgets' plugin.json and the core's from one description, so
the shared options never drift apart. Run after editing: python tools/manifests.py"""

from __future__ import annotations

import os as _os
import sys as _sys
from pathlib import Path as _Path

_TESSERAE = _Path(_os.environ.get("TESSERAE_REPO") or _Path(__file__).resolve().parents[3] / "tesserae")
if str(_TESSERAE) not in _sys.path:
    _sys.path.insert(0, str(_TESSERAE))

import importlib.util as _ilu
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.1.1"
TESSERAE_MIN = "0.463.0"

_spec = _ilu.spec_from_file_location("_tesserae_plugins.orbit_core.paint", ROOT / "orbit_core" / "lib" / "paint.py")
_paint = _ilu.module_from_spec(_spec)
sys.modules[_spec.name] = _paint
_spec.loader.exec_module(_paint)
STYLES = [(k, v[0]) for k, v in _paint.STYLES.items()] + [("builder", "Build my own"), ("custom", "Your own prompt")]
BUILDER = {name: (label, default, [(v, lab) for v, lab, _p in choices]) for name, (label, default, choices) in _paint.BUILDER.items()}
PRESETS = _paint.CUSTOM_PRESETS
BACKDROPS = [(k, v[0]) for k, v in _paint.BACKDROPS.items()]
MODELS = [(k, f"{v['label']} ({v['cost']})") for k, v in _paint.MODELS.items()]


def sel(name, label, default, choices, **kw):
    return {"name": name, "type": "select", "label": label, "default": default, "choices": [{"value": v, "label": l} for v, l in choices], **kw}


def where_options():
    return [
        {"name": "location", "type": "location_search", "label": "Place", "default": "", "help": "Where you will be looking up from; the times are the place's own. Falls back to the app's location."},
        sel("which", "Which objects", "bright", [("bright", "The stations and the brightest satellites (CelesTrak's visual list)"), ("stations", "The space stations only")], help="The visual list is the hundred-odd objects bright enough to see with the eye: the stations, Hubble, big satellites and spent rocket stages."),
        sel("min_el", "At least this high", "20", [("10", "10° (low over the horizon)"), ("20", "20°"), ("30", "30°"), ("45", "45° (high overhead)")], help="A pass counts when the object climbs at least this high while lit and the sky is dark."),
        sel("hours", "Looking ahead", "24", [("12", "12 hours"), ("24", "24 hours"), ("36", "36 hours")]),
    ]


def picture_options(with_backdrop: bool, scene: bool = False):
    show = {"pictures": "paintings"}
    out = [
        sel("pictures", "Pictures", "paintings", [("paintings", "AI paintings, each object once"), ("silhouettes", "Silhouettes")], help="AI paintings paint each object once in the style below, from a NASA photograph for the station and Hubble and from its description otherwise, at about US$0.04 a painting; needs a fal.ai key. Silhouettes cost nothing."),
        sel("style", "Style", "poster", STYLES, show_if=show),
        {"name": "custom_style", "type": "textarea", "label": "Your own prompt", "default": "", "show_if": {"pictures": "paintings", "style": "custom"}, "presets": PRESETS, "help": "The medium and the look; the widget adds the spacecraft and the paper. Pick an example above to start from."},
    ]
    for name, (label, default, choices) in BUILDER.items():
        out.append(sel(f"build_{name}", label, default, choices, show_if={"pictures": "paintings", "style": "builder"}))
    out.append({"name": "build_extra", "type": "string", "label": "Your own words", "default": "", "show_if": {"pictures": "paintings", "style": "builder"}, "help": "Added to the style: for example, with a little gold leaf on the solar panels."})
    if with_backdrop:
        out.append(sel("backdrop", "Backdrop", "space" if scene else "none", BACKDROPS if not scene else BACKDROPS[1:], show_if=show, help="None keeps the spacecraft alone on the page, cut out. The rest paint a whole picture that fills its frame, in the same style."))
    out.append(sel("view", "View", "side", [("side", "From the side, a little below"), ("quarter", "From a front quarter, a little above"), ("below", "From below, as it passes over you"), ("above", "From above, the Earth beyond")], show_if=show))
    out.append(sel("model", "Model", "nano_banana", MODELS, show_if=show, help="All on fal.ai. Nano Banana is faithful and cheap; Nano Banana Pro and FLUX follow the more abstract styles further."))
    return out


def page_options(paper_default="cream"):
    return [
        sel("chart", "Sky chart", "dome", [("dome", "The sky as a dome, north up, the path drawn across it"), ("none", "No chart")]),
        {"name": "title", "type": "string", "label": "Title", "default": "", "help": "Blank uses the place."},
        sel("header", "Title line", "top", [("top", "Above the page"), ("bottom", "Below the page"), ("hidden", "Hidden")]),
        sel("footer", "Foot of the page", "show", [("show", "Status and credits"), ("credits", "Credits only"), ("hide", "Nothing")]),
        sel("paper", "Paper", paper_default, [("cream", "Cream"), ("white", "White"), ("aged", "Aged"), ("blueprint", "Blueprint: pale ink on blue"), ("night", "Night: pale ink on near-black")]),
        sel("panel", "Panel", "colour", [("colour", "Colour"), ("gray16", "16 greys"), ("gray4", "4 greys"), ("mono", "Black and white")], help="What the panel can show. Pictures are converted and contrast-stretched to match."),
        sel("text_size", "Text size", "100", [(v, f"{v}%") for v in ("60", "80", "100", "125", "150")]),
        sel("font", "Type", "fell", [("fell", "IM Fell English: the old plate"), ("archivo", "Archivo Narrow: clean and plain"), ("georgia", "Georgia: a modern serif"), ("page", "The dashboard's own font")]),
    ]


WIDGETS = {
    "orbit_pass": {
        "name": "Orbit: Pass",
        "icon": "ph-planet",
        "description": "The best pass over your place to-night: the station or the brightest satellite coming, painted in a ruled frame, with a sky chart of its path, the rise and set times and directions, how high and how bright. Passes worked out on your server from CelesTrak's element sets, no key.",
        "options": lambda: where_options() + picture_options(True) + page_options(),
    },
    "orbit_tonight": {
        "name": "Orbit: To-night",
        "icon": "ph-shooting-star",
        "description": "Every visible pass over your place in the next day, in order: the station and the bright satellites, each with its small painting and a sky chart of its path, the times, the directions and how bright. Worked out on your server from CelesTrak's element sets, no key.",
        "options": lambda: where_options() + [{"name": "count", "type": "number", "label": "How many", "default": 6, "help": "1 to 10."}] + picture_options(False) + [
            sel("layout", "Layout", "rows", [("rows", "Rows: each pass with its picture and sky chart"), ("cluster", "Cluster: the objects packed on the page, sized as they are, captioned")], help="The cluster packs each object's painting or silhouette as large as the page allows, the station a hundred metres across and a rocket stage ten, with its next pass captioned beneath."),
            {"name": "scale", "type": "slider", "label": "Scale", "default": 100, "min": 40, "max": 100, "step": 5, "unit": "%", "help": "How far the cluster runs out to the margins.", "show_if": {"layout": "cluster"}},
        ] + page_options(),
    },
    "orbit_scene": {
        "name": "Orbit: Scene",
        "icon": "ph-moon-stars",
        "description": "The best pass coming as one whole painting across the page: the spacecraft in black space, above the Earth's limb, over the Earth by day or by night or at an orbital sunrise, with the pass written over it and a sky chart in the corner.",
        "options": lambda: where_options() + picture_options(True, scene=True) + page_options("night"),
    },
}

CORE = {
    "tesserae_compat": "1.x",
    "tesserae_min": TESSERAE_MIN,
    "name": "Orbit Core",
    "version": VERSION,
    "kind": "data",
    "description": "The settings and the paintings page for the Orbit widgets (orbit_pass, orbit_tonight, orbit_scene): the fal.ai key, the daily painting budget and a contact for CelesTrak and Wikimedia Commons. No widget of its own.",
    "icon": "ph-planet",
    "supports": {"sizes": []},
    "requires": ["network:*"],
    "settings": [
        {"name": "fal_api_key", "type": "string", "label": "fal.ai API key (AI paintings)", "secret": True, "default": "", "help": "With a key the widgets can paint each object once, at about US$0.04 a painting. Leave it blank to use the key under Settings › Generative AI. Without either the widgets show silhouettes."},
        {"name": "contact", "type": "string", "label": "Contact for CelesTrak and Wikimedia Commons", "default": "", "help": "An email address or a web page, sent in the widget's User-Agent. The widget names its own project page by default."},
        {"name": "gen_daily_usd", "type": "slider", "label": "Painting budget per day", "default": 2, "min": 0, "max": 30, "step": 1, "unit": "US$", "help": "The most the widgets may spend on new paintings in a day, at the models' listed prices. 0 is no limit, within the ceiling under Settings › Generative AI. The visual list is a fixed hundred-odd objects, so a style is painted out in a few weeks and then costs nothing."},
        {"name": "gen_per_refresh", "type": "number", "label": "New paintings started per preview", "default": 3, "help": "How many new paintings one settled preview in the editor may start (1 to 50)."},
        {"name": "gen_parallel", "type": "number", "label": "Paintings made at once", "default": 3, "help": "How many paintings fal.ai works on side by side (1 to 8)."},
    ],
}

(ROOT / "orbit_core" / "plugin.json").write_text(json.dumps(CORE, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
for wid, w in WIDGETS.items():
    manifest = {
        "tesserae_compat": "1.x",
        "name": w["name"],
        "version": VERSION,
        "kind": "widget",
        "tesserae_min": TESSERAE_MIN,
        "description": w["description"],
        "icon": w["icon"],
        "supports": {"sizes": ["sm", "md", "lg"]},
        "requires": ["network:*", "settings:plugin/orbit_core", "plugin:orbit_core"],
        "render": {"needs_network": True, "warm_ahead_s": 150},
        "design": {"palette": "extended"},
        "cell_options": w["options"](),
        "data_schema": {"fields": [{"name": "title", "type": "str", "label": "Title"}, {"name": "found", "type": "num", "label": "Passes in the window"}, {"name": "passes", "type": "arr", "label": "Passes shown"}]},
    }
    names = [o["name"] for o in manifest["cell_options"]]
    assert len(names) == len(set(names)), wid
    (ROOT / wid / "plugin.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(wid, len(names), "options")
