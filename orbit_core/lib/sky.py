"""What passes over: the station and the bright satellites, from CelesTrak's
element sets (no key), propagated with the bundled SGP4, with the sun's place
for who is lit and who is in the dark. Pass prediction is slow in pure Python,
so a predictor thread works it out for a place once every few hours and keeps
the answer on disk; a fetch reads it. Loaded by path."""

from __future__ import annotations

import contextlib
import importlib.util
import json
import math
import re
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
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
SGP4 = _sibling("sgp4")

CELESTRAK = "https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=json"
COMMONS = "https://commons.wikimedia.org/w/api.php"
GROUPS = {"stations": "stations", "bright": "visual"}
ELEMENTS_S = (
    4 * 3600
)  # CelesTrak asks for no more than one fetch of a group every two hours
PREDICT_S = (
    3 * 3600
)  # how long a place's passes are kept before they are worked out again
HOURS_AHEAD = 36
COARSE_S = 30
FINE_S = 2
DARK_DEG = -5.0  # the observer's sun below this: dark enough to see a satellite
DEG = math.pi / 180.0
FLATTENING = 1.0 / 298.26
RE = SGP4.RADIUS


def user_agent(contact: str) -> str:
    c = " ".join(str(contact or "").split())
    return f"tesserae-orbit/0.1 (+https://github.com/dmellok/tesserae-widget-orbit{'; ' + c if c else ''})"


# ----------------------------------------------------------------------
# What they are: the famous ones by catalogue number, the rest by their names
# ----------------------------------------------------------------------
KNOWN: dict[int, dict[str, Any]] = {
    25544: {
        "name": "International Space Station",
        "short": "ISS",
        "cls": "station",
        "mag": -1.8,
        "what": "the International Space Station: a long truss carrying eight great golden solar arrays and a cluster of white cylindrical modules, radiators and docked capsules",
        "ref": "File:STS-134 International Space Station after undocking.jpg",
        "by": "NASA",
        "lic": "Public domain",
    },
    48274: {
        "name": "Tiangong space station",
        "short": "Tiangong",
        "cls": "station",
        "mag": 0.3,
        "what": "China's Tiangong space station: a T of three white cylindrical modules with two long dark-blue solar wings on either side",
        "ref": "",
        "by": "",
        "lic": "",
    },
    20580: {
        "name": "Hubble Space Telescope",
        "short": "Hubble",
        "cls": "telescope",
        "mag": 2.0,
        "what": "the Hubble Space Telescope: a long silver foil-wrapped cylinder with two flat solar panel wings and an open aperture door at one end",
        "ref": "File:HST-SM4.jpeg",
        "by": "NASA",
        "lic": "Public domain",
    },
    27386: {
        "name": "Envisat",
        "short": "Envisat",
        "cls": "satellite",
        "mag": 3.0,
        "what": "Envisat, a large dead Earth-observation satellite: a long bus with a single huge solar panel and a radar antenna, tumbling",
        "ref": "",
        "by": "",
        "lic": "",
    },
    25994: {
        "name": "Terra",
        "short": "Terra",
        "cls": "satellite",
        "mag": 3.2,
        "what": "the Terra Earth-observing satellite: a long bus with one large solar panel wing and instruments along its side",
        "ref": "",
        "by": "",
        "lic": "",
    },
    28376: {
        "name": "Aura",
        "short": "Aura",
        "cls": "satellite",
        "mag": 3.6,
        "what": "the Aura atmospheric satellite: a long bus with one solar panel wing",
        "ref": "",
        "by": "",
        "lic": "",
    },
    39766: {
        "name": "ALOS-2",
        "short": "ALOS-2",
        "cls": "satellite",
        "mag": 3.8,
        "what": "a radar Earth-observation satellite with a long flat antenna panel and two solar wings",
        "ref": "",
        "by": "",
        "lic": "",
    },
    43013: {
        "name": "NOAA 20",
        "short": "NOAA 20",
        "cls": "satellite",
        "mag": 3.8,
        "what": "a polar-orbiting weather satellite: a boxy bus with one solar panel wing and instrument horns",
        "ref": "",
        "by": "",
        "lic": "",
    },
}
CLASSES = ("station", "telescope", "satellite", "rocket", "other")
CLASS_WHAT = {
    "station": "a crewed space station",
    "telescope": "a space telescope",
    "satellite": "a satellite: a boxy bus with two solar panel wings and a dish antenna, in sunlight against black space",
    "rocket": "a spent rocket upper stage: a plain cylindrical body with an engine bell at one end, tumbling slowly, one side catching the sun",
    "other": "a spacecraft in orbit",
}
CLASS_MAG = {
    "station": 0.5,
    "telescope": 2.5,
    "satellite": 4.0,
    "rocket": 3.5,
    "other": 4.5,
}


