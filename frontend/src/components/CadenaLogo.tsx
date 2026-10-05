import { useEffect, useRef } from 'react'

// CadenaLogo — the full Cadena animated logo sequence, ported verbatim into a
// self-contained auto-looping React/canvas component (7 animations, ~24s loop,
// transparent background). Only the surrounding structure (useRef/useEffect/
// canvas/ResizeObserver/RAF) is new; the drawing math, colours, geometry and
// timing are copied exactly from the source HTML.

interface Poly { f: number; ci: number; p: number[][] }
interface Penrose { polys: Poly[]; w: number; h: number; apexOff: number }
interface Face { f: number; ci: number; p: number[][]; c: number[] }

export default function CadenaLogo() {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const cvEl = ref.current
    if (!cvEl) return
    const ctxEl = cvEl.getContext('2d')
    if (!ctxEl) return
    const cv: HTMLCanvasElement = cvEl
    const ctx: CanvasRenderingContext2D = ctxEl

    /* ---------- ported verbatim ---------- */
    const TAU = Math.PI * 2, R3 = Math.sqrt(3) / 2, WS = 1080;   /* square world, scaled to fit the screen */
    const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v)), prog = (t: number, a: number, b: number) => clamp((t - a) / (b - a)), lerp = (a: number, b: number, x: number) => a + (b - a) * x;
    const eio = (x: number) => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2, eout = (x: number) => 1 - Math.pow(1 - x, 3), ein = (x: number) => x * x * x, sio = (x: number) => (1 - Math.cos(Math.PI * x)) / 2;
    const back = (x: number, c1 = 1.6) => { const c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };
    const bump = (x: number, c: number, w: number) => Math.exp(-Math.pow((x - c) / w, 2));
    let seed = 9; const rnd = () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
    const GREEN = ["#28e09c", "#16695b", "#279e88"];

    /* ---------- Penrose triangle: isometric cube chain, first cube drawn last ---------- */
    function penrose(n: number, S: number): Penrose {
      const c30 = Math.cos(Math.PI / 6), P = (x: number, y: number, z: number): number[] => [(x - y) * c30 * S, ((x + y) / 2 - z) * S];
      const cubes: number[][] = []; for (let i = 0; i < n; i++) cubes.push([i, 0, 0]); for (let j = 0; j < n; j++) cubes.push([n, j, 0]); for (let k = 0; k < n; k++) cubes.push([n, n, k]);
      const order = cubes.slice(1).concat([cubes[0]]), polys: Poly[] = [];
      order.forEach(([x, y, z]) => {
        const ci = cubes.findIndex(c => c[0] === x && c[1] === y && c[2] === z);
        polys.push({ f: 0, ci, p: [P(x, y, z + 1), P(x + 1, y, z + 1), P(x + 1, y + 1, z + 1), P(x, y + 1, z + 1)] });
        polys.push({ f: 1, ci, p: [P(x + 1, y, z), P(x + 1, y + 1, z), P(x + 1, y + 1, z + 1), P(x + 1, y, z + 1)] });
        polys.push({ f: 2, ci, p: [P(x, y + 1, z), P(x + 1, y + 1, z), P(x + 1, y + 1, z + 1), P(x, y + 1, z + 1)] });
      });
      polys.forEach(o => o.p = o.p.map(([x, y]): number[] => [y, -x]));
      const all = polys.flatMap(o => o.p), minY = Math.min(...all.map(p => p[1])), maxY = Math.max(...all.map(p => p[1])), minX = Math.min(...all.map(p => p[0])), maxX = Math.max(...all.map(p => p[0]));
      const apex = all.find(p => Math.abs(p[1] - minY) < 1e-6) as number[], cx = apex[0], cy = minY + (maxY - minY) * 2 / 3;
      polys.forEach(o => o.p = o.p.map(([x, y]): number[] => [x - cx, y - cy]));
      return { polys, w: maxX - minX, h: maxY - minY, apexOff: minY - cy };
    }
    const N = 4, unit = penrose(N, 1), LOGO_H = 430, KC = 3, L = LOGO_H / (unit.h * KC), TH = L * R3;
    const BIG = penrose(N, L * KC);
    const apexX = WS / 2, apexY = Math.round(WS / 2 - BIG.h / 2), BX = apexX, BY = apexY - BIG.apexOff;
    const FACES: Face[] = BIG.polys.map(o => { const p = o.p.map(([x, y]): number[] => [x + BX, y + BY]); return { f: o.f, ci: o.ci, p, c: [p.reduce((s, q) => s + q[0], 0) / 4, p.reduce((s, q) => s + q[1], 0) / 4] }; });
    /* convex hull of the mark, for rings */
    const HULL = (function () { const pts = FACES.flatMap(o => o.p).map(p => [Math.round(p[0] * 100) / 100, Math.round(p[1] * 100) / 100]).sort((a, b) => a[0] - b[0] || a[1] - b[1]); const cr = (o: number[], a: number[], b: number[]) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]); const lo: number[][] = [], up: number[][] = []; for (const p of pts) { while (lo.length >= 2 && cr(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); } for (let i = pts.length - 1; i >= 0; i--) { const p = pts[i]; while (up.length >= 2 && cr(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); } return lo.slice(0, -1).concat(up.slice(0, -1)); })();
    const inPoly = (px: number, py: number, p: number[][]) => { let c = false; for (let i = 0, j = p.length - 1; i < p.length; j = i++) { const [xi, yi] = p[i], [xj, yj] = p[j]; if (((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi)) c = !c; } return c; };

    const path = (p: number[][]) => { ctx.beginPath(); p.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath(); };
    function face(o: Face, fill: string, alpha: number) { if (alpha <= 0) return; ctx.globalAlpha = Math.min(1, alpha); path(o.p); ctx.fillStyle = fill; ctx.fill(); ctx.strokeStyle = fill; ctx.lineWidth = 1.2; ctx.lineJoin = "round"; ctx.stroke(); ctx.globalAlpha = 1; }
    function logo(alpha = 1, glow = 0) {
      if (alpha <= 0) return; ctx.save();
      if (glow > 0) { ctx.shadowColor = "rgba(40,224,156," + (0.55 * glow) + ")"; ctx.shadowBlur = 60 * glow; }
      FACES.forEach(o => face(o, GREEN[o.f], alpha)); ctx.restore();
    }
    function around(sc: number, rot: number, fn: () => void) { ctx.save(); ctx.translate(BX, BY); if (rot) ctx.rotate(rot); ctx.scale(sc, sc); ctx.translate(-BX, -BY); fn(); ctx.restore(); }

    /* small Penrose sprites for the tessellation */
    const SM = penrose(3, 30), SPR = 192, PAL: Record<string, string[]> = { dim: ["#24605a", "#163436", "#1d4846"], full: GREEN, f0: ["#5cf0bb", "#28e09c", "#3fe8a9"], f1: ["#1c8270", "#0f4c42", "#16695b"], f2: ["#30b59a", "#1d7766", "#279e88"] }, SPRITES: Record<string, { c: HTMLCanvasElement; k: number }> = {};
    for (const k in PAL) { const c = document.createElement("canvas"); c.width = c.height = SPR; const g = c.getContext("2d")!; const sc = SPR / (SM.h * 1.25); g.translate(SPR / 2, SPR / 2); g.scale(sc, sc); SM.polys.forEach(o => { g.beginPath(); o.p.forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y)); g.closePath(); g.fillStyle = PAL[k][o.f]; g.fill(); }); SPRITES[k] = { c, k: SPR / (SM.w * sc) }; }
    function sprite(key: string, x: number, y: number, rot: number, w: number, a: number) { if (a <= 0.003 || w <= 0.5) return; const s = SPRITES[key], size = w * s.k; ctx.save(); ctx.globalAlpha = Math.min(1, a); ctx.translate(x, y); ctx.rotate(rot); ctx.drawImage(s.c, -size / 2, -size / 2, size, size); ctx.restore(); }

    /* lattice cells around the mark (cube edge = 3 cells, so faces align) */
    const CELLS: { x: number; y: number; up: boolean; f: number; ci: number; d: number }[] = [];
    for (let r = -14; r <= Math.ceil(BIG.h / TH) + 14; r++) {
      const rowY = apexY + r * TH, shift = (((r % 2) + 2) % 2) * L / 2;
      for (let k = -40; k <= 40; k++) {
        const x = apexX + shift + k * L / 2, up = (((k % 2) + 2) % 2) === 0, y = rowY + (up ? TH * 2 / 3 : TH / 3), d = Math.hypot(x - BX, y - BY);
        if (d > 500) continue;
        let f = -1, ci = -1; for (const o of FACES) if (inPoly(x, y, o.p)) { f = o.f; ci = o.ci; }
        CELLS.push({ x, y, up, f, ci, d });
      }
    }

    /* ======================= the seven animations: u runs 0..1, both ends are the plain logo ======================= */

    /* 1. Blueprint: fill drains to white line work, construction lines sweep, faces refill along the chain */
    function blueprint(u: number) {
      const drain = prog(u, 0.02, 0.2), guides = Math.sin(Math.PI * prog(u, 0.14, 0.92)), glow = bump(u, 0.97, 0.05);
      if (guides > 0.01) {
        ctx.save(); ctx.strokeStyle = "#28e09c"; ctx.lineWidth = 1; ctx.globalAlpha = 0.35 * guides; ctx.setLineDash([6, 8]);
        const ext = 640 * eio(prog(u, 0.14, 0.42));
        const verts = [...new Set(FACES.flatMap(o => o.p).map(p => Math.round(p[0]) + "," + Math.round(p[1])))].map(s => s.split(",").map(Number));
        const dirs = [[1, 0], [0.5, R3], [0.5, -R3]];
        for (const [vx, vy] of verts.filter((v, i) => i % 2 === 0)) for (const [dx, dy] of dirs) { ctx.beginPath(); ctx.moveTo(vx - dx * ext, vy - dy * ext); ctx.lineTo(vx + dx * ext, vy + dy * ext); ctx.stroke(); }
        ctx.setLineDash([]); ctx.globalAlpha = 0.9 * guides; ctx.fillStyle = "#28e09c";
        for (const [vx, vy] of verts) { ctx.beginPath(); ctx.arc(vx, vy, 2.6, 0, TAU); ctx.fill(); }
        ctx.restore();
      }
      ctx.save(); if (glow > 0.01) { ctx.shadowColor = "rgba(40,224,156," + (0.5 * glow) + ")"; ctx.shadowBlur = 50; }
      FACES.forEach(o => {
        const st = 0.52 + o.ci / 11 * 0.32, refill = eio(prog(u, st, st + 0.08));
        const fillA = u < 0.5 ? 1 - drain : refill;
        face(o, GREEN[o.f], fillA);
        const lineA = (u < 0.5 ? drain : 1) * (1 - refill);
        if (lineA > 0.01) { ctx.globalAlpha = lineA; path(o.p); ctx.strokeStyle = "#279e88"; ctx.lineWidth = 2.2; ctx.lineJoin = "round"; ctx.stroke(); ctx.globalAlpha = 1; }
      });
      ctx.restore();
      /* pen tip runs the chain while refilling */
      if (u > 0.52 && u < 0.92) { const ci = clamp((u - 0.52) / 0.32) * 11, o = FACES.find(q => q.ci === Math.round(ci) && q.f === 0); if (o) { ctx.fillStyle = "#28e09c"; ctx.beginPath(); ctx.arc(o.c[0], o.c[1], 7, 0, TAU); ctx.fill(); } }
    }

    /* 2. Pulse: heartbeat with triangular shock rings */
    function pulse(u: number) {
      const beats = [0.12, 0.3, 0.6];
      let s = 0; beats.forEach((b, i) => { s += bump(u, b, 0.045) * (i === 2 ? 1.4 : 1); });
      around(1 + 0.07 * s, 0, () => logo(1, clamp(s)));
      beats.forEach((b, i) => {
        for (let r = 0; r < (i === 2 ? 3 : 1); r++) {
          const q = prog(u, b + r * 0.06, b + r * 0.06 + 0.42); if (q <= 0 || q >= 1) continue;
          ctx.save(); ctx.translate(BX, BY); const sc = 1 + q * (i === 2 ? 1.3 : 0.8); ctx.scale(sc, sc); ctx.translate(-BX, -BY);
          path(HULL); ctx.strokeStyle = "#28e09c"; ctx.globalAlpha = (1 - q) * (i === 2 ? 0.8 : 0.55); ctx.lineWidth = 3 / sc; ctx.stroke(); ctx.restore();
        }
      });
    }

    /* 3. Tessellate: the mark breaks into small Penrose tiles, the field grows around it, ripples, folds back */
    function tessellate(u: number) {
      const toTiles = eio(prog(u, 0, 0.14)), toSolid = eio(prog(u, 0.86, 1));
      const grow = eout(prog(u, 0.1, 0.4)), shrink = ein(prog(u, 0.62, 0.86));
      const MW = L * 0.8;
      for (const c of CELLS) {
        const dd = c.d / 500, base = c.up ? 0 : Math.PI;
        const wv = eio(prog(u, 0.3 + dd * 0.18, 0.3 + dd * 0.18 + 0.16)), rot = base + wv * TAU / 3, flash = Math.sin(wv * Math.PI);
        if (c.f >= 0) {
          const a = toTiles * (1 - toSolid);
          sprite("f" + c.f, c.x, c.y, rot, MW, a);
          if (flash > 0) sprite("full", c.x, c.y, rot, MW, flash * a * 0.8);
        } else {
          const appear = clamp(grow * 1.6 - dd * 0.9), vanish = clamp(shrink * 1.6 - (1 - dd) * 0.6), vis = appear * (1 - vanish);
          if (vis <= 0.01) continue;
          const fade = Math.pow(1 - dd, 1.1);
          sprite(c.up ? "f2" : "f1", c.x, c.y, rot, MW * vis, fade * 0.85);
          if (flash > 0) sprite("f0", c.x, c.y, rot, MW * vis, flash * fade);
        }
      }
      logo(Math.max(1 - toTiles, toSolid), bump(u, 0.98, 0.05));
    }

    /* 4. Exploded: faces burst out along their normals, hang, and snap back */
    const EXP = (seed = 31, FACES.map(o => { const n = o.f === 0 ? [0, -1] : o.f === 1 ? [R3, 0.5] : [-R3, 0.5], dx = o.c[0] - BX, dy = o.c[1] - BY, d = Math.hypot(dx, dy) || 1, m = 90 + rnd() * 110; return { ox: dx / d * m + n[0] * 80, oy: dy / d * m + n[1] * 80, rot: (rnd() - 0.5) * 1.6, dl: o.ci / 11 * 0.08 }; }));
    function exploded(u: number) {
      FACES.forEach((o, i) => {
        const e = EXP[i], out = eout(prog(u, 0.02 + e.dl, 0.3 + e.dl)), inn = back(prog(u, 0.55 + e.dl, 0.88 + e.dl), 1.8), k = out * (1 - inn) + (u > 0.5 ? 0 : 0);
        const drift = Math.sin((u - 0.3) * 9 + i) * 0.06 * out * (1 - inn);
        ctx.save(); ctx.translate(o.c[0] + e.ox * (k + drift), o.c[1] + e.oy * (k + drift)); ctx.rotate(e.rot * k); ctx.translate(-o.c[0], -o.c[1]);
        face(o, GREEN[o.f], 1);
        const lock = bump(prog(u, 0.55 + e.dl, 0.88 + e.dl), 0.62, 0.08); if (lock > 0.02 && u > 0.55) { ctx.globalAlpha = lock * 0.7; path(o.p); ctx.fillStyle = "#ccfff0"; ctx.fill(); ctx.globalAlpha = 1; }
        ctx.restore();
      });
    }

    /* 5. Lock: the three bars slide apart on their own axes, then slam together */
    const BARS = [0, 1, 2].map(b => { const fs = FACES.filter(o => Math.floor(o.ci / N) === b); const cx = fs.reduce((s, o) => s + o.c[0], 0) / fs.length, cy = fs.reduce((s, o) => s + o.c[1], 0) / fs.length, d = Math.hypot(cx - BX, cy - BY); return { ux: (cx - BX) / d, uy: (cy - BY) / d }; });
    function lock(u: number) {
      const k = BARS.map((b, i) => { const out = eout(prog(u, 0.03 + i * 0.05, 0.3 + i * 0.05)), inn = back(prog(u, 0.58 + i * 0.04, 0.8 + i * 0.04), 2.2); return 120 * out * (1 - inn); });
      const imp = Math.max(...[0, 1, 2].map(i => bump(u, 0.74 + i * 0.04, 0.02)));
      ctx.save(); ctx.translate(Math.sin(u * 400) * imp * 7, Math.cos(u * 330) * imp * 5);
      /* speed lines while slamming */
      BARS.forEach((b, i) => { const m = k[i]; if (u < 0.55 || m < 4) return; ctx.save(); ctx.strokeStyle = "#28e09c"; ctx.lineWidth = 2; ctx.globalAlpha = 0.5; for (let s = -2; s <= 2; s++) { const px = -b.uy * s * 30, py = b.ux * s * 30, ox = BX + b.ux * (m + 230) + px, oy = BY + b.uy * (m + 230) + py; ctx.beginPath(); ctx.moveTo(ox, oy); ctx.lineTo(ox + b.ux * m * 0.9, oy + b.uy * m * 0.9); ctx.stroke(); } ctx.restore(); });
      FACES.forEach(o => { const b = Math.floor(o.ci / N), B = BARS[b]; ctx.save(); ctx.translate(B.ux * k[b], B.uy * k[b]); face(o, GREEN[o.f], 1); ctx.restore(); });
      ctx.restore();
      if (imp > 0.02) { ctx.save(); ctx.globalAlpha = imp * 0.6; FACES.forEach(o => { if (o.ci % N === 0) { path(o.p); ctx.fillStyle = "#ccfff0"; ctx.fill(); } }); ctx.restore(); }
      if (u > 0.8) logo(0, bump(u, 0.9, 0.06));
      const g = bump(u, 0.9, 0.06); if (g > 0.02) { ctx.save(); ctx.shadowColor = "rgba(40,224,156," + (0.5 * g) + ")"; ctx.shadowBlur = 50; FACES.forEach(o => face(o, GREEN[o.f], g * 0.4)); ctx.restore(); }
    }

    /* 6. Halftone: the mark dissolves into dots, a ripple runs through, dots merge back */
    const DOTS = (function () { const sp = 13, out: { x: number; y: number; f: number; d: number }[] = []; for (let r = 0, y = BY - 520; y < BY + 520; y += sp * R3, r++) for (let x = BX - 520 + (r % 2) * sp / 2; x < BX + 520; x += sp) { const d = Math.hypot(x - BX, y - BY); if (d > 500) continue; let f = -1; for (const o of FACES) if (inPoly(x, y, o.p)) f = o.f; out.push({ x, y, f, d }); } return { sp, out }; })();
    function halftone(u: number) {
      const sp = DOTS.sp, toDots = eio(prog(u, 0, 0.18)), toSolid = eio(prog(u, 0.84, 1));
      const front = lerp(0, 520, prog(u, 0.2, 0.75)), field = Math.sin(Math.PI * prog(u, 0.15, 0.8));
      const buckets: number[][] = [[], [], [], []];
      for (const d of DOTS.out) {
        const ring = bump(d.d, front, 40);
        if (d.f >= 0) {
          const r = lerp(sp * 0.66, sp * 0.36, toDots * (1 - toSolid)) + ring * sp * 0.2;
          buckets[d.f].push(d.x, d.y, r);
        } else {
          const r = (1.6 + ring * 5) * field * Math.pow(1 - d.d / 500, 0.7);
          if (r > 0.3) buckets[3].push(d.x, d.y, r);
        }
      }
      const cols = [...GREEN, "#28e09c"];
      buckets.forEach((b, i) => { ctx.fillStyle = cols[i]; ctx.globalAlpha = i === 3 ? 0.55 : 1; ctx.beginPath(); for (let j = 0; j < b.length; j += 3) { ctx.moveTo(b[j] + b[j + 2], b[j + 1]); ctx.arc(b[j], b[j + 1], b[j + 2], 0, TAU); } ctx.fill(); });
      ctx.globalAlpha = 1;
      logo(Math.max(1 - toDots, toSolid), bump(u, 0.97, 0.05));
    }

    /* 7. Chain: light and a lift wave run around the impossible loop, twice */
    function chain(u: number) {
      const runs = 2, pos = eio(prog(u, 0.04, 0.92)) * 12 * runs;
      const lift = (ci: number) => { let v = 0; for (let k = -1; k <= runs; k++) v = Math.max(v, bump(ci + 12 * k, pos - 0.5, 1.1)); return v * Math.sin(Math.PI * prog(u, 0.02, 0.96)); };
      ctx.save();
      const g = bump(u, 0.5, 0.4); ctx.shadowColor = "rgba(40,224,156," + (0.35 * g) + ")"; ctx.shadowBlur = 40;
      FACES.forEach(o => { const l = lift(o.ci); ctx.save(); ctx.translate(0, -l * 22); face(o, GREEN[o.f], 1); if (l > 0.05) { ctx.globalAlpha = l * 0.65; path(o.p); ctx.fillStyle = "#ccfff0"; ctx.fill(); } ctx.restore(); });
      ctx.restore();
    }

    const SEGS: [string, number, (u: number) => void][] = [["Blueprint", 3.4, blueprint], ["Pulse", 2.6, pulse], ["Tessellate", 3.6, tessellate], ["Exploded", 2.8, exploded], ["Lock", 2.6, lock], ["Halftone", 3.2, halftone], ["Chain", 3.0, chain]];
    const HOLD = 0.45;
    const STARTS: number[] = []; let TOTAL = 0; SEGS.forEach(s => { STARTS.push(TOTAL); TOTAL += s[1] + HOLD; });

    function frame(t: number) {
      const k = cv.width / VWpx; ctx.setTransform(k, 0, 0, k, 0, 0); ctx.clearRect(0, 0, VWpx, VHpx);
      /* fit the square world into the screen */
      const sc = Math.min(VWpx, VHpx) / WS; ctx.translate((VWpx - WS * sc) / 2, (VHpx - WS * sc) / 2); ctx.scale(sc, sc);
      let i = SEGS.length - 1; for (let j = 0; j < SEGS.length; j++) if (t < STARTS[j] + SEGS[j][1] + HOLD) { i = j; break; }
      const lt = t - STARTS[i], [name, dur, fn] = SEGS[i];
      if (lt < dur) fn(clamp(lt / dur)); else logo(1, 0);
      /* feather everything out to fully transparent well inside the edge */
      ctx.save(); ctx.globalCompositeOperation = "destination-in";
      const g = ctx.createRadialGradient(WS / 2, WS / 2, WS * 0.4, WS / 2, WS / 2, WS * 0.5);
      g.addColorStop(0, "rgba(0,0,0,1)"); g.addColorStop(0.55, "rgba(0,0,0,0.6)"); g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = g; ctx.fillRect(-WS * 4, -WS * 4, WS * 9, WS * 9); ctx.restore();
      return i;
    }

    /* ---------- autoplay ---------- */
    let VWpx = 0, VHpx = 0;
    function resize() { const r = cv.getBoundingClientRect(), d = Math.min(window.devicePixelRatio || 1, 2); VWpx = r.width || 1; VHpx = r.height || 1; cv.width = Math.round(VWpx * d); cv.height = Math.round(VHpx * d); }
    let ro: ResizeObserver | null = null;
    if (window.ResizeObserver) { ro = new ResizeObserver(resize); ro.observe(cv); } else window.addEventListener("resize", resize);
    resize();
    const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const start = performance.now();
    let raf = 0, cancelled = false;
    function loop(now: number) { frame(((now - start) / 1000) % TOTAL); if (!cancelled) raf = requestAnimationFrame(loop); }
    if (reduce) frame(STARTS[1] - HOLD / 2); else raf = requestAnimationFrame(loop);

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      if (ro) ro.disconnect(); else window.removeEventListener("resize", resize);
    };
    // name is destructured for fidelity with the source frame() segment selection
  }, [])

  return (
    <div style={{ position: 'relative', width: '100%', aspectRatio: '1 / 1' }}>
      <canvas
        ref={ref}
        role="img"
        aria-label="Cadena logo"
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block' }}
      />
    </div>
  )
}
