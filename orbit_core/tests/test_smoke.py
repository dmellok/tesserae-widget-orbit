"""Offline tests for the Orbit bundle: the propagator, the sky, the passes,
the paintings and the three pages, with every call on the network answered
here."""

from __future__ import annotations

import importlib.util
import io
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_TESSERAE = Path(os.environ.get("TESSERAE_REPO") or Path(__file__).resolve().parents[3] / "tesserae")
if str(_TESSERAE) not in sys.path:
    sys.path.insert(0, str(_TESSERAE))
from app import fal as fal_mod  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pass_w = _load(ROOT / "orbit_pass" / "server.py", "orbit_pass_server")
tonight = _load(ROOT / "orbit_tonight" / "server.py", "orbit_tonight_server")
scene = _load(ROOT / "orbit_scene" / "server.py", "orbit_scene_server")
core = _load(ROOT / "orbit_core" / "server.py", "orbit_core_server")
S = pass_w._lib("sheet")
SKY = S.SKY
SGP4 = SKY.SGP4
P = S.P
N = S.N

MELBOURNE = {"latitude": -37.81, "longitude": 144.96, "location": {"label": "Melbourne", "timezone": "Australia/Melbourne"}}
SETTINGS = {"fal_api_key": "k", "contact": "tester@example.com", "gen_daily_usd": "1"}
# An ISS element set (epoch 2026-10-17) and a rocket body, as CelesTrak serves them
ISS = {"OBJECT_NAME": "ISS (ZARYA)", "OBJECT_ID": "1998-067A", "EPOCH": "2026-10-17T12:00:00.000000", "MEAN_MOTION": 15.49, "ECCENTRICITY": 0.0006, "INCLINATION": 51.64, "RA_OF_ASC_NODE": 120.0, "ARG_OF_PERICENTER": 40.0, "MEAN_ANOMALY": 320.0, "EPHEMERIS_TYPE": 0, "CLASSIFICATION_TYPE": "U", "NORAD_CAT_ID": 25544, "ELEMENT_SET_NO": 999, "REV_AT_EPOCH": 1, "BSTAR": 0.0002, "MEAN_MOTION_DOT": 0.0001, "MEAN_MOTION_DDOT": 0}
RB = {**ISS, "OBJECT_NAME": "SL-16 R/B", "NORAD_CAT_ID": 22220, "MEAN_MOTION": 14.2, "INCLINATION": 71.0, "RA_OF_ASC_NODE": 200.0, "BSTAR": 0.0001}
DEEP = {**ISS, "OBJECT_NAME": "GEO THING", "NORAD_CAT_ID": 99999, "MEAN_MOTION": 1.0027, "INCLINATION": 0.1}
DEB = {**ISS, "OBJECT_NAME": "FREGAT DEB", "NORAD_CAT_ID": 55555}


def _jpeg(w=600, h=400, paper=(255, 255, 255)) -> bytes:
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (w, h), paper)
    d = ImageDraw.Draw(im)
    d.rectangle((120, 150, 480, 250), fill=(90, 90, 100))
    d.rectangle((40, 180, 120, 220), fill=(200, 160, 40))
    d.rectangle((480, 180, 560, 220), fill=(200, 160, 40))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return out.getvalue()