def classify(norad: int, name: str) -> tuple[str, str, str, float]:
    """(shown name, class, what the painter is told, standard magnitude)."""
    k = KNOWN.get(norad)
    if k:
        return k["name"], k["cls"], k["what"], float(k["mag"])
    n = (name or "").strip()
    up = n.upper()
    if " R/B" in up or up.endswith("R/B") or "ROCKET" in up:
        who = (
            re.sub(r"\s*R/B.*$", "", n, flags=re.I).strip().upper()
        )  # SL-16, CZ-4B, H-2A: designators stay as they are
        return (
            f"{who} rocket body",
            "rocket",
            f"{CLASS_WHAT['rocket']}, the upper stage of a {who} launch",
            CLASS_MAG["rocket"],
        )
    if "COSMOS" in up or "KOSMOS" in up:
        return (
            n.title().replace("Cosmos", "Kosmos"),
            "satellite",
            "a Soviet-era Kosmos satellite: a long cylinder with solar panels, in sunlight against black space",
            4.2,
        )
    if "ISS" in up or "CSS" in up or "TIANGONG" in up:
        return n.title(), "station", CLASS_WHAT["station"], CLASS_MAG["station"]
    nice = re.sub(r"\s+", " ", n).title()
    nice = re.sub(r"\b(\d+)([A-Z])\b", lambda m: m.group(1) + m.group(2).upper(), nice)
    return (
        nice,
        "satellite",
        f"the {nice} satellite, {CLASS_WHAT['satellite']}",
        CLASS_MAG["satellite"],
    )


def brightness_words(mag: float) -> str:
    if mag <= -2.5:
        return "as bright as Venus"
    if mag <= -1.0:
        return "brighter than any star"
    if mag <= 0.5:
        return "as bright as the brightest stars"
    if mag <= 2.0:
        return "as bright as a bright star"
    if mag <= 3.5:
        return "a moving star of middling brightness"
    if mag <= 4.5:
        return "a faint moving star"
    return "very faint; binoculars help"


# ----------------------------------------------------------------------
# Element sets
# ----------------------------------------------------------------------
def elements(
    which: str, data_dir: Path, ua: str
) -> tuple[list[Any], str | None, float]:
    """(element sets, error, fetched-at) for a group: the stations alone or the
    stations and the hundred-odd brightest, kept ELEMENTS_S."""
    groups = ["stations"] if which == "stations" else ["stations", "visual"]
    out: list[Any] = []
    seen: set[int] = set()
    err: str | None = None
    newest = 0.0
    for g in groups:
        cache = data_dir / "elements" / f"{g}.json"
        got = N.read_json(cache, None)
        fresh = (
            isinstance(got, dict)
            and time.time() - float(got.get("at") or 0) < ELEMENTS_S
        )
        if not fresh:
            data, e = N.get_json(CELESTRAK.format(group=g), ua=ua, timeout=5)
            if isinstance(data, list) and data:
                got = {"at": time.time(), "data": data}
                N.write(cache, json.dumps(got).encode())
            elif not isinstance(got, dict):
                err = {
                    "unreachable": "CelesTrak could not be reached",
                    "auth": "CelesTrak refused the request",
                }.get(e or "", f"CelesTrak gave no answer ({e})")
                continue
        newest = max(newest, float(got.get("at") or 0))
        for d in got.get("data") or []:
            try:
                el = SGP4.Elements.from_omm(d)
            except (KeyError, ValueError, TypeError):
                continue
            if (
                el.norad in seen
                or " DEB" in el.name.upper()
                or el.name.upper().endswith(" DEB")
            ):
                continue
            seen.add(el.norad)
            out.append(el)
    return out, err, newest


# ----------------------------------------------------------------------
# Time and the sky
# ----------------------------------------------------------------------
def jd_of(when: datetime) -> float:
    t = when.astimezone(timezone.utc)
    return 2440587.5 + (t.timestamp() / 86400.0)


def gmst(when: datetime) -> float:
    """Greenwich mean sidereal time in radians."""
    jd = jd_of(when)
    t = (jd - 2451545.0) / 36525.0
    secs = (
        67310.54841
        + (876600.0 * 3600.0 + 8640184.812866) * t
        + 0.093104 * t * t
        - 6.2e-6 * t**3
    )
    return (secs % 86400.0) / 240.0 * DEG


