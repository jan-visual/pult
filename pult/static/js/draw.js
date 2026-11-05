// Pult: kreslení do snímků (pero s tlakem Pencilu, šipka, kroužek, obdélník, guma), zpět/znovu,
// živé tahy ostatních a vrstva s kresbou pro revizi.
import { $, $$, S, store, api, clientId, uid, emit, on, isTouch, toast, fmtTC, dbg } from "./core.js";
import { vid, img, cv, wrap, item, isVideo, fps, curFrame, pause, toggle, seekFrame, publish } from "./player.js";
import { op } from "./notes.js";

const ctx = cv.getContext("2d");
S.undo = []; S.redo = [];
S.drawing = false;

// ---------- vykreslení ----------
const widthOf = (p, pen) => (pen ? 0.12 + 3.4 * Math.pow(Math.min(1, p * 2), 0.8) : 1);

export function drawStroke(c, s, W, H) {
  c.strokeStyle = c.fillStyle = s.color;
  c.lineCap = "round"; c.lineJoin = "round";
  const base = Math.max(1, s.w * W);
  const P = s.pts.map((p) => [p[0] * W, p[1] * H, p[2] == null ? 0.5 : p[2]]);
  if (s.tool === "arrow" || s.tool === "ellipse" || s.tool === "rect") {
    if (P.length < 2) return;
    const a = P[0], b = P[P.length - 1];
    c.lineWidth = base;
    c.beginPath();
    if (s.tool === "arrow") {
      const ang = Math.atan2(b[1] - a[1], b[0] - a[0]), head = Math.max(base * 4, 10);
      c.moveTo(a[0], a[1]); c.lineTo(b[0] - Math.cos(ang) * head * 0.6, b[1] - Math.sin(ang) * head * 0.6); c.stroke();
      c.beginPath(); c.moveTo(b[0], b[1]);
      c.lineTo(b[0] - head * Math.cos(ang - 0.45), b[1] - head * Math.sin(ang - 0.45));
      c.lineTo(b[0] - head * Math.cos(ang + 0.45), b[1] - head * Math.sin(ang + 0.45));
      c.closePath(); c.fill();
      return;
    }
    if (s.tool === "ellipse") c.ellipse((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, Math.abs(b[0] - a[0]) / 2, Math.abs(b[1] - a[1]) / 2, 0, 0, Math.PI * 2);
    else c.rect(Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]));
    c.stroke();
    return;
  }
  if (P.length === 1) { c.beginPath(); c.arc(P[0][0], P[0][1], (base * widthOf(P[0][2], s.pen)) / 2, 0, Math.PI * 2); c.fill(); return; }
  let prev = P[0];
  for (let i = 1; i < P.length; i++) {
    const p = P[i], mid = i < P.length - 1 ? [(p[0] + P[i + 1][0]) / 2, (p[1] + P[i + 1][1]) / 2] : p;
    c.lineWidth = base * widthOf(p[2], s.pen);
    c.beginPath(); c.moveTo(prev[0], prev[1]); c.quadraticCurveTo(p[0], p[1], mid[0], mid[1]); c.stroke();
    prev = mid;
  }
}

export function strokesAt(n, frame) { return Object.values(S.notes.strokes).filter((s) => s.n === n && s.frame === frame); }

// co je vidět: zastaveno = přesně tento snímek; při přehrávání kresba chvíli „drží“ (Nastavení › Přehrávání)
function visible() {
  const it = item();
  if (!it || it.state !== "ready") return [];
  if (it.kind !== "video") return strokesAt(S.n, 0);
  const f = !vid.paused && S.shownFrame >= 0 ? S.shownFrame : curFrame();
  if (vid.paused) return strokesAt(S.n, f);
  const hf = Math.max(1, Math.round(S.hold * fps()));
  return Object.values(S.notes.strokes).filter((s) => s.n === S.n && s.frame <= f && f < s.frame + hf);
}

