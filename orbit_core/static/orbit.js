/* Orbit: the shared page for the three widgets. Each widget's client.js imports this and
   names its page. The server hands over the passes with their paintings as data URIs, so
   nothing is fetched here; the page is markup, an SVG sky chart and CSS. */

import { buildSheet } from './sheet.js';

const PAPER = { cream: '#f3ead6', white: '#ffffff', aged: '#e9dcc0', blueprint: '#1d3f73', night: '#0b1020' };
const INK = { cream: '#2a2116', white: '#111111', aged: '#2a2116', blueprint: '#eaf0f8', night: '#e8e6dc' };
/* Silhouettes in a 200 by 200 box. */
const SIL = {
  station: 'M20 92 h160 v16 h-160 Z M28 60 h28 v80 h-28 Z M64 60 h28 v80 h-28 Z M108 60 h28 v80 h-28 Z M144 60 h28 v80 h-28 Z M86 84 h28 v32 h-28 Z M60 96 h80 v8 h-80 Z',
  telescope: 'M70 40 h60 v120 h-60 Z M80 160 h40 v14 h-40 Z M10 86 h60 v28 h-60 Z M130 86 h60 v28 h-60 Z M70 40 a30 12 0 0 1 60 0 Z',
  satellite: 'M80 80 h40 v40 h-40 Z M14 88 h60 v24 h-60 Z M126 88 h60 v24 h-60 Z M90 60 h20 v20 h-20 Z M100 120 l-10 24 h20 Z',
  rocket: 'M80 30 h40 v120 h-40 Z M80 30 a20 10 0 0 1 40 0 Z M84 150 l-10 24 h52 l-10 -24 Z',
  other: 'M70 70 h60 v60 h-60 Z M30 92 h40 v16 h-40 Z M130 92 h40 v16 h-40 Z',
};

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

async function predecode(src) {
  if (!src || typeof Image === 'undefined') return;
  try { const img = new Image(); img.src = src; await Promise.race([img.decode(), new Promise((r) => setTimeout(r, 6000))]); } catch { /* shown as it is */ }
}

function sil(cls) {
  return `<svg class="ob-sil" viewBox="0 0 200 200" fill="currentColor" aria-hidden="true"><path d="${SIL[cls] || SIL.other}"/></svg>`;
}

function head(d, where = 'top') {
  if (d.header === 'hidden' || (d.header === 'bottom') !== (where === 'bottom')) return '';
  const bits = [d.title, d.area, d.period].filter(Boolean).map(esc).join(' · ');
  const line = `<div class="ph"><span class="ph-k">${bits}</span><b class="ph-d">${esc(d.time)} · ${esc(d.date)}</b></div>`;
  return where === 'bottom' ? `<div class="ph-rule"></div>${line}` : `${line}<div class="ph-rule"></div>`;
}

function foot(d) {
  const mode = d.footer || 'show';
  if (mode === 'hide') return '';
  const bits = [...(mode === 'credits' ? [] : [...(d.notices || []), ...(d.status || [])]), ...(d.credits || []), d.attribution].filter(Boolean);
  return bits.length ? `<div class="credit">${bits.map(esc).join(' · ')}</div>` : '';
}

function message(d, title, body, hint) {
  return `${head(d)}<div class="msg"><div class="msg-t">${esc(title)}</div><div class="msg-b">${esc(body)}</div>${hint ? `<div class="msg-h">${esc(hint)}</div>` : ''}</div>${foot(d)}`;
}

const IMPRESSION = 'an impression from its description, not from a picture';

function impression(p, cls = 'ob-imp') {
  return p.pic && p.pic.src && p.pic.impression ? `<span class="${cls}" title="${IMPRESSION}">impression</span>` : '';
}

function picture(p, cls = '') {
  if (p.pic && p.pic.src) return `<img class="ob-pic ${cls}${p.pic.whole ? ' whole' : ' cut'}" src="${p.pic.src}" alt="${esc(p.shown_name)}" decoding="sync">`;
  return `<span class="ob-pic ob-nopic ${cls}">${sil(p.cls)}</span>`;
}

/* The sky chart: the dome seen from above, north up, the zenith in the middle, the pass drawn
   as an arc with its rise and set marked. Azimuth clockwise from the top, elevation inward.
   ``pad`` widens the box either side so the rise and set times stay inside it. */