def sun_eci(when: datetime) -> tuple[float, float, float]:
    """A unit vector to the sun in the equatorial frame (Meeus's low-precision sun)."""
    n = jd_of(when) - 2451545.0
    lon = (280.460 + 0.9856474 * n) % 360.0
    g = ((357.528 + 0.9856003 * n) % 360.0) * DEG
    lam = (lon + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) * DEG
    eps = (23.439 - 0.0000004 * n) * DEG
    return (math.cos(lam), math.cos(eps) * math.sin(lam), math.sin(eps) * math.sin(lam))


def observer_eci(
    lat: float, lon: float, alt_km: float, theta: float
) -> tuple[float, float, float]:
    """The observer's place in the equatorial frame at local sidereal time ``theta``."""
    phi = lat * DEG
    e2 = FLATTENING * (2 - FLATTENING)
    c = 1.0 / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    s = c * (1 - e2)
    r_xy = (RE * c + alt_km) * math.cos(phi)
    return (
        r_xy * math.cos(theta),
        r_xy * math.sin(theta),
        (RE * s + alt_km) * math.sin(phi),
    )


def look(
    r_sat: tuple[float, float, float],
    lat: float,
    lon: float,
    alt_km: float,
    when: datetime,
    g: float | None = None,
) -> tuple[float, float, float]:
    """(azimuth deg, elevation deg, range km) of a TEME position from the observer."""
    g = gmst(when) if g is None else g
    theta = g + lon * DEG
    ox, oy, oz = observer_eci(lat, lon, alt_km, theta)
    rx, ry, rz = r_sat[0] - ox, r_sat[1] - oy, r_sat[2] - oz
    phi = lat * DEG
    sp, cp, st, ct = math.sin(phi), math.cos(phi), math.sin(theta), math.cos(theta)
    s = sp * ct * rx + sp * st * ry - cp * rz
    e = -st * rx + ct * ry
    z = cp * ct * rx + cp * st * ry + sp * rz
    rng = math.sqrt(s * s + e * e + z * z)
    el = math.degrees(math.asin(max(-1.0, min(1.0, z / rng))))
    az = (math.degrees(math.atan2(e, -s)) + 360.0) % 360.0
    return az, el, rng


def sun_elevation(
    lat: float, lon: float, when: datetime, g: float | None = None
) -> float:
    g = gmst(when) if g is None else g
    sx, sy, sz = sun_eci(when)
    far = 149_600_000.0
    _az, el, _r = look((sx * far, sy * far, sz * far), lat, lon, 0.0, when, g)
    return el


def sunlit(r_sat: tuple[float, float, float], sun: tuple[float, float, float]) -> bool:
    """Not in the Earth's cylindrical shadow."""
    d = r_sat[0] * sun[0] + r_sat[1] * sun[1] + r_sat[2] * sun[2]
    if d > 0:
        return True
    r2 = r_sat[0] ** 2 + r_sat[1] ** 2 + r_sat[2] ** 2
    return math.sqrt(max(0.0, r2 - d * d)) > RE


def magnitude(
    std: float,
    rng_km: float,
    r_sat: tuple[float, float, float],
    sun: tuple[float, float, float],
    obs: tuple[float, float, float],
) -> float:
    """An apparent magnitude from a standard one (1000 km, half lit): the
    inverse square of the range and a phase term."""
    to_obs = (obs[0] - r_sat[0], obs[1] - r_sat[1], obs[2] - r_sat[2])
    n = math.sqrt(sum(v * v for v in to_obs)) or 1.0
    cosphase = (to_obs[0] * sun[0] + to_obs[1] * sun[1] + to_obs[2] * sun[2]) / n
    phase = math.acos(max(-1.0, min(1.0, cosphase)))
    term = max(1e-3, (math.sin(phase) + (math.pi - phase) * math.cos(phase)) / math.pi)
    return (
        std + 5.0 * math.log10(max(rng_km, 1.0) / 1000.0) - 2.5 * math.log10(2.0 * term)
    )


def compass(deg: float) -> str:
    return (
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    )[round(deg / 22.5) % 16]


# ----------------------------------------------------------------------
# Passes
# ----------------------------------------------------------------------
def _sat_at(sat: Any, when: datetime) -> tuple[float, float, float] | None:
    tsince = (when - sat.el.epoch).total_seconds() / 60.0
    try:
        r, _v = sat.at(tsince)
    except ValueError:
        return None
    return r