@pytest.fixture
def offline(monkeypatch):
    prompts: list[dict] = []

    def fake_http(url, token="", accept="application/json", *, auth_scheme="Bearer", body=None, timeout=10, detail=False, ua=""):
        assert "tesserae-orbit" in ua or "celestrak" not in url
        if "celestrak" in url and "GROUP=stations" in url:
            return json.dumps([ISS]).encode(), None
        if "celestrak" in url and "GROUP=visual" in url:
            return json.dumps([ISS, RB, DEEP, DEB]).encode(), None
        if "commons.wikimedia.org" in url:
            return json.dumps({"query": {"pages": {"1": {"imageinfo": [{"thumburl": "https://upload.wikimedia.org/iss.jpg", "descriptionurl": "https://commons.wikimedia.org/wiki/File:ISS.jpg"}]}}}}).encode(), None
        if "upload.wikimedia.org" in url:
            return _jpeg(), None
        return None, "unreachable"

    monkeypatch.setattr(N, "http", fake_http)
    monkeypatch.setattr(SKY, "commons", None)  # the widget's own lookup; the host's has its own test below

    def fake_fal(url, body, key, timeout):
        prompts.append({**body, "_url": url})
        assert key == "k"
        return {"images": [{"url": "https://fal.example/out.jpg"}]}

    monkeypatch.setattr(fal_mod, "_http_json", fake_fal)
    monkeypatch.setattr(fal_mod, "_download", lambda url, timeout=60.0: _jpeg(paper=(252, 250, 246)))
    yield prompts
    P.ART.stop_all(Path("."))
    SKY.stop_predictors()


def _busy() -> bool:
    pr = P.ART.progress(Path("."), {})
    return bool(pr["running"] or pr["queued"])


def _settle(timeout=10.0):
    end = time.time() + timeout
    while _busy() and time.time() < end:
        time.sleep(0.02)
    assert not _busy()


def _ctx(tmp_path, **kw):
    ctx = {"data_dir": str(tmp_path), "cell_w": 800, "cell_h": 480, **kw}
    ctx.setdefault("settled", not ctx.get("preview"))
    return ctx


def _ready(widget, opts, tmp_path, settings=SETTINGS, timeout=30.0):
    """The fetch once the predictor has done its work."""
    end = time.time() + timeout
    r = widget.fetch(opts, settings, ctx=_ctx(tmp_path))
    while r["state"] == "computing" and time.time() < end:
        time.sleep(0.2)
        r = widget.fetch(opts, settings, ctx=_ctx(tmp_path))
    return r


# ----------------------------------------------------------------------
def test_manifests_and_client_files():
    for wid in ("orbit_core", "orbit_pass", "orbit_tonight", "orbit_scene"):
        m = json.loads((ROOT / wid / "plugin.json").read_text(encoding="utf-8"))
        assert m["version"] == "0.2.3" and m["tesserae_min"] == "0.463.0"
        if m["kind"] == "widget":
            assert m["render"]["warm_ahead_s"] == 150 and (ROOT / wid / "client.js").exists()
            names = [o["name"] for o in m["cell_options"]]
            assert len(names) == len(set(names))
    for cls in SKY.CLASSES:
        assert (ROOT / "orbit_core" / "static" / "sil" / f"{cls}.svg").exists(), cls



RELEASED = "v0.2.1"  # the saved cells to keep working: no option, choice value or default may change
UP_FRONT = {
    "orbit_pass": ["location", "pictures", "paper"],
    "orbit_tonight": ["location", "layout", "count", "pictures", "paper"],
    "orbit_scene": ["location", "pictures", "paper"],
}