function dome(p, size = 100, pad = 0) {
  const R = size / 2 - 7;
  const cx = size / 2, cy = size / 2;
  const pt = (az, el) => { const r = R * (90 - el) / 90; const a = (az - 90) * Math.PI / 180; return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; };
  const track = p.track || [];
  const path = track.map(([, az, el], i) => { const [x, y] = pt(az, el); return `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`; }).join(' ');
  const [sx, sy] = track.length ? pt(track[0][1], track[0][2]) : [cx, cy];
  const [ex, ey] = track.length ? pt(track[track.length - 1][1], track[track.length - 1][2]) : [cx, cy];
  const [px, py] = pt(p.peak_az, p.peak_el);
  const rings = [30, 60].map((el) => `<circle cx="${cx}" cy="${cy}" r="${(R * (90 - el) / 90).toFixed(1)}" class="ob-ring"/>`).join('');
  const labels = [['N', 0], ['E', 90], ['S', 180], ['W', 270]].map(([t, az]) => { const [x, y] = pt(az, -9); return `<text x="${x.toFixed(1)}" y="${(y + 2.2).toFixed(1)}" class="ob-cp">${t}</text>`; }).join('');
  return `<svg class="ob-dome" viewBox="${-pad} 0 ${size + 2 * pad} ${size}" aria-label="The pass across the sky">
    <circle cx="${cx}" cy="${cy}" r="${R}" class="ob-horizon"/>${rings}
    <line x1="${cx}" y1="${cy - R}" x2="${cx}" y2="${cy + R}" class="ob-ring"/><line x1="${cx - R}" y1="${cy}" x2="${cx + R}" y2="${cy}" class="ob-ring"/>
    ${labels}
    <path d="${path}" class="ob-track"/>
    <circle cx="${sx.toFixed(1)}" cy="${sy.toFixed(1)}" r="2.2" class="ob-dot"/><circle cx="${ex.toFixed(1)}" cy="${ey.toFixed(1)}" r="2.2" class="ob-dot ob-end"/>
    <circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="3" class="ob-peak"/>
    <text x="${(sx + (sx > cx ? 4 : -4)).toFixed(1)}" y="${(sy + 2).toFixed(1)}" class="ob-t" text-anchor="${sx > cx ? 'start' : 'end'}">${esc(p.start_local)}</text>
    <text x="${(ex + (ex > cx ? 4 : -4)).toFixed(1)}" y="${(ey + 2).toFixed(1)}" class="ob-t" text-anchor="${ex > cx ? 'start' : 'end'}">${esc(p.end_local)}</text>
  </svg>`;
}

/* The pass: the painting in a ruled frame, the dome beside it, the particulars below. */
function passPage(d) {
  const p = d.passes[0];
  const portrait = (d.cell_h || 1) > (d.cell_w || 1);
  const rows = [
    ['When', `${p.day}, ${p.start_local} to ${p.end_local} (${p.duration})`],
    ['Path', `${p.leaves_shadow ? 'out of the shadow' : 'rises ' + p.rise_dir}, highest ${p.peak_el}° in the ${p.peak_dir} at ${p.peak_local}, ${p.enters_shadow ? 'into the shadow' : 'sets ' + p.set_dir}`],
    ['Brightness', `${p.bright} (magnitude ${p.mag})`],
    ['Range', `${p.range_km.toLocaleString()} km at its highest`],
  ];
  const now = p.in_progress ? `<span class="ob-now">passing over now</span>` : '';
  return `${head(d)}<div class="pa${portrait ? ' portrait' : ''}">
    <div class="pa-plate"><div class="pa-frame"><i class="tl"></i><i class="tr"></i><i class="bl"></i><i class="br"></i></div>${picture(p, 'pa-pic')}${impression(p, 'ob-imp pa-imp')}<div class="pa-fig">Fig. 1. ${esc(p.shown_name)}${p.pic && p.pic.impression ? ', an impression' : ''}${p.pic && p.pic.credit ? `, ${esc(p.pic.credit)}` : ''}</div></div>
    <div class="pa-note"><div class="pa-name">${esc(p.shown_name)}${now}</div><div class="pa-sub">${esc(p.day)} · ${esc(p.start_local)} · ${esc(p.peak_el)}° in the ${esc(p.peak_dir)}</div>
      ${d.chart !== 'none' ? `<div class="pa-dome">${dome(p, 100)}</div>` : ''}
      <dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl></div>
  </div>${head(d, 'bottom')}${foot(d)}`;
}