def passes_for(
    sats: list[Any],
    lat: float,
    lon: float,
    start: datetime,
    hours: float,
    min_el: float,
    stop: threading.Event | None = None,
) -> list[dict[str, Any]]:
    """Every visible pass in the window: the observer in the dark, the object
    in sunlight, above ``min_el`` at its highest. Coarse steps find them,
    fine steps time them."""
    out: list[dict[str, Any]] = []
    end = start + timedelta(hours=hours)
    # the dark windows first: a satellite is looked for only while the observer is in the dark
    dark: list[tuple[datetime, datetime]] = []
    t = start
    cur: datetime | None = None
    while t <= end:
        if sun_elevation(lat, lon, t) < DARK_DEG:
            if cur is None:
                cur = t
        elif cur is not None:
            dark.append((cur, t))
            cur = None
        t += timedelta(minutes=5)
    if cur is not None:
        dark.append((cur, end))
    for sat in sats:
        if stop is not None and stop.is_set():
            break
        for d0, d1 in dark:
            t = d0
            above: list[tuple[datetime, float, float, float, bool]] = []
            while t <= d1:
                r = _sat_at(sat, t)
                if r is None:
                    break
                g = gmst(t)
                az, el, rng = look(r, lat, lon, 0.0, t, g)
                if el > 0:
                    above.append((t, az, el, rng, sunlit(r, sun_eci(t))))
                elif above:
                    out.extend(_refine(sat, above, lat, lon, min_el))
                    above = []
                t += timedelta(seconds=COARSE_S)
            if above:
                out.extend(_refine(sat, above, lat, lon, min_el))
    out.sort(key=lambda p: p["start"])
    return out