def test_options_panel_is_short_and_keeps_saved_cells():
    for wid, up_front in UP_FRONT.items():
        opts = json.loads((ROOT / wid / "plugin.json").read_text(encoding="utf-8"))["cell_options"]
        by = {o["name"]: o for o in opts}
        assert [o["name"] for o in opts if not o.get("show_if") and not o.get("advanced")] == up_front, wid
        for o in opts:
            for key, want in (o.get("show_if") or {}).items():
                assert key in by, (wid, o["name"], key)
                values = {c["value"] for c in by[key].get("choices", [])}
                for w in want if isinstance(want, list) else [want.get("not") if isinstance(want, dict) else want]:
                    assert not values or w in values or w == "", (wid, o["name"], key, w)
            assert "Type" != o["label"] and "\u2014" not in o["label"] + o.get("help", ""), (wid, o["name"])
        for name in ("view", "model", "which", "min_el", "hours", "chart", "title", "header", "footer", "panel", "text_size", "font"):
            assert by[name].get("advanced") is True, (wid, name)
        for name in ("style", "custom_style", "build_medium", "view", "model"):
            assert by[name]["show_if"]["pictures"] == "paintings", (wid, name)
        try:
            old = json.loads(subprocess.run(["git", "-C", str(ROOT), "show", f"{RELEASED}:{wid}/plugin.json"], capture_output=True, check=True).stdout)
        except (OSError, subprocess.CalledProcessError):
            continue  # a copy without the history
        old = {o["name"]: o for o in old["cell_options"]}
        assert set(old) == set(by), wid
        for name, o in old.items():
            n = by[name]
            assert (n["type"], n.get("default"), [c["value"] for c in n.get("choices", [])]) == (o["type"], o.get("default"), [c["value"] for c in o.get("choices", [])]), (wid, name)
    tonight_opts = {o["name"]: o for o in json.loads((ROOT / "orbit_tonight" / "plugin.json").read_text(encoding="utf-8"))["cell_options"]}
    for name in ("scale", "packing"):
        assert tonight_opts[name]["show_if"] == {"layout": "cluster"} and tonight_opts[name]["advanced"] is True

def test_sgp4_stays_in_orbit_and_refuses_deep_space():
    el = SGP4.Elements.from_omm(ISS)
    sat = SGP4.Satellite(el)
    r0, v0 = sat.at(0.0)
    assert 6700 < math.dist(r0, (0, 0, 0)) < 6900, "about 400 km up"
    assert 7.5 < math.dist(v0, (0, 0, 0)) < 7.8, "orbital speed in km/s"
    r1, _v = sat.at(el.period_min / 2)
    assert math.dist(r1, (0, 0, 0)) > 6700 and math.dist(r0, r1) > 13000, "half an orbit later, the far side"
    r2, _v = sat.at(el.period_min)
    assert math.dist(r0, r2) < 120, "one period later, nearly back (the node has moved a little)"
    assert 92 < el.period_min < 94
    with pytest.raises(SGP4.DeepSpace):
        SGP4.Satellite(SGP4.Elements.from_omm(DEEP))


def test_the_sky_geometry():
    lat, lon = -37.81, 144.96
    when = datetime(2026, 10, 18, 2, 20, tzinfo=timezone.utc)  # about 13:20 in Melbourne
    el = SKY.sun_elevation(lat, lon, when)
    assert 55 < el < 68, f"the October noon sun over Melbourne, got {el:.1f}"
    assert SKY.sun_elevation(lat, lon, when + timedelta(hours=12)) < -30
    g = SKY.gmst(when)
    obs = SKY.observer_eci(lat, lon, 0.0, g + lon * SKY.DEG)
    up = tuple(v * 1.06 for v in obs)
    az, elev, rng = SKY.look(up, lat, lon, 0.0, when, g)
    assert elev > 89.5 and 370 < rng < 400
    north = SKY.observer_eci(lat + 3.0, lon, 400.0, g + lon * SKY.DEG)
    az, elev, _r = SKY.look(north, lat, lon, 0.0, when, g)
    assert 350 < az or az < 10, f"a point to the north bears north, got {az:.0f}"
    sun = SKY.sun_eci(when)
    assert SKY.sunlit(tuple(v * 7000 for v in sun), sun) and not SKY.sunlit(tuple(-v * 7000 for v in sun), sun)
    assert SKY.sunlit(tuple(-v * 7000 for v in SKY.sun_eci(when)), sun) is False
    assert SKY.compass(0) == "N" and SKY.compass(200) == "SSW" and SKY.compass(359) == "N"
    assert SKY.brightness_words(-2.0) == "brighter than any star" and SKY.brightness_words(4.0) == "a faint moving star"