/* To-night: every pass coming, in order, each with its small painting and dome. The columns
   are chosen so each row comes out about three times as wide as it is tall, and each row's
   painting and dome columns from the row's size; the dome fits its own cell either way. */
const DOME_PAD = 15;
const DOME_ASPECT = (100 + 2 * DOME_PAD) / 100;

export function rowsPlan(n, W, H, chart = true, header = true, footer = true) {
  const m = Math.min(W, H) / 100;
  const gw = W - 4.8 * m, gh = H - 2 * m - (header ? 6.5 * m : 0) - (footer ? 3.6 * m : 0);
  let best = null;
  for (let cols = 1; cols <= Math.min(3, n); cols++) {
    const rows = Math.ceil(n / cols);
    const rw = (gw - (cols - 1) * 2 * m) / cols, rh = (gh - (rows - 1) * m) / rows - 0.8 * m;
    const score = Math.abs(Math.log(rw / Math.max(1, rh) / 4.5));
    if (!best || score < best.score - 1e-9) best = { cols, rows, rw, rh, score };
  }
  const { cols, rows, rw, rh } = best;
  const gap = 1.5 * m;
  // a row near square (one or two passes on the page) takes the painting across its top and
  // the words and the dome under it; a wide row has the three side by side
  const tall = rw / rh < 1.8;
  const band = tall ? 0.42 * rh : rh;
  let pic = tall ? 0 : Math.min(1.6 * rh, 0.28 * rw);
  let dome = chart ? Math.min(0.94 * band * DOME_ASPECT, (tall ? 0.42 : 0.3) * rw) : 0;
  const room = rw - 0.42 * rw - (chart ? 2 : 1) * gap;  // the words keep at least 42% of the row
  if (pic + dome > room) { const k = Math.max(0, room) / (pic + dome); pic *= k; dome *= k; }
  // the words grow on a roomy row, as far as both its height and the width left to them allow
  const words = rw - pic - dome - (chart ? 2 : 1) * gap;
  const scale = Math.max(1, Math.min(1.7, band / (14 * m), words / (40 * m)));
  return { cols, rows, tall, pic: (100 * pic) / rw, dome: (100 * dome) / rw, scale };
}

function tonightPage(d) {
  const n = d.passes.length;
  const chart = d.chart !== 'none';
  const plan = rowsPlan(n, d.cell_w || 800, d.cell_h || 480, chart, d.header !== 'hidden', (d.footer || 'show') !== 'hide');
  const tmpl = `${plan.tall ? '' : `${plan.pic.toFixed(2)}% `}minmax(0, 1fr)${chart ? ` ${plan.dome.toFixed(2)}%` : ''}`;
  return `${head(d)}<div class="tn-grid${plan.tall ? ' tall' : ''}" style="--cols:${plan.cols};--rows:${plan.rows};--tn-cols:${tmpl};--rs:${plan.scale.toFixed(3)}">${d.passes.map((p) => `<article class="tn-row${p.in_progress ? ' now' : ''}">
      <div class="tn-pic">${picture(p)}</div>
      <div class="tn-t"><b><span class="tn-name">${esc(p.shown_name)}</span>${impression(p, 'ob-imp tn-imp')}</b><span class="tn-when">${esc(p.day)} · ${esc(p.start_local)} to ${esc(p.end_local)}</span><span class="tn-l">${esc(p.peak_el)}° in the ${esc(p.peak_dir)}, ${esc(p.rise_dir)} to ${esc(p.set_dir)}</span><span class="tn-l tn-b">${esc(p.bright)}</span></div>
      ${chart ? `<div class="tn-dome">${dome(p, 100, DOME_PAD)}</div>` : ''}
    </article>`).join('')}</div>${head(d, 'bottom')}${foot(d)}`;
}

/* To-night, packed: every object's cut-out on a lattice from the middle out, sized by what it
   really is (the station a hundred metres across, a rocket stage ten), captioned with its pass. */
const SIZE_M = { station: 109, telescope: 13, satellite: 8, rocket: 11, other: 6 };
const SIL_URL = (cls) => 'data:image/svg+xml;utf8,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="400" height="400" fill="#7a7a7a"><path d="${SIL[cls] || SIL.other}"/></svg>`);