let lastEmpty = true;
export function redraw() {
  const W = cv.clientWidth, H = cv.clientHeight;
  if (!W || !H) return;
  const pr = cv.width / W;
  const list = visible();
  const it = item(), f = isVideo() ? curFrame() : 0;
  const live = Object.values(S.live).filter((l) => l.s.n === S.n && l.s.frame === f && (vid.paused || !isVideo()));
  if (!list.length && !live.length && !S.cur && lastEmpty) return;
  ctx.setTransform(pr, 0, 0, pr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  for (const s of list) drawStroke(ctx, s, W, H);
  for (const l of live) { ctx.globalAlpha = 0.8; drawStroke(ctx, l.s, W, H); ctx.globalAlpha = 1; }
  if (S.cur && it) drawStroke(ctx, S.cur, W, H);
  lastEmpty = !list.length && !live.length && !S.cur;
}
let rafPending = false;
export function requestRedraw() { if (!rafPending) { rafPending = true; requestAnimationFrame(() => { rafPending = false; redraw(); }); } }
on("frame", requestRedraw);
on("redraw", () => { lastEmpty = false; requestRedraw(); });
on("notes", () => { lastEmpty = false; requestRedraw(); });

// ---------- vstup ----------
function pt(e) {
  const r = cv.getBoundingClientRect();
  return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)),
    e.pointerType === "pen" ? (e.pressure || 0.5) : 0.5];
}
const ready = () => { const it = item(); return !!it && it.state === "ready"; };

cv.addEventListener("pointerdown", (e) => {
  if (!ready()) return;
  if (e.pointerType === "touch" && !S.finger) return; // prst: gesta (klepnutí, swipe) řeší níž
  if (e.pointerType === "mouse" && e.button === 1) return startPan(e);
  if (e.pointerType === "mouse" && e.button !== 0) return;
  e.preventDefault();
  try { cv.setPointerCapture(e.pointerId); } catch {}
  // myš: klik = přehrát / pauza, tah = kreslení
  if (e.pointerType === "mouse" && S.tool !== "eraser") { S.press = { x: e.clientX, y: e.clientY, p0: pt(e) }; return; }
  begin(e, pt(e));
});
cv.addEventListener("pointermove", (e) => {
  if (S.press) {
    if (Math.hypot(e.clientX - S.press.x, e.clientY - S.press.y) < 4) return;
    const p0 = S.press.p0; S.press = null;
    begin(e, p0);
  }
  if (!S.drawing || (e.pointerType === "touch" && !S.finger)) return;
  e.preventDefault();
  if (S.erasing) { eraseAt(pt(e)); return; }
  if (!S.cur) return;
  if (S.cur.tool === "pen") {
    const evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
    for (const ev of evs.length ? evs : [e]) {
      const q = pt(ev), last = S.cur.pts[S.cur.pts.length - 1];
      if (S.cur.pen && last) q[2] = 0.6 * q[2] + 0.4 * last[2];
      S.cur.pts.push(q);
    }
  } else {
    let q = pt(e);
    if (e.shiftKey && S.cur.tool !== "arrow") { // Shift: kruh / čtverec
      const a = S.cur.pts[0], W = cv.clientWidth, H = cv.clientHeight;
      const d = Math.max(Math.abs(q[0] - a[0]) * W, Math.abs(q[1] - a[1]) * H);
      q = [a[0] + Math.sign(q[0] - a[0] || 1) * d / W, a[1] + Math.sign(q[1] - a[1] || 1) * d / H, 0.5];
    }
    S.cur.pts = [S.cur.pts[0], q];
  }
  sendLive();
  requestRedraw();
});
cv.addEventListener("pointerup", end);
cv.addEventListener("pointercancel", end);

function begin(e, p0) {
  emit("before-play");
  if (isVideo() && !vid.paused) pause();
  S.drawing = true;
  const n = S.n, frame = isVideo() ? curFrame() : 0;
  if (S.tool === "eraser") { S.erasing = { n, frame, removed: [] }; eraseAt(p0); return; }
  S.cur = { id: uid(), n, frame, tool: S.tool, color: S.color, w: S.size, pen: e.pointerType === "pen", pts: [p0], by: S.me.name, byc: S.me.color };
  requestRedraw();
}

function end(e) {
  if (S.press) {
    S.press = null;
    if (e.type === "pointerup" && isVideo()) { toggle(); emit("kbar"); }
    return;
  }
  if (!S.drawing) return;
  S.drawing = false;
  if (S.erasing) {
    const er = S.erasing; S.erasing = null;
    if (er.removed.length) {
      op({ op: "stroke.del", ids: er.removed.map((s) => s.id) }, { localDone: true });
      pushUndo({ type: "del", strokes: er.removed });
    }
    return;
  }
  const s = S.cur; S.cur = null;
  sendLive(true, s);
  if (!s) return;
  if (s.tool !== "pen") {
    const [a, b] = [s.pts[0], s.pts[s.pts.length - 1]];
    if (s.pts.length < 2 || Math.hypot((a[0] - b[0]) * cv.clientWidth, (a[1] - b[1]) * cv.clientHeight) < 4) { requestRedraw(); return; }
  }
  addStrokes([s]);
  pushUndo({ type: "add", strokes: [s] });
}

