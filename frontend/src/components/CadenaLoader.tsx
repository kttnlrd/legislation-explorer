import { useEffect, useRef, useState } from 'react'

// CadenaLoader — the FINAL Cadena loading screen, ported verbatim from the
// standalone HTML into a self-contained React/canvas component. The drawing
// math, palettes, sprites, timing (cfg) and geometry are copied exactly; only
// the surrounding structure (useEffect/useRef/canvas/RAF/resize/done-prop) is
// new. The canvas is itself the full-screen overlay: no outer wrapper div.

type Pt = [number, number]
interface Poly { f: number; ci: number; p: Pt[] }
interface Penrose { polys: Poly[]; w: number; h: number; apexOff: number }
interface Tile { x: number; y: number; up: boolean; face: number; ci: number; d: number; rnd: number; tgt?: Tile }

export default function CadenaLoader({ done }: { done: boolean }) {
  const ref = useRef<HTMLCanvasElement>(null)
  // The loop's `stopped` flag. Lives in a ref so the effect's RAF loop can read
  // it and the `done` effect can flip it.
  const stoppedRef = useRef(false)
  const [hidden, setHidden] = useState(false)

  useEffect(() => {
    // React StrictMode (dev) mounts, unmounts, then remounts the effect; the
    // cleanup below sets stoppedRef true, so reset it on each setup.
    stoppedRef.current = false
    const cvEl = ref.current
    if (!cvEl) return
    const ctxEl = cvEl.getContext('2d')
    if (!ctxEl) return
    const cv: HTMLCanvasElement = cvEl
    const ctx: CanvasRenderingContext2D = ctxEl

    /* ---------- ported verbatim from the HTML ---------- */
    const TAU = Math.PI * 2, R3 = Math.sqrt(3) / 2;
    /* Timing in seconds. Loop = pattern, collapse into the triangle, hold, then a fade back to the pattern. */
    const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v)), prog = (t: number, a: number, b: number) => b <= a ? (t >= b ? 1 : 0) : clamp((t - a) / (b - a)), lerp = (a: number, b: number, x: number) => a + (b - a) * x;
    const eio = (x: number) => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2, eout = (x: number) => 1 - Math.pow(1 - x, 3), ein = (x: number) => x * x * x;
    const cfg = { P: 1.05, T: 0.95, H: 1.35, F: 0.30, S: 0.25 };   /* S = triangle height as a share of the shorter screen side */

    /* Penrose triangle from an isometric cube chain, first cube drawn last */
    function penrose(n: number, S: number): Penrose {
      const c30 = Math.cos(Math.PI / 6), P = (x: number, y: number, z: number): Pt => [(x - y) * c30 * S, ((x + y) / 2 - z) * S];
      const cubes: number[][] = []; for (let i = 0; i < n; i++) cubes.push([i, 0, 0]); for (let j = 0; j < n; j++) cubes.push([n, j, 0]); for (let k = 0; k < n; k++) cubes.push([n, n, k]);
      const order = cubes.slice(1).concat([cubes[0]]), polys: Poly[] = [];
      order.forEach(([x, y, z]) => {
        const ci = cubes.findIndex(c => c[0] === x && c[1] === y && c[2] === z);
        polys.push({ f: 0, ci, p: [P(x, y, z + 1), P(x + 1, y, z + 1), P(x + 1, y + 1, z + 1), P(x, y + 1, z + 1)] });
        polys.push({ f: 1, ci, p: [P(x + 1, y, z), P(x + 1, y + 1, z), P(x + 1, y + 1, z + 1), P(x + 1, y, z + 1)] });
        polys.push({ f: 2, ci, p: [P(x, y + 1, z), P(x + 1, y + 1, z), P(x + 1, y + 1, z + 1), P(x, y + 1, z + 1)] });
      });
      polys.forEach(o => o.p = o.p.map(([x, y]): Pt => [y, -x]));
      const all = polys.flatMap(o => o.p), minY = Math.min(...all.map(p => p[1])), maxY = Math.max(...all.map(p => p[1])), minX = Math.min(...all.map(p => p[0])), maxX = Math.max(...all.map(p => p[0]));
      const apex = all.find(p => Math.abs(p[1] - minY) < 1e-6) as Pt, cx = apex[0], cy = minY + (maxY - minY) * 2 / 3;
      polys.forEach(o => o.p = o.p.map(([x, y]): Pt => [x - cx, y - cy]));
      return { polys, w: maxX - minX, h: maxY - minY, apexOff: minY - cy };
    }
    const PAL: Record<string, string[]> = { full: ["#28e09c", "#16695b", "#279e88"], dim: ["#24605a", "#163436", "#1d4846"], f0: ["#5cf0bb", "#28e09c", "#3fe8a9"], f1: ["#1c8270", "#0f4c42", "#16695b"], f2: ["#30b59a", "#1d7766", "#279e88"] };
    const small = penrose(3, 30), SPR = 256, sprites: Record<string, { c: HTMLCanvasElement; k: number }> = {};
    for (const k in PAL) { const c = document.createElement("canvas"); c.width = c.height = SPR; const g = c.getContext("2d") as CanvasRenderingContext2D; const sc = SPR / (small.h * 1.25); g.translate(SPR / 2, SPR / 2); g.scale(sc, sc); small.polys.forEach(o => { g.beginPath(); o.p.forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y)); g.closePath(); g.fillStyle = PAL[k][o.f]; g.fill(); }); sprites[k] = { c, k: SPR / (small.w * sc) }; }

    let VW = 0, VH = 0, L = 0, tiles: Tile[] = [], bigPolys: Poly[] = [], BX = 0, BY = 0, MW = 0, maxD = 1;
    function build() {
      const r = cv.getBoundingClientRect(), d = Math.min(window.devicePixelRatio || 1, 2);
      VW = r.width; VH = r.height; cv.width = Math.round(VW * d); cv.height = Math.round(VH * d); ctx.setTransform(d, 0, 0, d, 0, 0);
      /* big mark: n=4 cubes per bar, cube edge = 3 cells, so its faces sit exactly on the tile grid */
      const unit = penrose(4, 1), mn = Math.min(VW, VH), mx = Math.max(VW, VH);
      const target = clamp(mx / 34, 22, 54);                       /* tile size suits both phone and desktop */
      const kc = Math.max(1, Math.round((mn * cfg.S) / (unit.h * target)));  /* cells per cube edge */
      L = (mn * cfg.S) / (unit.h * kc);
      const TH = L * R3, big = penrose(4, L * kc);
      const apexX = VW / 2, apexY = Math.round(VH / 2 - big.h / 2); BX = apexX; BY = apexY - big.apexOff;
      bigPolys = big.polys.map(o => ({ f: o.f, ci: o.ci, p: o.p.map(([x, y]): Pt => [x + BX, y + BY]) }));
      const inPoly = (px: number, py: number, p: Pt[]) => { let c = false; for (let i = 0, j = p.length - 1; i < p.length; j = i++) { const [xi, yi] = p[i], [xj, yj] = p[j]; if (((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi)) c = !c; } return c; };
      tiles = [];
      for (let r2 = Math.floor(-apexY / TH) - 2; r2 <= Math.ceil((VH - apexY) / TH) + 2; r2++) {
        const rowY = apexY + r2 * TH, shift = (((r2 % 2) + 2) % 2) * L / 2;
        for (let k = Math.floor(-VW / L) - 4; k <= Math.ceil(VW / L) + 4; k++) {
          const x = apexX + shift + k * L / 2, up = (((k % 2) + 2) % 2) === 0, y = rowY + (up ? TH * 2 / 3 : TH / 3);
          if (x < -L || x > VW + L || y < -L || y > VH + L) continue;
          let face = -1, ci = -1; for (const o of bigPolys) if (inPoly(x, y, o.p)) { face = o.f; ci = o.ci; }
          tiles.push({ x, y, up, face, ci, d: Math.hypot(x - BX, y - BY), rnd: ((k * 73856093) ^ (r2 * 19349663)) >>> 0 });
        }
      }
      maxD = Math.max(...tiles.map(t => t.d));
      const inside = tiles.filter(t => t.face >= 0);
      tiles.forEach(t => { if (t.face < 0) t.tgt = inside[t.rnd % inside.length]; });
      MW = L * 0.80;
    }
    function sprite(key: string, x: number, y: number, rot: number, w: number, a: number) { if (a <= 0.003 || w <= 0.5) return; const s = sprites[key], size = w * s.k; ctx.save(); ctx.globalAlpha = Math.min(1, a); ctx.translate(x, y); ctx.rotate(rot); ctx.drawImage(s.c, -size / 2, -size / 2, size, size); ctx.restore(); }
    function solid(alpha: number, glow: number) {
      if (alpha <= 0) return; ctx.save(); ctx.globalAlpha = alpha;
      if (glow > 0) { ctx.shadowColor = "rgba(40,224,156," + (0.35 * glow) + ")"; ctx.shadowBlur = L * 1.2; }
      bigPolys.forEach(o => { ctx.beginPath(); o.p.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath(); ctx.fillStyle = PAL.full[o.f]; ctx.fill(); ctx.strokeStyle = PAL.full[o.f]; ctx.lineWidth = 1; ctx.stroke(); });
      ctx.restore();
    }

    /* one loop: [0,P) full pattern, [P,P+T) collapse, [P+T,E) solid triangle, [E,E+F) triangle fades as the pattern fades back in */
    function frame(t: number) {
      const P = cfg.P, T = cfg.T, H = cfg.H, F = cfg.F, E = P + T + H;
      ctx.fillStyle = "#0a1214"; ctx.fillRect(0, 0, VW, VH);
      const tc = t - P, fade = t >= E ? eio(prog(t - E, 0, F)) : 0;  /* 0 -> 1 across the fade */
      let sol: number;
      if (t < P) sol = 0; else if (t < P + T) sol = eio(prog(tc, T * 0.6, T)); else sol = 1;
      const glow = (t >= P + T && t < E) ? Math.sin(Math.PI * prog(t, P + T, E)) : 0;
      const span = Math.max(0.05, P - 0.05);
      for (const tl of tiles) {
        const dd = tl.d / maxD, base = tl.up ? 0 : Math.PI;
        const w0 = 0.05 + dd * span * 0.6, w = eio(prog(t, w0, w0 + span * 0.4));
        const rot = base + w * TAU / 3, flash = t < P ? Math.sin(w * Math.PI) : 0;
        if (tl.face < 0) {
          let g: number;
          if (t < P) g = 0;
          else if (t < P + T) g = ein(prog(tc, (1 - dd) * T * 0.4, (1 - dd) * T * 0.4 + T * 0.6));   /* far tiles fly in first */
          else if (t < E) g = 1;
          else g = 0;   /* during the fade the pattern is back at rest, faded in below */
          const x = lerp(tl.x, (tl.tgt as Tile).x, g), y = lerp(tl.y, (tl.tgt as Tile).y, g), sc = 1 - 0.75 * g, al = g < 0.85 ? 1 : 1 - (g - 0.85) / 0.15;
          const pa = t >= E ? fade : 1;
          sprite("dim", x, y, rot + g * TAU / 3, MW * sc, al * pa);
          if (flash > 0) sprite("full", x, y, rot, MW * sc, flash * al);
        } else {
          let tn: number;
          if (t < P) tn = 0; else if (t < P + T) tn = eio(prog(tc, 0, T * 0.7)); else if (t < E) tn = 1; else tn = 0;
          if (t >= E) { sprite("dim", tl.x, tl.y, rot, MW, fade); continue; }
          sprite("dim", tl.x, tl.y, rot, MW, (1 - sol) * (1 - tn));
          sprite("f" + tl.face, tl.x, tl.y, rot, MW, (1 - sol) * tn);
          if (flash > 0) sprite("full", tl.x, tl.y, rot, MW, flash * (1 - sol) * (1 - tn));
        }
      }
      solid(t >= E ? 1 - fade : sol, glow);
    }

    let rz: ReturnType<typeof setTimeout> | undefined; const onR = () => { clearTimeout(rz); rz = setTimeout(build, 120); }; window.addEventListener("resize", onR); window.addEventListener("orientationchange", onR); if (window.visualViewport) window.visualViewport.addEventListener("resize", onR); build();
    (window as unknown as { cadenaRender?: (t: number) => void }).cadenaRender = t => frame(t);
    const start = performance.now();
    const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    function loop(now: number) {
      if (stoppedRef.current) return;
      const Ltot = cfg.P + cfg.T + cfg.H + cfg.F, t = reduce ? cfg.P + cfg.T + 0.01 : ((now - start) / 1000) % Ltot;
      frame(t);
      raf = requestAnimationFrame(loop);
    }
    raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      stoppedRef.current = true;
      clearTimeout(rz);
      window.removeEventListener("resize", onR);
      window.removeEventListener("orientationchange", onR);
      if (window.visualViewport) window.visualViewport.removeEventListener("resize", onR);
      delete (window as unknown as { cadenaRender?: (t: number) => void }).cadenaRender;
    };
  }, [])

  // done -> fade the canvas out, stop the loop, remove it after ~450ms.
  useEffect(() => {
    if (!done) return
    const cv = ref.current
    if (!cv) return
    cv.classList.add('done')
    const id = setTimeout(() => { stoppedRef.current = true; setHidden(true) }, 450)
    return () => clearTimeout(id)
  }, [done])

  if (hidden) return null
  return (
    <>
      <style>{`#loader{transition:opacity .4s ease}#loader.done{opacity:0;pointer-events:none}`}</style>
      <canvas
        ref={ref}
        id="loader"
        role="img"
        aria-label="Loading: Penrose triangle pattern resolving into the Cadena triangle"
        style={{ position: 'fixed', inset: 0, width: '100%', height: '100%', display: 'block', zIndex: 9999 }}
      />
    </>
  )
}
