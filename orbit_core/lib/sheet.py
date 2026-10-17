"""One fetch for the three Orbit widgets: the passes over a place, the words
for each, the paintings. Loaded by path from each widget's server.py."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_HERE = Path(__file__).resolve().parent
logger = logging.getLogger("app.plugins.orbit")


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
SKY = _sibling("sky")
P = _sibling("paint")

WIDGETS = ("pass", "tonight", "scene")
WHICH = ("stations", "bright")
MIN_ELS = ("10", "20", "30", "45")
HOURS = ("12", "24", "36")
PICTURES = ("silhouettes", "paintings")
PANELS = ("colour", "gray16", "gray4", "mono")
PAPERS = ("cream", "white", "aged", "blueprint", "night")
FONTS = ("fell", "archivo", "georgia", "page")
MAX_COUNT = 10
PICTURE_PX = 600
HERO_PX = 1400
COMPUTE_S = 8
LOOK_OPTIONS = frozenset(
    (
        "layout",
        "scale",
        "font",
        "pictures",
        "style",
        "custom_style",
        "build_medium",
        "build_period",
        "build_palette",
        "build_line",
        "build_texture",
        "build_mood",
        "build_extra",
        "model",
        "backdrop",
        "view",
        "text_size",
        "paper",
        "panel",
        "header",
        "footer",
        "title",
        "chart",
    )
)


def _choice(value: Any, choices: tuple[str, ...], default: str = "") -> str:
    v = str(value or "").strip()
    return v if v in choices else (default if default in choices else choices[0])


def _int(value: Any, default: int, low: int, high: int) -> int:
    with contextlib.suppress(TypeError, ValueError):
        return max(low, min(high, int(float(str(value).strip()))))
    return default


def _tz(options: dict[str, Any]) -> ZoneInfo | None:
    loc = options.get("location")
    name = loc.get("timezone") if isinstance(loc, dict) else ""
    with contextlib.suppress(Exception):
        if name:
            return ZoneInfo(str(name))
    return None


def place_of(
    options: dict[str, Any], ctx: dict[str, Any]
) -> tuple[float, float, str] | None:
    loc = options.get("location")
    label = str(loc.get("label") or "") if isinstance(loc, dict) else ""
    for lat, lon in (
        (options.get("latitude"), options.get("longitude")),
        (ctx.get("home_lat"), ctx.get("home_lon")),
    ):
        with contextlib.suppress(TypeError, ValueError):
            la, lo = float(lat), float(lon)
            if la or lo:
                return la, lo, label
    return None


def subject_id(options: dict[str, Any]) -> str:
    return hashlib.sha1(
        json.dumps(
            {k: v for k, v in sorted(options.items()) if k not in LOOK_OPTIONS},
            sort_keys=True,
            default=str,
        ).encode(),
        usedforsecurity=False,
    ).hexdigest()[:16]


# ----------------------------------------------------------------------
# Words
# ----------------------------------------------------------------------
def _hhmm(iso: str, tz: Any) -> str:
    t = datetime.fromisoformat(iso).astimezone(tz)
    return t.strftime("%H:%M")


def _day_word(when: datetime, now: datetime) -> str:
    d = (when.date() - now.date()).days
    if d <= 0:
        return "to-night" if when.hour >= 12 or now.hour >= 12 else "this morning"
    if d == 1:
        return "to-morrow morning" if when.hour < 12 else "to-morrow night"
    return when.strftime("%A")


def _duration(s: int) -> str:
    m, sec = divmod(int(s), 60)
    return f"{m} min" if m and sec < 15 else f"{m} min {sec} s" if m else f"{sec} s"


def describe(p: dict[str, Any], tz: Any, now: datetime) -> dict[str, Any]:
    """The pass with its words: local times, the directions, how bright."""
    start = datetime.fromisoformat(p["start"]).astimezone(tz)
    peak = datetime.fromisoformat(p["peak"]).astimezone(tz)
    end = datetime.fromisoformat(p["end"]).astimezone(tz)
    name, cls, what, _std = SKY.classify(int(p["norad"]), str(p["name"]))
    short = SKY.KNOWN.get(int(p["norad"]), {}).get("short") or name
    rise_dir, peak_dir, set_dir = (
        SKY.compass(p["start_az"]),
        SKY.compass(p["peak_az"]),
        SKY.compass(p["end_az"]),
    )
    bright = SKY.brightness_words(float(p["mag"]))
    appears = (
        "comes out of the Earth's shadow"
        if p.get("leaves_shadow")
        else f"rises in the {rise_dir}"
    )
    goes = (
        "fades into the Earth's shadow"
        if p.get("enters_shadow")
        else f"sets in the {set_dir}"
    )
    about = f"{name} {appears} at {start.strftime('%H:%M')}, climbs to {p['peak_el']}° in the {peak_dir} at {peak.strftime('%H:%M')} and {goes} at {end.strftime('%H:%M')}: {_duration(p['duration_s'])} across the sky, {bright}."
    return {
        **p,
        "shown_name": name,
        "short": short,
        "cls": cls,
        "what": what,
        "day": _day_word(start, now),
        "start_local": start.strftime("%H:%M"),
        "peak_local": peak.strftime("%H:%M"),
        "end_local": end.strftime("%H:%M"),
        "date_local": start.strftime("%a %-d %b")
        if sys.platform != "win32"
        else start.strftime("%a %d %b"),
        "rise_dir": rise_dir,
        "peak_dir": peak_dir,
        "set_dir": set_dir,
        "duration": _duration(p["duration_s"]),
        "bright": bright,
        "about": about,
        "lines": [
            f"{start.strftime('%H:%M')} to {end.strftime('%H:%M')}",
            f"{p['peak_el']}° high in the {peak_dir}",
            f"{rise_dir} to {set_dir}",
            bright,
        ],
        "sil": f"/plugins/orbit_core/static/sil/{cls}.svg",
        "in_progress": start <= now <= end,
        "starts_in_s": int((start - now).total_seconds()),
    }


# ----------------------------------------------------------------------
# The fetch
# ----------------------------------------------------------------------
def fetch(
    options: dict[str, Any], settings: dict[str, Any], ctx: dict[str, Any], widget: str
) -> dict[str, Any]:
    widget = widget if widget in WIDGETS else "pass"
    settings = settings or {}
    data_dir = Path(ctx.get("data_dir") or ".")
    with contextlib.suppress(OSError):
        data_dir.mkdir(parents=True, exist_ok=True)
    preview = bool(ctx.get("preview"))
    ua = SKY.user_agent(str(settings.get("contact") or ""))
    art = P.ART.open(ctx, settings, subject=subject_id(options))

    which = _choice(options.get("which"), WHICH, "bright")
    min_el = float(_choice(options.get("min_el"), MIN_ELS, "20"))
    hours = int(_choice(options.get("hours"), HOURS, "24"))
    count = _int(options.get("count"), 6, 1, MAX_COUNT) if widget == "tonight" else 1
    pictures = _choice(options.get("pictures"), PICTURES, "paintings")
    panel = _choice(options.get("panel"), PANELS)
    paper = _choice(
        options.get("paper"), PAPERS, "night" if widget == "scene" else "cream"
    )
    header = _choice(options.get("header"), ("top", "bottom", "hidden"))
    footer = _choice(options.get("footer"), ("show", "credits", "hide"))
    text_size = _int(options.get("text_size"), 100, 60, 150)
    chart = _choice(options.get("chart"), ("dome", "none"), "dome")
    style = str(options.get("style") or "poster")
    how = ""
    if style == "builder":
        how = P.build_how(options)
        style = P.register_custom(how)
    elif style == "custom":
        how = (
            " ".join(str(options.get("custom_style") or "").split())[:600]
            or P.CUSTOM_EXAMPLE
        )
        style = P.register_custom(how)
    elif style not in P.STYLES:
        style = "poster"
    model = P.model_of(str(options.get("model") or P.DEFAULT_MODEL))
    backdrop = _choice(options.get("backdrop"), tuple(P.BACKDROPS))
    if widget == "tonight":
        backdrop = "none"
    if widget == "scene" and backdrop == "none":
        backdrop = "space"
    view = _choice(options.get("view"), tuple(P.VIEWS))

    tz = _tz(options) or datetime.now().astimezone().tzinfo
    now = datetime.now(timezone.utc).astimezone(tz)
    place = place_of(options, ctx)
    title = " ".join(str(options.get("title") or "").split()) or (
        f"Over {place[2]}" if place and place[2] else "Overhead to-night"
    )
    base: dict[str, Any] = {
        "widget": widget,
        "state": "ok",
        "title": title,
        "area": "the station and the bright satellites"
        if which == "bright"
        else "the space stations",
        "period": f"the next {hours} hours",
        "date": now.strftime("%a %-d %b")
        if sys.platform != "win32"
        else now.strftime("%a %d %b"),
        "time": now.strftime("%H:%M"),
        "passes": [],
        "found": 0,
        "shown": 0,
        "notices": [],
        "status": [],
        "credits": [],
        "live_refresh_s": 0,
        "header": header,
        "footer": footer,
        "paper": paper,
        "panel": panel,
        "text_size": text_size,
        "chart": chart,
        "pictures": pictures,
        "style": style,
        "style_label": P.style_of(style)[0],
        "backdrop": backdrop,
        "font_css": N.font_css(("im_fell", "im_fell_sc", "archivo_narrow")),
        "font": _choice(options.get("font"), FONTS),
        "layout": _choice(options.get("layout"), ("rows", "cluster"), "rows"),
        "scale": _int(options.get("scale"), 100, 40, 100),
        "min_el": int(min_el),
    }
    if not place:
        return {
            **base,
            "state": "error",
            "error": "Set a place: the cell's location, or the app's location in Settings.",
        }

    pred = SKY.predictor_for(place[0], place[1], which, min_el, data_dir, ua)
    got = pred.read()
    if got is None:
        if pred.error and not pred.running:
            return {
                **base,
                "state": "error",
                "error": f"The passes could not be worked out: {pred.error}.",
            }
        return {
            **base,
            "state": "computing",
            "live_refresh_s": COMPUTE_S,
            "hint": "Working out the passes over the next day and a half from CelesTrak's element sets; a moment.",
        }
    end = now + timedelta(hours=hours)
    rows = [
        describe(p, tz, now)
        for p in got.get("passes") or []
        if (
            which != "stations"
            or SKY.classify(int(p["norad"]), str(p["name"]))[1] == "station"
        )
        and datetime.fromisoformat(p["end"]) > now.astimezone(timezone.utc)
        and datetime.fromisoformat(p["start"]) <= end.astimezone(timezone.utc)
    ]
    base["found"] = len(rows)
    base["computed"] = datetime.fromtimestamp(float(got.get("at") or 0), tz).strftime(
        "%H:%M"
    )
    base["objects"] = int(got.get("objects") or 0)
    if widget in ("pass", "scene"):
        # the best of the coming night: among the passes within twelve hours of the first, the
        # station over anything, else the highest; a pass under way counts
        rows.sort(key=lambda r: r["start"])
        if rows:
            horizon = datetime.fromisoformat(rows[0]["start"]) + timedelta(
                hours=4
            )  # the evening, not the small hours
            night = [r for r in rows if datetime.fromisoformat(r["start"]) <= horizon]
            night.sort(
                key=lambda r: (
                    0 if r["cls"] == "station" else 1,
                    -r["peak_el"],
                    r["start"],
                )
            )
            rows = night[:1]
    else:
        rows.sort(key=lambda r: r["start"])
        rows = rows[:count]
    if not rows:
        return {
            **base,
            "state": "empty",
            "hint": f"Nothing bright passes over in the dark in the next {hours} hours, above {int(min_el)}°. A lower elevation or a longer window would show more.",
        }

    credits: list[str] = []
    from_words = 0
    px = HERO_PX if widget != "tonight" else PICTURE_PX
    whole_ = backdrop != "none" or style in P.OWN_PAPER
    for r in rows:
        pic: dict[str, Any] | None = None
        if pictures == "paintings":
            known = SKY.KNOWN.get(int(r["norad"]), {})
            ref = (
                SKY.ref_src(str(known.get("ref") or ""), data_dir, ua)
                if known.get("ref")
                else {}
            )
            key = P.key_for(int(r["norad"]), style, backdrop, view, model)
            payload = {
                "norad": r["norad"],
                "name": r["shown_name"],
                "what": r["what"],
                "style": style,
                "how": how,
                "backdrop": backdrop,
                "view": view,
                "model": model,
                "ref": ref.get("src") or "",
                "by": known.get("by") or "",
                "lic": known.get("lic") or "",
                "link": ref.get("link") or "",
                "ua": ua,
                "aspect": "4:3",
            }
            if not ref.get("src"):
                from_words += 1
            got_pic = art.request(
                key, payload, title=f"{r['shown_name']}, {P.style_of(style)[0]}"
            )
            if got_pic.ready:
                pic = P.picture(art, key, px, panel, whole_)
                if pic and pic.get("credit"):
                    credits.append(pic["credit"])
            elif got_pic.state == "failed":
                r["why"] = got_pic.why
        r["pic"] = pic
    base["passes"] = rows
    base["shown"] = len(rows)
    notices, status = [], []
    if pictures == "paintings":
        status.extend(art.status())
        notices.extend(art.notes())
        art.finish(ctx, facet=style)
    if pred.error:
        notices.append(
            f"the passes are from {base['computed']}; CelesTrak could not be asked again ({pred.error})"
        )
    live = art.live()
    # the page comes back as the next pass nears, so a panel shows it under way
    soon = min((r["starts_in_s"] for r in rows if r["starts_in_s"] > 0), default=0)
    if widget == "pass" and 0 < soon <= 15 * 60:
        live["live_refresh_s"] = max(live["live_refresh_s"], 60)
    base.update(
        notices=notices,
        status=status,
        credits=list(dict.fromkeys(credits))[:4],
        attribution="element sets from CelesTrak",
        **live,
    )
    logger.info(
        "orbit: %s %s, %d passes, %d shown, painted %d, started %d, from words %d",
        "preview" if preview else "panel",
        widget,
        len(got.get("passes") or []),
        len(rows),
        art.states.get("ready", 0),
        art.started,
        from_words,
    )
    return base