def test_names_and_classes():
    assert SKY.classify(25544, "ISS (ZARYA)")[:2] == ("International Space Station", "station")
    assert SKY.classify(22220, "SL-16 R/B")[:2] == ("SL-16 rocket body", "rocket") and "Zenit" in SKY.classify(22220, "SL-16 R/B")[2]
    assert SKY.ref_of(25544, "ISS (ZARYA)").startswith("File:STS-134") and SKY.ref_of(1, "COSMOS 1844") == SKY.TSELINA_REF and SKY.ref_of(2, "ARIANE 5 R/B").startswith("File:Ariane 5") and SKY.ref_of(3, "SL-16 R/B") == ""
    assert SKY.classify(12345, "COSMOS 1408")[:2] == ("Kosmos 1408", "satellite")
    name, cls, what, mag = SKY.classify(55, "SPACEMOBILE-004")
    assert name == "Spacemobile-004" and cls == "satellite" and "BlueBird" in what and mag == 3.0
    assert SKY.classify(1, "MIDORI II (ADEOS-II)")[0] == "Midori II (ADEOS-II)" and SKY.classify(2, "NOAA 19")[0] == "NOAA 19" and SKY.classify(3, "ENVISAT")[0] == "Envisat"


def test_elements_skip_debris_and_duplicates(tmp_path, offline):
    els, err, at = SKY.elements("bright", tmp_path, SKY.user_agent(""))
    assert err is None and at > 0
    assert sorted(e.norad for e in els) == [22220, 25544, 99999], "the station once, the rocket body, the deep one (refused later), no debris"
    assert SKY.docked("PROGRESS-MS 34") and SKY.docked("CSS (WENTIAN)") and not SKY.docked("CSS (TIANHE)") and not SKY.docked("ISS (ZARYA)")
    assert (tmp_path / "elements" / "visual.json").exists() and (tmp_path / "elements" / "stations.json").exists()


def test_passes_are_found_and_timed(tmp_path, offline):
    els, _err, _at = SKY.elements("bright", tmp_path, SKY.user_agent(""))
    sats = []
    for el in els:
        try:
            sats.append(SGP4.Satellite(el))
        except SGP4.DeepSpace:
            pass
    start = datetime(2026, 10, 17, 22, 0, tzinfo=timezone.utc)
    found = SKY.passes_for(sats, -37.81, 144.96, start, 48, 10.0)
    assert found, "two days of two low objects over Melbourne: something passes in the dark"
    for p in found:
        assert p["peak_el"] >= 10 and p["duration_s"] > 30 and p["start"] <= p["peak"] <= p["end"]
        assert 0 <= p["start_az"] < 360 and -5 < p["mag"] < 9 and p["range_km"] > 400
        assert len(p["track"]) >= 2 and all(len(x) == 3 for x in p["track"])
        t = datetime.fromisoformat(p["peak"])
        assert SKY.sun_elevation(-37.81, 144.96, t) < SKY.DARK_DEG, "the observer was in the dark at the peak"
    assert found == sorted(found, key=lambda p: p["start"])


def test_pages_compute_then_show(tmp_path, offline):
    r = pass_w.fetch({**MELBOURNE, "pictures": "silhouettes"}, SETTINGS, ctx=_ctx(tmp_path))
    assert r["state"] == "computing" and r["live_refresh_s"] == S.COMPUTE_S
    r = _ready(pass_w, {**MELBOURNE, "pictures": "silhouettes", "hours": "36", "min_el": "10"}, tmp_path)
    assert r["state"] in ("ok", "empty")
    if r["state"] == "ok":
        p = r["passes"][0]
        assert p["shown_name"] in ("International Space Station", "SL-16 rocket body") and p["pic"] is None and p["sil"].endswith((".svg"))
        assert p["about"].startswith(p["shown_name"]) and ":" in p["start_local"] and p["duration"]
        assert r["attribution"] == "element sets from CelesTrak" and r["computed"]
    r = _ready(tonight, {**MELBOURNE, "pictures": "silhouettes", "hours": "36", "min_el": "10", "count": "3"}, tmp_path)
    assert r["state"] in ("ok", "empty") and len(r["passes"]) <= 3
    if len(r["passes"]) > 1:
        assert r["passes"] == sorted(r["passes"], key=lambda p: p["start"])
    r = _ready(scene, {**MELBOURNE, "pictures": "silhouettes", "hours": "36", "min_el": "10"}, tmp_path)
    assert r["state"] in ("ok", "empty") and r["backdrop"] == "space" and r["paper"] == "night"
    r = pass_w.fetch({}, SETTINGS, ctx=_ctx(tmp_path))
    assert r["state"] == "error" and "Set a place" in r["error"]
    # the stations alone, from the stations list
    r = _ready(pass_w, {**MELBOURNE, "pictures": "silhouettes", "which": "stations", "hours": "36", "min_el": "10"}, tmp_path)
    assert r["state"] in ("ok", "empty") and r["area"] == "the space stations"