/* ---- building the sheet without holding the page ----
   The packer runs in one module worker (OffscreenCanvas) so the page, and an editor showing it,
   stay responsive while the sheet is built; the page builds the sheet itself where workers are
   missing or one fails. A sheet is kept by a key of everything that decides it, so a page drawn
   again from the same data (an editor's refresh while pictures are on the way) is not packed
   again. */
const WORKER_PATH = './sheet.js';
let WORKER = null;
let CHAIN = Promise.resolve();
function packOffThread(args) {
  if (typeof Worker === 'undefined' || typeof OffscreenCanvas === 'undefined') return buildSheet(args);
  const run = () => new Promise((resolve) => {
    try { if (!WORKER) WORKER = new Worker(new URL(WORKER_PATH, import.meta.url), { type: 'module' }); } catch { resolve(buildSheet(args)); return; }
    const w = WORKER;
    let done = false;
    const finish = (sheet) => { if (done) return; done = true; clearTimeout(timer); w.onmessage = null; w.onerror = null; resolve(sheet); };
    const drop = () => { if (WORKER === w) WORKER = null; try { w.terminate(); } catch { /* gone */ } };
    const timer = setTimeout(() => { drop(); finish(buildSheet(args)); }, 60000);
    w.onmessage = (e) => { if (e.data && e.data.kind === 'cut') return; finish(e.data && e.data.ok ? e.data.sheet : buildSheet(args)); };
    w.onerror = () => { drop(); finish(buildSheet(args)); };
    w.postMessage(args);
  });
  CHAIN = CHAIN.then(run, run);
  return CHAIN;
}
const fnv = (s) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(36); };
function keyOf(a) {
  const parts = a.specimens.map((x) => `${x.name}|${x.sci}|${x.src ? x.src.length : 0}|${x.whole ? 1 : 0}|${x.factor}|${x.aspect}|${(x.lines || []).join('/')}`);
  return `sh1:${a.ratio.toFixed(4)}:${a.size}:${a.label.toFixed(4)}:${a.paper}:${a.packer || ''}:${a.zoom}:${a.budget}:${fnv(parts.join(';'))}`;
}
const SHEETS = new Map();
const SHEETS_MAX = 8;

/* A silhouette as a PNG, drawn once per kind: a worker cannot decode the SVG itself. */
const SIL_PNG = new Map();
async function silPng(cls) {
  const k = SIL[cls] ? cls : 'other';
  if (SIL_PNG.has(k)) return SIL_PNG.get(k);
  let out = SIL_URL(k);
  try {
    const img = new Image();
    img.src = SIL_URL(k);
    await img.decode();
    const cv = document.createElement('canvas');
    cv.width = 400; cv.height = 400;
    cv.getContext('2d').drawImage(img, 0, 0, 400, 400);
    out = cv.toDataURL('image/png');
  } catch { /* the SVG as it is */ }
  SIL_PNG.set(k, out);
  return out;
}

async function packTonight(d) {
  const w = d.cell_w || 800, h = d.cell_h || 480;
  const seen = new Set();
  const specimens = [];
  for (const p of d.passes) {
    if (seen.has(p.norad)) continue;  // one picture per object, however many passes
    seen.add(p.norad);
    const pic = p.pic || {};
    const src = pic.src || await silPng(p.cls);
    const whole = !!pic.src && !!pic.whole;
    specimens.push({
      name: String(p.norad), sci: p.shown_name, src, cut: whole ? null : src, on_paper: false, classic: false, whole, neutral: false, no_flip: true,
      factor: Math.pow((SIZE_M[p.cls] || 8) / 30, 0.35), aspect: pic.aspect > 0 ? pic.aspect : 2, paper: null,
      lines: [p.shown_name + (pic.impression ? ' (impression)' : ''), `${p.day} · ${p.start_local}`, `${p.peak_el}° in the ${p.peak_dir}`, p.bright],
    });
  }
  const label = Math.max(0.017, 13 / h) * ((Number(d.text_size) || 100) / 100);
  const zoom = Math.max(0.4, Math.min(1, (Number(d.scale) || 100) / 100));
  const packer = ['spiral', 'voids'].includes(d.packing) ? d.packing : 'balanced';
  // while pictures are still on the way the page is drawn again soon: a quicker arrangement
  const budget = Number(d.live_refresh_s) > 0 ? 1500 : 4000;
  const args = { specimens, ratio: w / h, size: 1400, label, paper: ['white', 'aged', 'night', 'blueprint'].includes(d.paper) ? d.paper : 'cream', ink: INK[d.paper] || INK.cream, layout: 'cluster', packer, facing: 'inward', zoom , budget };
  const key = keyOf(args);
  if (SHEETS.has(key)) return SHEETS.get(key);
  try {
    const made = await packOffThread(args);
    if (made && made.src) {
      SHEETS.set(key, made);
      while (SHEETS.size > SHEETS_MAX) SHEETS.delete(SHEETS.keys().next().value);
    }
    return made;
  } catch (e) { console.warn('orbit: packing failed', e); return null; }
}