export function addStrokes(list) {
  for (const s of list) S.notes.strokes[s.id] = s;
  op({ op: "stroke.add", strokes: list }, { localDone: true });
}
function delStrokes(list) {
  for (const s of list) delete S.notes.strokes[s.id];
  op({ op: "stroke.del", ids: list.map((s) => s.id) }, { localDone: true });
}

// guma: maže celé tahy, kterých se dotkne (i tvary podle obrysu)
function distSeg(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy;
  const t = l2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)) : 0;
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
}
function hit(s, p, W, H, R) {
  const P = s.pts.map((q) => [q[0] * W, q[1] * H]), x = [p[0] * W, p[1] * H], r = R + (s.w * W) / 2;
  if (s.tool === "pen") return P.length === 1 ? Math.hypot(x[0] - P[0][0], x[1] - P[0][1]) < r : P.some((q, i) => i && distSeg(x, P[i - 1], q) < r);
  const a = P[0], b = P[P.length - 1];
  if (s.tool === "arrow") return distSeg(x, a, b) < r;
  if (s.tool === "rect") { const c = [[a[0], a[1]], [b[0], a[1]], [b[0], b[1]], [a[0], b[1]]]; return c.some((q, i) => distSeg(x, q, c[(i + 1) % 4]) < r); }
  const cx = (a[0] + b[0]) / 2, cy = (a[1] + b[1]) / 2, rx = Math.abs(b[0] - a[0]) / 2, ry = Math.abs(b[1] - a[1]) / 2;
  let prev = null;
  for (let i = 0; i <= 48; i++) { const q = [cx + rx * Math.cos(i / 48 * Math.PI * 2), cy + ry * Math.sin(i / 48 * Math.PI * 2)]; if (prev && distSeg(x, prev, q) < r) return true; prev = q; }
  return false;
}
function eraseAt(p) {
  const er = S.erasing, W = cv.clientWidth, H = cv.clientHeight;
  const gone = strokesAt(er.n, er.frame).filter((s) => hit(s, p, W, H, 12 / (S.zoom ? S.zoom.k : 1)));
  if (!gone.length) return;
  for (const s of gone) { delete S.notes.strokes[s.id]; er.removed.push(s); }
  emit("notes-local");
  requestRedraw();
}

// posun přiblíženého obrazu prostředním tlačítkem myši
function startPan(e) {
  if (S.zoom.k <= 1) return;
  e.preventDefault();
  const sx = e.clientX, sy = e.clientY, ox = S.zoom.x, oy = S.zoom.y;
  const move = (ev) => { S.zoom.x = ox + ev.clientX - sx; S.zoom.y = oy + ev.clientY - sy; emit("zoom-pan"); };
  const up = () => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); };
  addEventListener("pointermove", move); addEventListener("pointerup", up);
}

// ---------- zpět / znovu (moje změny, i když kreslí víc lidí) ----------
function pushUndo(x) { S.undo.push(x); if (S.undo.length > 200) S.undo.shift(); S.redo = []; }
function focusOn(strokes) {
  const s = strokes[0];
  if (!s) return;
  if (s.n !== S.n) emit("goto", { n: s.n, frame: s.frame });
  else if (isVideo() && curFrame() !== s.frame) { if (!vid.paused) vid.pause(); seekFrame(s.frame); }
}
export function undo() {
  const x = S.undo.pop();
  if (!x) return toast("Není co vrátit", { ms: 1200 });
  focusOn(x.strokes);
  if (x.type === "add") delStrokes(x.strokes.filter((s) => S.notes.strokes[s.id])); else addStrokes(x.strokes);
  S.redo.push(x);
  emit("notes-local");
}
export function redo() {
  const x = S.redo.pop();
  if (!x) return toast("Není co zopakovat", { ms: 1200 });
  focusOn(x.strokes);
  if (x.type === "add") addStrokes(x.strokes); else delStrokes(x.strokes.filter((s) => S.notes.strokes[s.id]));
  S.undo.push(x);
  emit("notes-local");
}
export function clearFrame() {
  if (!ready()) return;
  clearAt(S.n, isVideo() ? curFrame() : 0);
}
export function clearAt(n, frame) {
  const list = strokesAt(n, frame);
  if (!list.length) return toast("Na tomhle snímku není žádná kresba", { ms: 1500 });
  delStrokes(list);
  pushUndo({ type: "del", strokes: list });
  emit("notes-local");
  toast(list.length === 1 ? "Kresba smazána" : `Smazáno ${list.length} tahů`, { action: "Vrátit", onAction: undo, ms: 5000 });
}
export function resetHistory() { S.undo = []; S.redo = []; S.live = {}; }