def test_paintings_from_a_reference_and_from_words(tmp_path, offline):
    prompts = offline
    opts = {**MELBOURNE, "pictures": "paintings", "style": "linocut", "hours": "36", "min_el": "10", "count": "4"}
    r = _ready(tonight, opts, tmp_path)
    if r["state"] != "ok":
        pytest.skip("no pass in the fixture window")
    _settle()
    names = {p["shown_name"] for p in r["passes"]}
    assert len(prompts) == len(names), "one painting per object, not per pass"
    for pr in prompts:
        assert "linocut" in pr["prompt"] and "pure white paper" in pr["prompt"]
        if "International Space Station" in pr["prompt"]:
            assert pr.get("image_urls") and pr["image_urls"][0].startswith("data:image/"), "the station from NASA's picture, handed over inline"
            assert "golden solar arrays" in pr["prompt"]
        else:
            assert not pr.get("image_urls") and "Zenit" in pr["prompt"]
    r = _ready(tonight, opts, tmp_path)
    assert all(p["pic"] and p["pic"]["kind"] == "painting" and not p["pic"]["whole"] for p in r["passes"])
    assert all(p["pic"]["impression"] == (p["norad"] != 25544) for p in r["passes"]), "the station from a picture, the stage an impression"
    assert len(prompts) == len(names), "painted once"
    keys = [p.stem for p in P.gen_dir(tmp_path).glob("*.jpg")]
    assert any(k.startswith("sat_25544--linocut--p2") or k.startswith("sat_22220--linocut--p2") for k in keys)
    assert any("Wikimedia Commons" in p["pic"]["credit"] or "description" in p["pic"]["credit"] for p in r["passes"])


def test_prompt_pieces_and_core():
    assert core.settings_of(None) == {}
    assert P.key_for(25544, "poster") == "sat_25544--poster--p2"
    assert P.key_for(25544, "poster", "limb", "below", "flux_kontext") == "sat_25544--poster--p2--bd_limb--v_below--m_flux_kontext"
    text = P.prompt_for({"style": "engraving", "name": "Hubble Space Telescope", "what": "the Hubble Space Telescope", "ref": "x", "backdrop": "sunrise"})
    assert "black, white and grey only" in text and "orbital sunrise" in text and "filling the frame" in text
    text = P.prompt_for({"style": "poster", "name": "SL-16 rocket body", "what": "a spent rocket upper stage", "view": "below"})
    assert "pure white paper" in text and "foreshortened" in text and "contour line" in text
    how = P.build_how({"build_medium": "ink", "build_period": "atlas", "build_extra": "a comet in the corner"})
    assert how.startswith("a pen-and-ink drawing of the {kind}, in the manner of a seventeenth-century celestial atlas") and how.endswith("a comet in the corner")


