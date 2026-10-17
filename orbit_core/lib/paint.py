"""AI paintings of spacecraft through fal.ai: each object painted once, from a
reference picture where there is a free one (the station, Hubble) and from
its description otherwise, in a style, on white paper (cut out on the page)
or as a whole picture in space. The prompts and the styles are here; the
budget, the queue, the files and the admin page are Tesserae's
(``app.artwork``, 0.463 and later). Loaded by path."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import re
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _sibling(name: str) -> Any:
    full = f"_tesserae_plugins.orbit_core.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, _HERE / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


N = _sibling("net")

try:
    from app import artwork  # Tesserae 0.463+: the pictures a widget makes and keeps
    from app import fal as _fal
except (
    ImportError
):  # an older Tesserae: the widgets still draw, with silhouettes, and say why
    artwork = None  # type: ignore[assignment]
    _fal = None  # type: ignore[assignment]

NEEDS_HOST = "AI paintings need Tesserae 0.463 or later; this server is older, so silhouettes show."


class _NoArt:
    key = ""
    preview = False
    settled = True
    subject = ""
    cell = ""
    cap = 0
    started = 0
    pending = 0
    busy = False
    c = None

    def __init__(self) -> None:
        self.states: dict[str, int] = {}
        self.asked: dict[str, Any] = {}
        self.data_dir = Path(".")

    def request(
        self, key: str, payload: dict[str, Any], *, title: str = "", want: bool = True
    ) -> Any:
        from types import SimpleNamespace

        self.states["no_host"] = self.states.get("no_host", 0) + 1
        return SimpleNamespace(
            key=key,
            state="no_host",
            ready=False,
            path=None,
            meta={},
            why=NEEDS_HOST,
            credit="",
        )

    def url(self, *a: Any, **k: Any) -> str:
        return ""

    def live(self) -> dict[str, int]:
        return {"live_refresh_s": 0, "live_pending": 0}

    def notes(self) -> list[str]:
        return [NEEDS_HOST] if self.states.get("no_host") else []

    def status(self) -> list[str]:
        return []

    def finish(self, *a: Any, **k: Any) -> None:
        return None


class _NoArtwork:
    name = "paintings"
    href = "/plugins/orbit_core/"
    actions: list[Any] = []
    extra_template = None
    extra_context = None
    _DEFAULTS: dict[str, Any] = {
        "state": "none",
        "why_failed": "",
        "held": {},
        "dashboards": [],
        "listing": [],
        "errors": [],
        "versions": [],
        "budget_used": 0,
        "cap": 0,
        "adopt": False,
        "progress": {
            "running": [],
            "queued": [],
            "finished": [],
            "used": 0,
            "cap": 0,
            "used_text": "",
            "cap_text": "",
            "held": 0,
        },
    }

    def open(
        self,
        ctx: dict[str, Any],
        settings: dict[str, Any] | None,
        *,
        subject: str = "",
        cell: str = "",
    ) -> _NoArt:
        return _NoArt()

    def folder(self, data_dir: Path) -> Path:
        return Path(data_dir) / self.name

    def __getattr__(self, name: str) -> Any:
        default = self._DEFAULTS.get(name)
        return lambda *a, **k: default


MODELS: dict[str, dict[str, str]] = {
    "nano_banana": {"label": "Nano Banana", "cost": "about US$0.04", "cents": 4},
    "nano_banana_pro": {
        "label": "Nano Banana Pro",
        "cost": "about US$0.15",
        "cents": 15,
    },
    "flux_kontext": {
        "label": "FLUX.1 Kontext Pro",
        "cost": "about US$0.04",
        "cents": 4,
    },
    "gpt_image": {"label": "GPT Image 2", "cost": "about US$0.05", "cents": 5},
    "seedream": {"label": "Seedream 4", "cost": "about US$0.03", "cents": 3},
}
DEFAULT_MODEL = "nano_banana"
UNLIMITED = artwork.UNLIMITED if artwork is not None else 10**9
PROMPT_VERSION = 1
CUT_VERSION = 1
NOTE_NO_KEY = "AI pictures need a fal.ai key: this widget's own, or the app's under Settings › Generative AI."

STYLES: dict[str, tuple[str, str]] = {
    "poster": (
        "Space-age poster",
        "a vintage space-age poster illustration in gouache, in the manner of the 1960s agency posters: flat confident shapes, a limited palette of deep blue, silver, gold and vermilion, crisp edges with a little paper texture, the spacecraft rendered with affection and accuracy",
    ),
    "engraving_colour": (
        "Hand-coloured engraving",
        "a hand-coloured copperplate engraving from a nineteenth-century astronomical atlas: fine engraved linework and stippling under delicate watercolour washes",
    ),
    "engraving": (
        "Black-ink engraving",
        "a black-ink copperplate engraving from a Victorian encyclopaedia: fine cross-hatching and stippling, no colour at all",
    ),
    "technical": (
        "Engineering drawing",
        "a precise technical ink illustration from an aerospace manufacturer's manual: clean ruled linework, light hatching for shadow, the panels, trusses and antennas drawn, no colour",
    ),
    "watercolour": (
        "Loose watercolour",
        "a loose, airy watercolour with soft wet edges, a few precise details on the solar panels and antennas and plenty of white space",
    ),
    "woodblock": (
        "Japanese woodblock print",
        "a Japanese woodblock print: flat areas of colour with a fine dark keyline and the texture of washi paper",
    ),
    "linocut": (
        "Linocut",
        "a bold linocut print in black ink with one muted colour: strong carved lines, simple shapes, a little texture from the block",
    ),
    "deco": (
        "Art Deco",
        "an Art Deco poster of the 1930s imagining the future: streamlined geometric shapes, sweeping speed lines, a palette of cream, teal and vermilion, airbrushed gradients",
    ),
    "midcentury": (
        "Mid-century flat illustration",
        "a mid-century modern illustration in the manner of a 1960s children's book about space: the spacecraft reduced to clean geometric shapes, flat colour in a handful of tones, no outlines",
    ),
    "pencil": (
        "Pencil study",
        "a careful graphite pencil study: soft shading, the metal's sheen suggested with a few highlights, no colour",
    ),
    "blueprint": (
        "Blueprint",
        "a cyanotype blueprint: fine white linework on deep Prussian blue paper, dimension ticks and construction lines",
    ),
    "cutaway": (
        "Magazine cutaway",
        "a 1960s magazine cutaway illustration: the spacecraft opened to show its modules, tanks and crew quarters in neat sections, tiny figures inside, painted in gouache with a draughtsman's precision",
    ),
    "stamp": (
        "Postage stamp",
        "a finely engraved postage stamp commemorating a space mission: the spacecraft in the stamp's engraved linework within an ornate perforated border, the country and value lettered in the stamp's own style, the whole stamp filling the picture",
    ),
    "riso": (
        "Risograph",
        "a two-colour risograph print in fluorescent pink and blue ink only: the spacecraft reduced to two overprinted flat ink layers with grainy texture, slight misregistration and coarse halftone shading",
    ),
    "pixel": (
        "Pixel art",
        "coarse pixel art as from a 16-bit video game: the spacecraft drawn at a tiny resolution of about 96 pixels across and scaled up so every square pixel is plainly visible, a palette of sixteen colours, stair-stepped edges, dithered shading, nothing smooth",
    ),
    "lowpoly": (
        "Low-poly render",
        "a low-polygon 3D render: the spacecraft built from a few hundred large flat-shaded triangles so that every facet shows as a visible flat plane with a hard edge, no smooth surfaces, soft studio lighting",
    ),
    "papercraft": (
        "Paper craft",
        "a paper model of the spacecraft made from cut and folded card, photographed on a table: visible folds, glued tabs and the cut edges of the card, lit from the side",
    ),
    "toybrick": (
        "Toy bricks",
        "a model of the spacecraft built from interlocking plastic toy bricks, rendered as a product photograph: rows of round studs, every curve stepped into blocky brick shapes, glossy moulded plastic",
    ),
    "charcoal": (
        "Charcoal",
        "a drawing in charcoal sticks on rough toothy paper: visibly smudged by hand, strokes and finger-rubbed shading plain to see, a few sharp lines on the panels, nothing photographic, no colour",
    ),
    "stained_glass": (
        "Stained glass",
        "a stained-glass window design: the spacecraft made of flat panes of coloured glass separated by thick black lead lines, the light coming through the glass",
    ),
    "gilt": (
        "Illuminated manuscript",
        "an illuminated manuscript miniature: the spacecraft painted in tempera with gold leaf on the solar panels, a fine red and blue filigree border with stars",
    ),
    "pulp": (
        "Pulp cover",
        "a 1950s pulp science-fiction magazine cover painting: airbrushed, dramatic, saturated, the spacecraft heroic against the stars",
    ),
    "synthwave": (
        "Synthwave",
        "a synthwave illustration: neon pink and cyan on a dark purple ground, a glowing grid horizon and a striped sun, the spacecraft in chrome",
    ),
    "chalk": (
        "Chalkboard",
        "a chalk drawing on a dark blackboard: white and coloured chalk, soft smudges, the lines a little dusty, as on a planetarium's board",
    ),
    "atlas": (
        "Celestial atlas",
        "a plate from a seventeenth-century celestial atlas: the spacecraft drawn among constellation figures and gilt stars on aged paper, fine engraved lines and muted hand colour",
    ),
}
STYLE_IDS = (*STYLES, "builder", "custom")
MONO = {"engraving", "technical", "pencil", "charcoal"}
OWN_PAPER = {"blueprint", "stamp", "synthwave", "chalk", "gilt", "pulp", "atlas"}
CUSTOM_EXAMPLE = "a chalk pastel drawing on grey paper, soft and smudgy, with the sun catching the solar panels"
CUSTOM_PRESETS = [
    {
        "label": "Gouache poster",
        "value": "a vintage space-age poster in gouache: flat confident shapes, a palette of deep blue, silver and vermilion, crisp edges",
    },
    {
        "label": "Cutaway",
        "value": "a 1960s magazine cutaway illustration: the spacecraft opened to show its modules and crew, labelled in small neat capitals",
    },
    {"label": "Chalk pastel", "value": CUSTOM_EXAMPLE},
    {
        "label": "Space art",
        "value": "a traditional painting in the manner of classic space art: dramatic sunlight, the Earth's limb below, confident brushwork",
    },
    {
        "label": "Comic ink",
        "value": "a comic-book ink drawing with bold outlines, hatched shadows and flat halftone colour",
    },
    {
        "label": "Neon line",
        "value": "a single-weight neon line drawing on white: one continuous glowing line describing the spacecraft",
    },
]
_CUSTOM_RE = re.compile(r"custom[a-z]{8}")
BUILDER: dict[str, tuple[str, str, tuple[tuple[str, str, str], ...]]] = {
    "medium": (
        "Medium",
        "gouache",
        (
            ("gouache", "Gouache", "a flat gouache painting"),
            ("watercolour", "Watercolour", "a loose watercolour painting"),
            ("oil", "Oil paint", "an oil painting with visible brushwork"),
            ("pastel", "Soft pastel", "a soft pastel drawing"),
            ("coloured_pencil", "Coloured pencil", "a coloured-pencil drawing"),
            ("pencil", "Graphite pencil", "a graphite pencil drawing"),
            ("ink", "Pen and ink", "a pen-and-ink drawing"),
            ("engraving", "Engraving", "a copperplate engraving"),
            ("lithograph", "Lithograph", "a hand-coloured lithograph"),
            ("woodblock", "Woodblock", "a woodblock print"),
            ("linocut", "Linocut", "a linocut print"),
            ("screenprint", "Screen print", "a screen print with a few flat inks"),
            ("vector", "Flat vector", "a flat vector illustration"),
            ("airbrush", "Airbrush", "an airbrushed illustration"),
            ("papercut", "Paper cut", "layered cut paper"),
        ),
    ),
    "period": (
        "Period or school",
        "",
        (
            ("", "None in particular", ""),
            (
                "1950s",
                "1950s science-fiction cover",
                "in the manner of a 1950s science-fiction magazine cover",
            ),
            (
                "1960s",
                "1960s space-age poster",
                "in the manner of a 1960s space-age poster",
            ),
            (
                "victorian",
                "Victorian technical plate",
                "in the manner of a Victorian technical plate",
            ),
            (
                "atlas",
                "Celestial atlas",
                "in the manner of a seventeenth-century celestial atlas",
            ),
            ("bauhaus", "Bauhaus", "in the Bauhaus manner"),
            ("ukiyoe", "Ukiyo-e", "in the manner of a Japanese ukiyo-e print"),
            ("deco", "Art Deco", "in the Art Deco manner"),
            ("retrofuture", "Retro-futurism", "in a retro-futurist manner"),
        ),
    ),
    "palette": (
        "Palette",
        "",
        (
            ("", "As it is", ""),
            ("limited", "A few warm tones", "in a limited palette of a few warm tones"),
            ("muted", "Muted", "in muted, dusty colours"),
            ("vivid", "Vivid", "in vivid saturated colour"),
            ("duotone", "Two inks", "in two inks only"),
            ("mono", "Black and white", "in black and white only"),
            ("sepia", "Sepia", "in sepia tones"),
        ),
    ),
    "line": (
        "Line",
        "",
        (
            ("", "As the medium has it", ""),
            ("fine", "Fine", "with fine delicate line"),
            ("bold", "Bold", "with bold confident outlines"),
            ("none", "No outlines", "with no outlines, shapes meeting edge to edge"),
            ("sketchy", "Sketchy", "with loose sketchy line"),
        ),
    ),
    "texture": (
        "Texture",
        "",
        (
            ("", "As the medium has it", ""),
            ("paper", "Paper grain", "with visible paper grain"),
            (
                "print",
                "Print texture",
                "with the texture of a print, slightly misregistered",
            ),
            ("smooth", "Smooth", "smooth and clean"),
            ("halftone", "Halftone", "with halftone dots in the shading"),
        ),
    ),
    "mood": (
        "Mood",
        "",
        (
            ("", "Plain", ""),
            ("heroic", "Heroic", "heroic and dramatic, lit from below by the Earth"),
            ("calm", "Calm", "calm and serene"),
            ("nostalgic", "Nostalgic", "warm and nostalgic"),
            ("technical", "Precise", "precise and matter-of-fact"),
        ),
    ),
}


def build_how(options: dict[str, Any]) -> str:
    parts: list[str] = []
    for name, (_label, default, choices) in BUILDER.items():
        pick = str(options.get(f"build_{name}") or default)
        phrase = next((p for v, _l, p in choices if v == pick), "")
        if name == "medium":
            phrase = (phrase or choices[0][2]) + " of the {kind}"
        if phrase:
            parts.append(phrase)
    extra = " ".join(str(options.get("build_extra") or "").split())[:300]
    if extra:
        parts.append(extra)
    return ", ".join(parts)


BACKDROPS: dict[str, tuple[str, str]] = {
    "none": ("None: the spacecraft alone, cut out on the page", ""),
    "space": (
        "Black space and stars",
        "black space scattered with stars in the same style, the spacecraft lit hard from one side by the sun",
    ),
    "limb": (
        "Above the Earth's limb",
        "the blue curve of the Earth's limb below with its thin bright atmosphere, black space above, in the same style",
    ),
    "earth": (
        "Over the Earth by day",
        "the Earth below filling the lower picture, oceans, clouds and coastlines in the same style, the spacecraft passing over",
    ),
    "night": (
        "Over the Earth by night",
        "the Earth by night below, city lights in the dark and a faint airglow at the limb, in the same style",
    ),
    "sunrise": (
        "Orbital sunrise",
        "an orbital sunrise in the same style, the sun breaking over the Earth's limb and the spacecraft lit in gold",
    ),
    "ornate": (
        "Ornate framed plate",
        "a decorative backdrop in the same style, a patterned or foliate ground with stars within a drawn ornamental border that fills the whole picture to its edges, the page's own art in that style and nothing modern",
    ),
}
GEN_REF = (
    "Draw the spacecraft in the reference photo, {name}, afresh as {style}: a new illustration of this very "
    "spacecraft in that style, not the photo restyled. The reference photo is for identity only: its exact modules, "
    "trusses, solar arrays, antennas, colours and proportions are kept. It is {what}. Seen {view}{scene}. {page} No "
    "text or lettering, no border, no signature.{outline}"
)
GEN_WORDS = (
    "Draw {what_cap}, {name}, as {style}: a plausible, specific, well-observed spacecraft of that kind, seen "
    "{view}{scene}. {page} No text or lettering beyond any markings a real one carries, no border, no signature.{outline}"
)
PAGE_ALONE = (
    "The spacecraft alone on plain, pure white paper with a clear margin all round and nothing else on the page: "
    "no space, stars, Earth, glow, shadow or ornament round or behind it. The style says how the spacecraft is "
    "drawn and nothing else."
)
PAGE_WHOLE = "The picture complete, filling the frame edge to edge."
OUTLINE = (
    " The whole spacecraft is drawn with a fine, clear, unbroken dark contour line along its entire outline, "
    "modules, trusses, panels and antennas, so that a white or pale part is never lost against the white paper."
)
VIEWS = {
    "side": "from the side and a little below, as from a chase craft",
    "quarter": "from a front quarter, a little above",
    "below": "from below, as it would pass over an observer on the ground, foreshortened against the sky",
    "above": "from above, looking down past it at the Earth",
}


def style_of(style: str | None) -> tuple[str, str]:
    if style in STYLES:
        return STYLES[style]
    if style and _CUSTOM_RE.fullmatch(style):
        return ("Your own style", _CUSTOM.get(style, ""))
    return STYLES["poster"]


def custom_tag(how: str) -> str:
    digest = hashlib.sha1(
        " ".join(how.split()).lower().encode(), usedforsecurity=False
    ).hexdigest()
    return "custom" + "".join(
        "abcdefghijklmnopqrstuvwxyz"[int(c, 16) % 26] for c in digest[:8]
    )


_CUSTOM: dict[str, str] = {}


def register_custom(how: str) -> str:
    tag = custom_tag(how)
    _CUSTOM[tag] = how
    return tag


def key_for(
    norad: int,
    style: str,
    backdrop: str = "none",
    view: str = "side",
    model: str = DEFAULT_MODEL,
) -> str:
    parts = [f"sat_{norad}", style, f"p{PROMPT_VERSION}"]
    if backdrop != "none":
        parts.append(f"bd_{backdrop}")
    if view != "side":
        parts.append(f"v_{view}")
    if model != DEFAULT_MODEL:
        parts.append(f"m_{model}")
    return "--".join(parts)


def prompt_for(job: dict[str, Any]) -> str:
    _label, how = style_of(job.get("style"))
    how = str(job.get("how") or how).replace("{kind}", "spacecraft")
    style = str(job.get("style") or "")
    backdrop = str(job.get("backdrop") or "none")
    alone = backdrop == "none" and style not in OWN_PAPER
    scene = ""
    if backdrop == "ornate":
        scene = (
            ", as the single subject of an ornate framed plate: the spacecraft large in the middle on "
            + BACKDROPS["ornate"][1]
        )
    elif backdrop in BACKDROPS and backdrop != "none":
        scene = f", across {BACKDROPS[backdrop][1]}"
    what = str(job.get("what") or "a spacecraft")
    view = VIEWS.get(str(job.get("view") or "side"), VIEWS["side"])
    if job.get("ref"):
        text = GEN_REF.format(
            name=job.get("name") or "the spacecraft",
            style=how,
            what=what,
            view=view,
            scene=scene,
            page=PAGE_ALONE if alone else PAGE_WHOLE,
            outline=OUTLINE if alone else "",
        )
    else:
        text = GEN_WORDS.format(
            what_cap=what,
            name=job.get("name") or "a spacecraft",
            style=how,
            view=view,
            scene=scene,
            page=PAGE_ALONE if alone else PAGE_WHOLE,
            outline=OUTLINE if alone else "",
        )
    if style in MONO:
        text += " Rendered without any colour: black, white and grey only."
    return text


def model_of(model: str | None) -> str:
    return model if model in MODELS else DEFAULT_MODEL


ART: Any = (
    artwork.Collection(
        "orbit_core",
        "paintings",
        make=lambda job: make(job),
        label="Orbit",
        title="Painting spacecraft",
        facet="style",
        facet_label=lambda s: style_of(s)[0],
    )
    if artwork is not None
    else _NoArtwork()
)


def gen_dir(data_dir: Path) -> Path:
    return ART.folder(Path(data_dir))


def cut_out(raw: bytes) -> bytes | None:
    """The painting as a PNG with alpha: the paper is what is paper-coloured
    and reaches the edge of the page; everything else is the spacecraft."""
    try:
        import numpy as np
        from PIL import Image, ImageFilter
    except ImportError:  # pragma: no cover
        return None
    try:
        im = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    a = np.asarray(im).astype(float)
    H, W = a.shape[:2]
    c = 30
    corners = np.concatenate(
        [
            a[:c, :c].reshape(-1, 3),
            a[:c, -c:].reshape(-1, 3),
            a[-c:, :c].reshape(-1, 3),
            a[-c:, -c:].reshape(-1, 3),
        ]
    )
    paper = np.median(corners, axis=0)
    spread = np.sqrt(((corners - paper) ** 2).sum(-1))
    near = spread[spread < 60]
    noise = float(near.std()) if len(near) > 50 else 0.0
    d = np.sqrt(((a - paper) ** 2).sum(-1))
    thr = max(22.0, 10 + 4 * noise)
    paperlike = d < thr
    s = 2
    small = (
        paperlike[: H // s * s, : W // s * s]
        .reshape(H // s, s, W // s, s)
        .all(axis=(1, 3))
    )
    h, w = small.shape
    keep_small = None
    for inset in (0, 0.03, 0.06, 0.1, 0.15):
        iy, ix = int(h * inset), int(w * inset)
        bg = np.zeros_like(small)
        stack = []
        for x in range(ix, w - ix):
            for y in (iy, h - 1 - iy):
                if small[y, x]:
                    stack.append((y, x))
        for y in range(iy, h - iy):
            for x in (ix, w - 1 - ix):
                if small[y, x]:
                    stack.append((y, x))
        for y, x in stack:
            bg[y, x] = True
        while stack:
            y, x = stack.pop()
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < h and 0 <= nx < w and small[ny, nx] and not bg[ny, nx]:
                    bg[ny, nx] = True
                    stack.append((ny, nx))
        rim = max(1, int(round(min(h, w) * 0.012)))
        for lo in (iy, rim):
            bg[:lo, :] = True
            bg[h - lo :, :] = True
        for lo in (ix, rim):
            bg[:, :lo] = True
            bg[:, w - lo :] = True
        keep_small = ~bg
        if keep_small.mean() < 0.6:
            break
    lab = np.zeros(keep_small.shape, dtype=np.int32)
    sizes: dict[int, int] = {}
    n = 0
    for y0 in range(h):
        for x0 in range(w):
            if keep_small[y0, x0] and not lab[y0, x0]:
                n += 1
                stack = [(y0, x0)]
                lab[y0, x0] = n
                count = 0
                while stack:
                    y, x = stack.pop()
                    count += 1
                    for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                        if (
                            0 <= ny < h
                            and 0 <= nx < w
                            and keep_small[ny, nx]
                            and not lab[ny, nx]
                        ):
                            lab[ny, nx] = n
                            stack.append((ny, nx))
                sizes[n] = count
    if sizes:
        biggest = max(sizes.values())
        floor = max(40, int(0.004 * h * w), biggest // 40)
        for k, count in sizes.items():
            if count < floor:
                keep_small[lab == k] = False
    keep = np.zeros((H, W), dtype=bool)
    keep[: h * s, : w * s] = np.kron(keep_small, np.ones((s, s), dtype=bool))
    soft = np.clip((d - thr) / 35, 0, 1)
    hard = (
        Image.fromarray((keep * 255).astype("uint8"))
        .filter(ImageFilter.MinFilter(3))
        .filter(ImageFilter.MaxFilter(3))
    )
    hard_a = np.asarray(hard) > 0
    alpha = np.where(hard_a, np.maximum(soft, 0.98), 0.0)
    alpha8 = np.asarray(
        Image.fromarray((alpha * 255).astype("uint8")).filter(
            ImageFilter.GaussianBlur(0.6)
        )
    )
    share = (alpha8 > 40).mean()
    if share < 0.004 or share > 0.9:
        return None
    rgba = np.dstack([a.astype("uint8"), alpha8])
    out = Image.fromarray(rgba.astype("uint8"), "RGBA")
    bbox = Image.fromarray(alpha8).point(lambda p: 255 if p > 40 else 0).getbbox()
    if bbox:
        out = out.crop(bbox)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def picture(
    art: Any, key: str, px: int, levels: str, whole_: bool
) -> dict[str, Any] | None:
    c, data_dir = art.c, art.data_dir
    if c is None:
        return None
    path = c.path(key, data_dir)
    if path is None:
        return None
    meta = c.meta(key, data_dir)
    credit = str(meta.get("credit") or "")
    if whole_:
        src = art.url(key, px=px, levels=levels)
        return (
            {
                "src": src,
                "kind": "painting",
                "whole": True,
                "credit": credit,
                "aspect": N.aspect_of(src),
            }
            if src
            else None
        )
    variant = f"cut{CUT_VERSION}"
    cut = c.folder(data_dir) / f"{key}__{variant}.png"
    if not cut.exists():
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        png = cut_out(raw)
        if not png:
            c.note_error(
                key,
                data_dir,
                "the painting could not be cut out",
                title=str(meta.get("title") or key),
            )
            return None
        N.write(cut, png)
    src = art.url(key, px=px, levels=levels, cut=True, variant=variant)
    return (
        {
            "src": src,
            "kind": "painting",
            "whole": False,
            "credit": credit,
            "aspect": N.aspect_of(src),
        }
        if src
        else None
    )


def make(job: Any) -> tuple[bytes, dict[str, Any]]:
    """One painting, on a worker thread: the prompt from the payload, the
    reference picture fetched here and handed over inline, the picture from
    fal.ai through the collection's budget."""
    j = job.payload
    ref = str(j.get("ref") or "")
    model = model_of(j.get("model"))
    prompt = prompt_for(j)
    aspect = str(j.get("aspect") or "4:3")
    if ref and not ref.startswith("data:"):
        raw_ref = N.cached_get(job.data_dir, ref, ua=str(j.get("ua") or ""))
        if not raw_ref:
            raise artwork.ArtworkError("the reference picture could not be read")
        ref = _fal.data_uri(raw_ref)
    t2i = not ref
    raw = job.fal.generate(
        "nano_banana_t2i" if t2i else model,
        prompt,
        refs=[] if t2i else [ref],
        aspect=aspect,
        retries=1,
    )
    label = MODELS["nano_banana" if t2i else model]["label"]
    credit = (
        f"painted by {label} from its description"
        if t2i
        else f"painted by {label} from a picture by {j.get('by') or 'NASA'} ({j.get('lic') or 'public domain'})"
    )
    meta = {
        "norad": j.get("norad"),
        "name": j.get("name"),
        "style": j.get("style"),
        "how": j.get("how") or "",
        "backdrop": j.get("backdrop") or "none",
        "model": model,
        "credit": credit,
        "by": j.get("by") or "",
        "link": j.get("link") or "",
        "prompt": prompt,
        "prompt_version": PROMPT_VERSION,
    }
    return raw, meta