// ---------- živé tahy: ostatní vidí, jak kreslíš ----------
let liveAt = 0, liveTimer = 0;
function sendLive(done = false, s = S.cur) {
  if (!S.batch || !s || !S.people.some((p) => p.id !== clientId)) return;
  const now = Date.now();
  if (!done && now - liveAt < 90) { if (!liveTimer) liveTimer = setTimeout(() => { liveTimer = 0; sendLive(); }, 90); return; }
  liveAt = now;
  const body = done ? { from: clientId, batch: S.batch.id, id: s.id, done: true } : { from: clientId, batch: S.batch.id, stroke: { ...s, pts: s.pts.slice(-800) } };
  api("POST", "/api/live", body).catch(() => {});
}
export function onLive(m) {
  if (m.from === clientId || !S.batch || m.batch !== S.batch.id) return;
  if (m.done) delete S.live[m.id];
  else if (m.stroke) S.live[m.stroke.id] = { s: m.stroke, at: Date.now() };
  requestRedraw();
}
setInterval(() => { const old = Date.now() - 5000; let ch = false; for (const [k, l] of Object.entries(S.live)) if (l.at < old) { delete S.live[k]; ch = true; } if (ch) requestRedraw(); }, 2000);

// ---------- vrstva s kresbou pro revizi (Claude dostane snímek + kresbu + popisek) ----------
// Jedno plátno pro všechny snímky: starý iPad má na plátna malý limit paměti.
let ovc = null;
export function releaseOverlay() { if (ovc) { ovc.width = ovc.height = 0; ovc = null; } }
export function renderOverlay(it, frame, label) {
  let W = it.rw || it.width, H = it.rh || it.height;
  if (!W || !H) return null;
  if (it.n === S.n && it.kind === "image" && img.naturalWidth) { // otočená fotka: poměr stran podle prohlížeče
    const k = Math.min(1, 2560 / Math.max(img.naturalWidth, img.naturalHeight));
    W = Math.max(2, Math.round((img.naturalWidth * k) / 2) * 2); H = Math.max(2, Math.round((img.naturalHeight * k) / 2) * 2);
  }
  const c = ovc || (ovc = document.createElement("canvas"));
  c.width = W; c.height = H;
  const x = c.getContext("2d");
  if (!x) return null;
  x.clearRect(0, 0, W, H);
  for (const s of strokesAt(it.n, frame)) drawStroke(x, s, W, H);
  const fs = Math.max(14, Math.round(Math.min(W, H) * 0.028));
  x.font = `600 ${fs}px -apple-system, "Segoe UI", system-ui, sans-serif`;
  const tw = x.measureText(label).width, pad = fs * 0.5;
  x.fillStyle = "rgba(0,0,0,.62)";
  x.fillRect(10, H - fs * 1.7 - 10, tw + pad * 2, fs * 1.7);
  x.fillStyle = "#fff";
  x.fillText(label, 10 + pad, H - 10 - fs * 0.52);
  try { return c.toDataURL("image/png"); } catch { return null; }
}