def test_the_hosts_commons_lookup_is_used_when_there(tmp_path, monkeypatch):
    from app import commons as host_commons

    monkeypatch.setattr(SKY, "commons", host_commons)
    monkeypatch.setattr(host_commons, "file", lambda title, px=1400: {"title": title, "src": f"https://upload.wikimedia.org/{px}.jpg", "link": "https://commons.wikimedia.org/wiki/x", "by": "NASA", "lic": "Public domain", "w": 1200, "h": 800})
    r = SKY.ref_src("File:HST-SM4.jpeg", tmp_path, "ua")
    assert r == {"src": "https://upload.wikimedia.org/1200.jpg", "link": "https://commons.wikimedia.org/wiki/x", "by": "NASA", "lic": "Public domain"}
    assert not (tmp_path / "refs").exists(), "nothing kept by the widget; the host keeps it"


def test_fugleramme_packings_keep_objects_apart_and_on_the_page():
    script = (
        f"import('file://{ROOT}/orbit_core/static/pack.js').then((m) => {{"
        " const blob = (w, h, s) => { const d = new Uint8Array(w * h);"
        "   for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {"
        "     const dx = (x - w * 0.45) / (w * 0.35), dy = (y - h * 0.45) / (h * 0.3);"
        "     const head = ((x - w * 0.75) / (w * 0.13)) ** 2 + ((y - h * 0.25) / (h * 0.13)) ** 2 < 1;"
        "     if (dx * dx + dy * dy < 1 || head || (Math.abs(x - w * 0.45) < 2 && y > h * 0.7)) d[y * w + x] = 1; }"
        "   return { w, h, data: d }; };"
        " for (const packer of ['spiral', 'voids']) for (const [W, H] of [[1400, 840], [840, 1400]]) {"
        "   const its = Array.from({ length: 14 }, (_, i) => ({ mask: blob(160 + (i * 37) % 140, 130 + (i * 53) % 110, i),"
        "     factor: 0.6 + (i % 5) / 5, lines: ['Object ' + i], flippable: false, sci: 'Sat ' + i }));"
        "   const out = m.packSheet(its, W, H, 13 / H, { packer });"
        "   const occ = new Uint8Array(W * H);"
        "   out.forEach((p, i) => { if (!p) throw new Error(packer + ' left one off');"
        "     const k = its[i].mask;"
        "     for (let y = 0; y < k.h; y++) for (let x = 0; x < k.w; x++) { if (!k.data[y * k.w + x]) continue;"
        "       if (p.flip) throw new Error(packer + ' mirrored one');"
        "       const sx = x;"
        "       const X = Math.floor(p.x + (sx + 0.5) * p.w / k.w), Y = Math.floor(p.y + (y + 0.5) * p.h / k.h);"
        "       if (X < 0 || Y < 0 || X >= W || Y >= H) throw new Error(packer + ' off the page');"
        "       if (occ[Y * W + X] && occ[Y * W + X] !== i + 1) throw new Error(packer + ' overlap');"
        "       occ[Y * W + X] = i + 1; } });"
        "   const same = m.packSheet(its, W, H, 13 / H, { packer });"
        "   if (JSON.stringify(same) !== JSON.stringify(out)) throw new Error(packer + ' not repeatable'); }"
        " console.log('ok'); })"
    )
    out = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr


def test_packing_option_reaches_the_page(tmp_path):
    assert tonight.fetch({}, SETTINGS, ctx=_ctx(tmp_path))["packing"] == "balanced"
    assert tonight.fetch({"packing": "voids"}, SETTINGS, ctx=_ctx(tmp_path))["packing"] == "voids"
    assert tonight.fetch({"packing": "nonsense"}, SETTINGS, ctx=_ctx(tmp_path))["packing"] == "balanced"
    # a look, not a subject: switching it repacks the same passes and paintings
    assert S.subject_id({**MELBOURNE, "packing": "spiral"}) == S.subject_id(MELBOURNE)


# ----------------------------------------------------------------------
# The pages in a real browser: the shared page script served to Chromium from this folder.