/* A caption line as the packer wrapped it: its breaks kept, so the line is as wide as was measured. */
const br = (t) => esc(t).replace(/\n/g, '<br>');

function packedPage(d, made) {
  const tags = made.items.map((m) => {
    const ls = m.lines || [];
    if (!ls.length) return '';
    return `<span class="sh-l" style="left:${(m.at[0] * 100).toFixed(2)}%;top:${(m.at[1] * 100).toFixed(2)}%"><span class="sh-ln sh-name">${br(ls[0])}</span>${ls.slice(1).map((t) => `<span class="sh-ln sh-sm">${br(t)}</span>`).join('')}</span>`;
  }).join('');
  const page = `<div class="sh-page" style="--r:${made.ratio};--lf:${made.label}"><img src="${made.src}" alt="" decoding="sync">${tags}</div>`;
  return `${head(d)}<div class="sh">${page}</div>${head(d, 'bottom')}${foot(d)}`;
}

/* The scene: one whole painting across the page, the pass written over it. */
function scenePage(d) {
  const p = d.passes[0];
  const art = p.pic && p.pic.src ? `<div class="sc-bg" style="background-image:url('${p.pic.src}');background-size:${p.pic.whole ? 'cover' : 'contain'}"></div>` : `<div class="sc-bg sc-none">${sil(p.cls)}</div>`;
  const top = d.header === 'hidden' ? '' : `<div class="sc-top"><span>${esc(d.title)}</span><span>${esc(d.time)} · ${esc(d.date)}</span></div>`;
  return `${art}${top}${d.chart !== 'none' ? `<div class="sc-dome">${dome(p, 100)}</div>` : ''}<div class="sc-main"><div class="sc-name">${esc(p.shown_name)}</div><div class="sc-when">${esc(p.day)} · ${esc(p.start_local)} to ${esc(p.end_local)} · ${esc(p.peak_el)}° in the ${esc(p.peak_dir)}${p.pic && p.pic.impression ? ' · an impression, not from a picture' : ''}</div><div class="sc-r">${esc(p.about)}</div></div>${foot(d).replace('class="credit"', 'class="credit sc-credit"')}`;
}