// ---------- paleta ----------
export function setTool(t) {
  S.tool = t; store.set("tool", t);
  $$("[data-tool]").forEach((b) => b.classList.toggle("on", b.dataset.tool === t));
  $("#app").classList.toggle("tool-eraser", t === "eraser");
}
export function setColor(c) {
  S.color = c; store.set("pen", c);
  $$("[data-color]").forEach((b) => b.classList.toggle("on", b.dataset.color === c));
  if (S.tool === "eraser") setTool("pen");
}
export function setSize(v) {
  S.size = v; store.set("size", v);
  $$("[data-size]").forEach((b) => b.classList.toggle("on", +b.dataset.size === v));
}
export function sizeStep(d) { const sizes = $$("[data-size]").map((b) => +b.dataset.size); const i = sizes.indexOf(S.size); setSize(sizes[Math.max(0, Math.min(sizes.length - 1, (i < 0 ? 1 : i) + d))]); }
export function colorAt(i) { const b = $$("[data-color]")[i]; if (b) setColor(b.dataset.color); }
export function setFinger(v) { S.finger = v; store.set("finger", v); $("#fingerBtn").classList.toggle("on", v); }
$$("[data-tool]").forEach((b) => (b.onclick = () => setTool(b.dataset.tool)));
$$("[data-color]").forEach((b) => (b.onclick = () => setColor(b.dataset.color)));
$$("[data-size]").forEach((b) => (b.onclick = () => setSize(+b.dataset.size)));
$("#undoBtn").onclick = undo;
$("#redoBtn").onclick = redo;
$("#clearBtn").onclick = clearFrame;
$("#fingerBtn").onclick = () => { setFinger(!S.finger); toast(S.finger ? "Prst kreslí" : "Prst přehrává a přepíná, kreslí jen Pencil", { ms: 1600 }); };
setTool(S.tool); setColor(S.color); setSize(S.size); setFinger(S.finger);

// ---------- dotyk na iPadu: klepnutí = přehrát/pauza, swipe = další/předchozí položka ----------
// Hlídají se touch i pointer události (co přijde první), Pencil se ignoruje, víc prstů gesto ruší.
const inStage = (el) => !!(el && el.closest && el.closest("#stage")) && !(S.finger && el.id === "cv") && !el.closest(".palette, .kbar");
const sw = {};
const touchPointers = new Set();
let lastSwipe = 0, lastTap = 0, multiUntil = 0;
function cancelGesture() { delete sw.t; delete sw.p; multiUntil = Date.now() + 500; }
function gestureEnd(kind, id, x, y) {
  const g = sw[kind];
  if (!g || g.id !== id) return;
  delete sw[kind];
  if (Date.now() < multiUntil) return;
  const dx = x - g.x, dy = y - g.y, dt = Date.now() - g.at;
  if (Math.abs(dx) < 12 && Math.abs(dy) < 12 && dt < 350) {
    if (Date.now() - lastTap < 400) return;
    lastTap = Date.now();
    if (isVideo()) toggle();
    emit("kbar");
    return;
  }
  if (Math.abs(dx) < 50 || Math.abs(dx) < Math.abs(dy) * 1.2 || Date.now() - lastSwipe < 450) return;
  lastSwipe = Date.now();
  emit("swipe-item", dx < 0 ? 1 : -1); // doleva = další (jako v Kameře / Fotkách)
}
document.addEventListener("touchstart", (e) => {
  const t = e.changedTouches[0];
  if (e.touches.length > 1) return cancelGesture();
  if (!t || t.touchType === "stylus" || !inStage(e.target)) { delete sw.t; return; }
  sw.t = { id: t.identifier, x: t.clientX, y: t.clientY, at: Date.now() };
}, { passive: true, capture: true });
document.addEventListener("touchmove", (e) => {
  if (e.touches.length > 1 || (sw.t && inStage(e.target))) e.preventDefault(); // žádné přibližování stránky
}, { passive: false, capture: true });
document.addEventListener("touchend", (e) => { for (const t of e.changedTouches) gestureEnd("t", t.identifier, t.clientX, t.clientY); }, { passive: true, capture: true });
document.addEventListener("touchcancel", () => { delete sw.t; }, { capture: true });
document.addEventListener("pointerdown", (e) => {
  if (e.pointerType !== "touch") return;
  touchPointers.add(e.pointerId);
  if (touchPointers.size > 1) return cancelGesture();
  if (inStage(e.target)) sw.p = { id: e.pointerId, x: e.clientX, y: e.clientY, at: Date.now() };
}, true);
document.addEventListener("pointerup", (e) => { if (e.pointerType !== "touch") return; touchPointers.delete(e.pointerId); gestureEnd("p", e.pointerId, e.clientX, e.clientY); }, true);
document.addEventListener("pointercancel", (e) => { if (e.pointerType === "touch") { touchPointers.delete(e.pointerId); delete sw.p; } }, true);
if (isTouch) for (const ev of ["gesturestart", "gesturechange", "gestureend"]) document.addEventListener(ev, (e) => e.preventDefault(), { passive: false });