HARNESS = """<!doctype html><html><body style="margin:0"><div id="host"></div><script type="module">
window.run = async (job) => {
  const host = document.getElementById('host');
  host.style.cssText = `width:${job.w}px;height:${job.h}px`;
  const shadow = host.shadowRoot || host.attachShadow({ mode: 'open' });
  if (job.kind === 'rows') {
    const m = await import('/orbit.js');
    await m.render(shadow, { data: job.data, cell: { w: job.w, h: job.h, size: 'lg' } }, 'tonight');
    const box = (el) => { const r = el.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom]; };
    return [...shadow.querySelectorAll('.tn-row')].map((row) => {
      const cell = row.querySelector('.tn-dome'), svg = row.querySelector('.tn-dome svg'), b = row.querySelector('.tn-t b'), t = row.querySelector('.tn-t');
      return { row: box(row), cell: cell && box(cell), svg: svg && box(svg), text: box(t), nameCut: b.scrollHeight > b.clientHeight + 1 };
    });
  }
  const m = await import('/sheet.js');
  const made = await m.buildSheet(job.sheet);
  const img = new Image(); img.src = made.src; await img.decode();
  const c = document.createElement('canvas'); c.width = made.w; c.height = made.h;
  const ctx = c.getContext('2d'); ctx.drawImage(img, 0, 0);
  const at = (fx, fy) => [...ctx.getImageData(Math.round(fx * made.w), Math.round(fy * made.h), 1, 1).data].slice(0, 3);
  return made.items.map((it) => { const [x, y, w, h] = it.box; return { corner: at(x + w * 0.04, y + h * 0.04), middle: at(x + w / 2, y + h / 2) }; });
};
window.ready = true;
</script></body></html>"""


@pytest.fixture(scope="module")
def browser_page():
    pw = pytest.importorskip("playwright.sync_api")
    from app.renderer import _chromium_launch_kwargs

    static = ROOT / "orbit_core" / "static"

    def serve(route):
        path = route.request.url.split("orbit.test/", 1)[1].split("?")[0]
        if path == "h.html":
            return route.fulfill(body=HARNESS, content_type="text/html")
        f = static / path
        if not f.is_file():
            return route.fulfill(status=404, body="")
        return route.fulfill(
            body=f.read_bytes(),
            content_type="text/javascript" if f.suffix == ".js" else "image/svg+xml",
        )

    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch(**_chromium_launch_kwargs())
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"no Chromium here: {exc}")
        page = browser.new_page()
        page.route("http://orbit.test/**", serve)
        page.goto("http://orbit.test/h.html")
        page.wait_for_function("window.ready === true")
        yield page
        browser.close()


def _fake_passes(n):
    names = [
        "THOR AGENA D rocket body",
        "International Space Station",
        "Knacksat-2",
        "Okean-3",
        "DELTA 2 rocket body",
        "SL-3 rocket body",
        "HMU-SAT2",
        "ERS-1",
        "ISIS 1",
    ]
    track = [[0, 220, 0], [1, 180, 30], [2, 95, 0]]
    return [
        {
            "norad": 100 + i,
            "shown_name": names[i % len(names)],
            "cls": "rocket",
            "day": "to-night",
            "start_local": "20:11",
            "end_local": "20:24",
            "peak_el": 32,
            "peak_dir": "SSE",
            "peak_az": 180,
            "rise_dir": "SW",
            "set_dir": "E",
            "bright": "a moving star of middling brightness",
            "track": track,
            "pic": None,
            "in_progress": False,
        }
        for i in range(n)
    ]