export async function render(shadow, ctx, widget) {
  const d = ctx.data || {};
  const size = ctx.cell?.size || 'md';
  d.cell_w = ctx.cell?.w; d.cell_h = ctx.cell?.h;
  let body;
  if (!d.widget && !d.error) body = `<div class="msg"><div class="msg-t">Orbit</div><div class="msg-b">No data from the server yet.</div></div>`;
  else if (d.state === 'error' || d.error) body = message(d, d.title || 'Orbit', d.error || 'Something went wrong.', d.hint);
  else if (d.state === 'empty') body = message(d, d.title || 'Orbit', 'Nothing bright passes over in the dark.', d.hint);
  else if (d.state === 'computing') body = message(d, d.title || 'Orbit', 'Working out the passes.', d.hint);
  else {
    for (const p of d.passes) if (p.pic && p.pic.src) await predecode(p.pic.src);
    if (widget === 'tonight' && d.layout === 'cluster' && typeof document !== 'undefined') {
      const made = await packTonight(d);
      if (made && made.src) { await predecode(made.src); body = packedPage(d, made); }
      else body = tonightPage(d);
    } else body = widget === 'tonight' ? tonightPage(d) : widget === 'scene' ? scenePage(d) : passPage(d);
  }
  const paper = PAPER[d.paper] || PAPER.cream;
  const ink = INK[d.paper] || INK.cream;
  const dark = d.paper === 'night' || d.paper === 'blueprint';
  const fonts = {
    fell: "--serif: 'IM Fell English', Georgia, serif; --sc: 'IM Fell English SC', Georgia, serif; --sans: 'Archivo Narrow', Arial, sans-serif;",
    archivo: "--serif: 'Archivo Narrow', Arial, sans-serif; --sc: 'Archivo Narrow', Arial, sans-serif; --sans: 'Archivo Narrow', Arial, sans-serif;",
    georgia: "--serif: Georgia, 'Times New Roman', serif; --sc: Georgia, 'Times New Roman', serif; --sans: Georgia, 'Times New Roman', serif;",
    page: "--serif: inherit; --sc: inherit; --sans: inherit;",
  }[d.font] || '';
  shadow.innerHTML = `
    <style>${d.font_css || ''}</style>
    <div class="ob ${esc(widget)} font-${esc(d.font || 'fell')} paper-${esc(d.paper || 'cream')} size-${esc(size)} lv-${esc(d.panel || 'colour')}${dark ? ' dark' : ''}" style="--paper:${paper};--ink:${ink};--ts:${(Number(d.text_size) || 100) / 100};${fonts}">${body}</div>
    <style>
      :host { display: block; height: 100%; }
      .ob { container-type: size; height: 100%; width: 100%; overflow: hidden; position: relative; display: flex; flex-direction: column; background: var(--paper); color: var(--ink); font-family: var(--serif); font-variant-numeric: tabular-nums; }
      .ob.font-page { font-family: inherit; }
      .ob.font-archivo .ph-k, .ob.font-archivo .pa-name, .ob.font-archivo .pa-note dt, .ob.font-georgia .ph-k, .ob.font-page .ph-k { text-transform: uppercase; letter-spacing: .1em; }
      .lv-mono { --ink: #000; }
      .ob.lv-mono .ob-pic.cut, .ob.lv-gray4 .ob-pic.cut { filter: contrast(1.15); }
      .ob.dark .ob-pic.cut { mix-blend-mode: screen; }
      .ph { display: flex; justify-content: space-between; align-items: baseline; gap: 2cqmin; padding: 1.2cqmin 2.4cqmin .3cqmin; flex: 0 0 auto; font-size: calc(var(--ts) * 1em); }
      .ph-k { font-family: var(--sc); font-size: 2.4cqmin; letter-spacing: .13em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .ph-d { font-weight: 400; font-size: 3cqmin; letter-spacing: .04em; white-space: nowrap; }
      .ph-rule { border-top: 1px solid var(--ink); position: relative; margin: 0 2.4cqmin .2cqmin; flex: 0 0 auto; }
      .ph-rule::after { content: ""; position: absolute; left: 0; right: 0; top: 2px; border-top: 1px solid var(--ink); }
      .credit { flex: 0 0 auto; font-size: 1.7cqmin; opacity: .7; padding: .3cqmin 2.4cqmin .7cqmin; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-style: italic; }
      .msg { flex: 1; display: flex; flex-direction: column; justify-content: center; gap: 1.4cqmin; padding: 4cqmin 6cqmin; text-align: center; }
      .msg-t { font-family: var(--sc); font-size: 5cqmin; letter-spacing: .06em; } .msg-b { font-size: 3.4cqmin; } .msg-h { font-size: 2.6cqmin; font-style: italic; opacity: .75; }
      .ob-nopic { position: relative; display: block; overflow: hidden; }
      /* the mark on a painting made from words alone */
      .ob-imp { font-family: var(--sans); font-size: calc(var(--ts) * 1.9cqmin); letter-spacing: .14em; text-transform: uppercase; border: 1px solid var(--ink); padding: .25em .7em; opacity: .75; }
      .pa-imp { position: absolute; left: 2.6cqmin; top: 2.6cqmin; } .tn-imp { margin-left: .6em; font-size: calc(var(--ts) * 1.5cqmin * var(--rs, 1)); padding: .15em .5em; vertical-align: middle; letter-spacing: .1em; }
      .ob-sil { position: absolute; inset: 0; width: 100%; height: 100%; opacity: .3; }
      /* the dome */
      .ob-dome { width: 100%; height: 100%; display: block; overflow: visible; }
      .ob-horizon { fill: none; stroke: var(--ink); stroke-width: .8; } .ob-ring { fill: none; stroke: var(--ink); stroke-width: .35; opacity: .45; stroke-dasharray: 1.5 1.5; }
      .ob-track { fill: none; stroke: var(--ink); stroke-width: 1.8; stroke-linecap: round; } .ob-dot { fill: var(--paper); stroke: var(--ink); stroke-width: 1; } .ob-end { fill: var(--ink); } .ob-peak { fill: var(--ink); }
      .ob-cp { font-family: var(--sc); font-size: 6px; text-anchor: middle; fill: var(--ink); letter-spacing: .05em; } .ob-t { font-family: var(--sans); font-size: 5.5px; fill: var(--ink); }
      .ob.dark .ob-track { stroke: #ffd66b; } .ob.dark .ob-peak, .ob.dark .ob-end { fill: #ffd66b; }
      /* the pass */
      .pa { flex: 1; min-height: 0; display: grid; grid-template-columns: 58fr 42fr; gap: 2cqmin; padding: 1.5cqmin 2.4cqmin; }
      .pa.portrait { grid-template-columns: 1fr; grid-template-rows: 55fr 45fr; }
      .pa-plate { position: relative; display: flex; align-items: center; justify-content: center; min-height: 0; padding: 4cqmin; }
      .pa-frame { position: absolute; inset: 1cqmin; border: 1.5px solid var(--ink); outline: 1px solid var(--ink); outline-offset: 4px; }
      .pa-frame i { position: absolute; width: 4cqmin; height: 4cqmin; border: 1.5px solid var(--ink); }
      .pa-frame i.tl { left: -1.3cqmin; top: -1.3cqmin; border-right: 0; border-bottom: 0; } .pa-frame i.tr { right: -1.3cqmin; top: -1.3cqmin; border-left: 0; border-bottom: 0; }
      .pa-frame i.bl { left: -1.3cqmin; bottom: -1.3cqmin; border-right: 0; border-top: 0; } .pa-frame i.br { right: -1.3cqmin; bottom: -1.3cqmin; border-left: 0; border-top: 0; }
      .pa-pic { max-width: 92%; max-height: 82%; object-fit: contain; mix-blend-mode: multiply; } .pa-pic.whole { mix-blend-mode: normal; max-height: 90%; } .ob.dark .pa-pic { mix-blend-mode: normal; }
      .ob-nopic.pa-pic { width: 60%; aspect-ratio: 1; }
      .pa-fig { position: absolute; left: 0; right: 0; bottom: 2.2cqmin; text-align: center; font-size: calc(var(--ts) * 1.9cqmin); font-style: italic; padding: 0 3cqmin; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .pa-note { display: grid; grid-template-columns: 1fr auto; grid-template-rows: auto auto 1fr; gap: .4cqmin 2cqmin; min-width: 0; padding-top: 1cqmin; align-content: start; }
      .pa-name { grid-column: 1 / -1; font-family: var(--sc); font-size: calc(var(--ts) * 5.2cqmin); letter-spacing: .03em; line-height: 1.05; }
      .ob-now { display: inline-block; margin-left: 1.2cqmin; font-family: var(--sans); font-size: .42em; letter-spacing: .12em; text-transform: uppercase; border: 1px solid var(--ink); padding: .2em .6em; vertical-align: middle; }
      .pa-sub { grid-column: 1 / -1; font-size: calc(var(--ts) * 2.8cqmin); opacity: .85; }
      .pa-dome { grid-column: 2; grid-row: 3; width: 28cqmin; height: 28cqmin; } .pa.portrait .pa-dome { width: 34cqmin; height: 34cqmin; }
      .pa-note dl { grid-column: 1; grid-row: 3; margin: .6cqmin 0 0; display: grid; grid-template-columns: auto 1fr; gap: .5cqmin 1.4cqmin; font-size: calc(var(--ts) * 2.4cqmin); align-content: start; min-width: 0; }
      .pa-note dt { font-family: var(--sc); letter-spacing: .08em; font-size: .8em; opacity: .8; padding-top: .3em; } .pa-note dd { margin: 0; }
      /* to-night, packed */
      .sh { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; padding: 0 .6cqmin; }
      .sh-page { position: relative; aspect-ratio: var(--r); max-width: 100%; max-height: 100%; width: min(100%, calc((100cqh - 9cqmin) * var(--r))); container-type: size; }
      .sh-page > img { display: block; width: 100%; height: 100%; }
      .sh-l { position: absolute; transform: translate(-50%, 12%); white-space: nowrap; text-align: center; line-height: 1.15; font-family: var(--sc); font-size: calc(var(--lf) * 100cqh); letter-spacing: .04em; color: var(--ink); --halo: var(--paper); text-shadow: .06em 0 0 var(--halo), -.06em 0 0 var(--halo), 0 .06em 0 var(--halo), 0 -.06em 0 var(--halo), .045em .045em 0 var(--halo), -.045em .045em 0 var(--halo), .045em -.045em 0 var(--halo), -.045em -.045em 0 var(--halo); }
      .sh-ln { display: block; } .sh-sm { font-family: var(--serif); font-style: italic; letter-spacing: 0; font-size: .88em; opacity: .85; }
      /* to-night */
      .tn-grid { flex: 1; min-height: 0; display: grid; grid-template-columns: repeat(var(--cols), minmax(0, 1fr)); grid-template-rows: repeat(var(--rows), minmax(0, 1fr)); gap: 1cqmin 2cqmin; padding: 1cqmin 2.4cqmin; }
      .tn-row { display: grid; grid-template-columns: var(--tn-cols); gap: 1.5cqmin; align-items: center; min-height: 0; min-width: 0; overflow: hidden; border-bottom: 1px solid color-mix(in srgb, var(--ink) 25%, transparent); padding: .4cqmin 0; }
      .tn-grid.tall .tn-row { grid-template-rows: 56% minmax(0, 1fr); align-items: center; } .tn-grid.tall .tn-pic { grid-column: 1 / -1; padding: 1cqmin 0; box-sizing: border-box; }
      .tn-row.now { background: color-mix(in srgb, var(--ink) 7%, transparent); }
      .tn-pic { height: 100%; min-height: 0; min-width: 0; display: flex; align-items: center; justify-content: center; } .tn-pic .ob-pic { max-width: 100%; max-height: 100%; object-fit: contain; mix-blend-mode: multiply; } .ob.dark .tn-pic .ob-pic { mix-blend-mode: normal; } .ob-nopic.ob-pic { width: 70%; aspect-ratio: 1; }
      .tn-t { display: flex; flex-direction: column; min-width: 0; line-height: 1.2; }
      .tn-t b { font-family: var(--sc); font-weight: 700; font-size: calc(var(--ts) * 2.9cqmin * var(--rs)); letter-spacing: .03em; line-height: 1.1; margin-bottom: .1em; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; overflow-wrap: anywhere; }
      .tn-imp { display: inline-block; white-space: nowrap; line-height: 1.2; }
      .tn-when { font-size: calc(var(--ts) * 2.4cqmin * var(--rs)); } .tn-l { font-size: calc(var(--ts) * 2cqmin * var(--rs)); opacity: .85; font-style: italic; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; } .tn-b { font-style: normal; }
      .tn-dome { container-type: size; height: 100%; min-width: 0; display: flex; align-items: center; justify-content: center; }
      .tn-dome .ob-dome { width: min(100cqw, ${(100 * DOME_ASPECT).toFixed(1)}cqh); height: auto; aspect-ratio: ${DOME_ASPECT}; flex: 0 0 auto; overflow: hidden; }
      /* the scene */
      .sc-bg { position: absolute; inset: 0; background-position: center; background-repeat: no-repeat; } .sc-none .ob-sil { inset: 15cqmin; width: auto; height: auto; }
      .sc-top, .sc-main, .sc-credit, .sc-dome { position: absolute; font-family: var(--sans); }
      .sc-top { top: 2.6cqmin; left: 2.6cqmin; right: 2.6cqmin; display: flex; justify-content: space-between; font-size: 2.6cqmin; letter-spacing: .1em; text-transform: uppercase; }
      .sc-main, .sc-top, .sc-credit { --halo: rgba(0,0,0,.75); text-shadow: 0 0 .6cqmin var(--halo), 0 0 1.2cqmin var(--halo); color: #fff; }
      .sc-dome { right: 2.6cqmin; top: 7cqmin; width: 26cqmin; height: 26cqmin; --ink: #fff; --paper: transparent; filter: drop-shadow(0 0 .5cqmin rgba(0,0,0,.8)); }
      .sc-main { left: 3cqmin; right: 32cqmin; bottom: 6cqmin; max-width: 70%; }
      .sc-name { font-size: calc(var(--ts) * 9cqmin); font-weight: 700; line-height: .95; }
      .sc-when { font-size: calc(var(--ts) * 3.2cqmin); font-weight: 600; margin-top: .8cqmin; }
      .sc-r { font-size: calc(var(--ts) * 2.5cqmin); margin-top: .6cqmin; line-height: 1.3; }
      .sc-credit { left: 2.6cqmin; right: auto; bottom: 2cqmin; max-width: 60%; padding: 0; }
    </style>`;
}