def _refine(
    sat: Any,
    coarse: list[tuple[datetime, float, float, float, bool]],
    lat: float,
    lon: float,
    min_el: float,
) -> list[dict[str, Any]]:
    """One coarse pass timed finely: rise, highest, set, the lit part, the magnitude."""
    if max(c[2] for c in coarse) < min_el or not any(c[4] for c in coarse):
        return []
    t0 = coarse[0][0] - timedelta(seconds=COARSE_S)
    t1 = coarse[-1][0] + timedelta(seconds=COARSE_S)
    track: list[dict[str, Any]] = []
    t = t0
    while t <= t1:
        r = _sat_at(sat, t)
        if r is None:
            return []
        g = gmst(t)
        az, el, rng = look(r, lat, lon, 0.0, t, g)
        if el > 0:
            sun = sun_eci(t)
            lit = sunlit(r, sun) and sun_elevation(lat, lon, t, g) < DARK_DEG
            track.append(
                {
                    "t": t,
                    "az": az,
                    "el": el,
                    "rng": rng,
                    "lit": lit,
                    "r": r,
                    "sun": sun,
                    "g": g,
                }
            )
        t += timedelta(seconds=FINE_S)
    if not track:
        return []
    lit = [p for p in track if p["lit"]]
    if not lit or max(p["el"] for p in lit) < min_el:
        return []
    peak = max(lit, key=lambda p: p["el"])
    _name, cls, _what, std = classify(sat.norad, sat.name)
    obs = observer_eci(lat, lon, 0.0, peak["g"] + lon * DEG)
    mag = magnitude(std, peak["rng"], peak["r"], peak["sun"], obs)
    first, last = lit[0], lit[-1]
    return [
        {
            "norad": sat.norad,
            "name": sat.name,
            "start": first["t"].isoformat(),
            "start_az": round(first["az"]),
            "start_el": round(first["el"]),
            "peak": peak["t"].isoformat(),
            "peak_az": round(peak["az"]),
            "peak_el": round(peak["el"]),
            "end": last["t"].isoformat(),
            "end_az": round(last["az"]),
            "end_el": round(last["el"]),
            "duration_s": int((last["t"] - first["t"]).total_seconds()),
            "mag": round(mag, 1),
            "range_km": round(peak["rng"]),
            "track": [
                [
                    round((p["t"] - first["t"]).total_seconds()),
                    round(p["az"]),
                    round(p["el"], 1),
                ]
                for p in lit[:: max(1, len(lit) // 40)]
            ],
            "enters_shadow": last["t"] < track[-1]["t"] - timedelta(seconds=FINE_S * 2),
            "leaves_shadow": first["t"] > track[0]["t"] + timedelta(seconds=FINE_S * 2),
        }
    ]


# ----------------------------------------------------------------------
# The predictor: one thread per place, its answer kept on disk
# ----------------------------------------------------------------------
_PREDICTORS: dict[str, Predictor] = {}
_LOCK = threading.Lock()


def predictor_id(lat: float, lon: float, which: str, min_el: float) -> str:
    return N.slug(f"{lat:.2f}_{lon:.2f}_{which}_{int(min_el)}")


class Predictor:
    def __init__(
        self,
        pid: str,
        lat: float,
        lon: float,
        which: str,
        min_el: float,
        data_dir: Path,
        ua: str,
    ) -> None:
        (
            self.pid,
            self.lat,
            self.lon,
            self.which,
            self.min_el,
            self.data_dir,
            self.ua,
        ) = pid, lat, lon, which, min_el, data_dir, ua
        self.path = data_dir / "passes" / f"{pid}.json"
        self.stop = threading.Event()
        self.error = ""
        self.running = False
        self.thread: threading.Thread | None = None

    def kick(self) -> None:
        got = N.read_json(self.path, None)
        fresh = (
            isinstance(got, dict)
            and time.time() - float(got.get("at") or 0) < PREDICT_S
        )
        if fresh or self.running:
            return
        self.running = True
        self.thread = threading.Thread(
            target=self._run, name=f"orbit-predict-{self.pid}", daemon=True
        )
        self.thread.start()

    def _run(self) -> None:
        try:
            sats_el, err, fetched = elements(self.which, self.data_dir, self.ua)
            if not sats_el:
                self.error = err or "no element sets"
                return
            sats = []
            for el in sats_el:
                with contextlib.suppress(
                    SGP4.DeepSpace, ValueError, ZeroDivisionError, OverflowError
                ):
                    sats.append(SGP4.Satellite(el))
            start = datetime.now(timezone.utc).replace(second=0, microsecond=0)
            t0 = time.time()
            found = passes_for(
                sats, self.lat, self.lon, start, HOURS_AHEAD, self.min_el, self.stop
            )
            N.write(
                self.path,
                json.dumps(
                    {
                        "at": time.time(),
                        "from": start.isoformat(),
                        "hours": HOURS_AHEAD,
                        "objects": len(sats),
                        "took_s": round(time.time() - t0, 1),
                        "elements_at": fetched,
                        "passes": found,
                    }
                ).encode(),
            )
            self.error = ""
        except Exception as exc:  # noqa: BLE001 - the page says so, the next kick tries again
            self.error = f"{type(exc).__name__}: {str(exc)[:120]}"
        finally:
            self.running = False

    def read(self) -> dict[str, Any] | None:
        got = N.read_json(self.path, None)
        return got if isinstance(got, dict) else None


def predictor_for(
    lat: float, lon: float, which: str, min_el: float, data_dir: Path, ua: str
) -> Predictor:
    pid = predictor_id(lat, lon, which, min_el)
    with _LOCK:
        p = _PREDICTORS.get(pid)
        if p is None:
            p = _PREDICTORS[pid] = Predictor(pid, lat, lon, which, min_el, data_dir, ua)
    p.kick()
    return p


def stop_predictors() -> None:
    with _LOCK:
        for p in _PREDICTORS.values():
            p.stop.set()
        _PREDICTORS.clear()


# ----------------------------------------------------------------------
# A reference picture for the painter, by its Commons title
# ----------------------------------------------------------------------
def ref_src(title: str, data_dir: Path, ua: str) -> dict[str, str]:
    """{src, link} for a Commons file by title, kept a month; {} when it cannot be found."""
    if not title:
        return {}
    cache = data_dir / "refs" / f"{N.slug(title)}.json"
    got = N.read_json(cache, None)
    if isinstance(got, dict) and time.time() - float(got.get("at") or 0) < 30 * 86400:
        return got.get("ref") or {}
    q = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": "1200",
        }
    )
    data, _err = N.get_json(f"{COMMONS}?{q}", ua=ua, timeout=4)
    ref: dict[str, str] = {}
    with contextlib.suppress(KeyError, TypeError, AttributeError):
        for page in data["query"]["pages"].values():
            ii = (page.get("imageinfo") or [{}])[0]
            if ii.get("thumburl"):
                ref = {
                    "src": str(ii["thumburl"]),
                    "link": str(ii.get("descriptionurl") or ""),
                }
    if data is not None:
        N.write(cache, json.dumps({"at": time.time(), "ref": ref}).encode())
    return ref