@pytest.mark.parametrize("w,h", [(1200, 800), (640, 400), (380, 240), (480, 800)])
def test_rows_keep_each_sky_chart_inside_its_column(browser_page, w, h):
    for n in (1, 2, 3, 4, 6, 9):
        for chart in ("dome", "none"):
            data = {
                "widget": "orbit_tonight",
                "state": "ok",
                "title": "Over Melbourne",
                "time": "09:00",
                "date": "Fri 23 Oct",
                "passes": _fake_passes(n),
                "chart": chart,
                "credits": ["x"],
            }
            rows = browser_page.evaluate(
                "(j) => window.run(j)", {"kind": "rows", "w": w, "h": h, "data": data}
            )
            assert len(rows) == n
            for r in rows:
                rx0, ry0, rx1, ry1 = r["row"]
                assert rx1 <= w + 0.5 and ry1 <= h + 0.5, (
                    w,
                    h,
                    n,
                    "the row stays on the page",
                )
                if chart == "none":
                    assert r["cell"] is None
                    assert r["text"][2] - r["text"][0] >= 0.4 * (rx1 - rx0), (
                        w,
                        h,
                        n,
                        "the words take the room the chart left",
                    )
                    continue
                cx0, cy0, cx1, cy1 = r["cell"]
                sx0, sy0, sx1, sy1 = r["svg"]
                assert cx0 >= rx0 - 0.5 and cx1 <= rx1 + 0.5, (
                    w,
                    h,
                    n,
                    "the dome's column is inside the row",
                )
                assert (
                    sx0 >= cx0 - 0.5
                    and sx1 <= cx1 + 0.5
                    and sy0 >= cy0 - 0.5
                    and sy1 <= cy1 + 0.5
                ), (w, h, n, r)
                assert sx1 - sx0 > 0.3 * (cy1 - cy0) or sx1 - sx0 > 30, (
                    w,
                    h,
                    n,
                    "the dome is not shrunk to nothing",
                )
            if (w, h) == (1200, 800) and n <= 6:
                assert not any(r["nameCut"] for r in rows), (
                    n,
                    chart,
                    "the long name is shown whole",
                )


def _rgba_png(w=300, h=200) -> str:
    import base64

    from PIL import Image, ImageDraw

    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse(
        (40, 40, w - 40, h - 40), fill=(200, 60, 40, 255)
    )  # its box corners stay clear
    out = io.BytesIO()
    im.save(out, "PNG")
    return "data:image/png;base64," + base64.b64encode(out.getvalue()).decode()


@pytest.mark.parametrize(
    "paper,rgb",
    [("night", (11, 16, 32)), ("blueprint", (29, 63, 115)), ("cream", (243, 234, 214))],
)
def test_cluster_cut_outs_sit_on_the_paper(browser_page, paper, rgb):
    src = _rgba_png()
    base = {
        "name": "a",
        "sci": "a",
        "src": src,
        "cut": src,
        "on_paper": False,
        "whole": False,
        "neutral": False,
        "no_flip": True,
        "factor": 1,
        "aspect": 1.5,
        "paper": None,
        "lines": ["A"],
    }
    specimens = [
        {**base, "classic": False},
        {**base, "name": "b", "classic": True},
    ]  # one drawn over, one by multiply
    sheet = {
        "specimens": specimens,
        "ratio": 1.5,
        "size": 900,
        "label": 0.02,
        "paper": paper,
        "ink": "#888",
        "layout": "grid",
    }
    got = browser_page.evaluate(
        "(j) => window.run(j)", {"kind": "sheet", "w": 10, "h": 10, "sheet": sheet}
    )
    assert len(got) == 2
    for g in got:
        assert all(abs(a - b) <= 10 for a, b in zip(g["corner"], rgb)), (
            paper,
            g,
            "the paper round a cut-out is the page's own paper, not white",
        )
        r, gr, b = g["middle"]
        assert r > 140 and r > 2.5 * gr and r > 2.5 * b, (
            paper,
            g,
            "the cut-out shows in its own colours, not black or white",
        )
    assert all(abs(a - b) <= 14 for a, b in zip(got[0]["middle"], (200, 60, 40))), (
        paper,
        got[0],
        "one with alpha is drawn as it is",
    )


def test_the_cluster_is_built_on_the_dark_paper():
    js = (ROOT / "orbit_core" / "static" / "orbit.js").read_text(encoding="utf-8")
    assert (
        "transparent: dark" not in js
        and "mix-blend-mode: screen; }\n      .sh-l" not in js
    )
    assert ".sh-page > img { mix-blend-mode" not in js
