import { useEffect, useRef } from 'react'

// PenroseLogo — the "Exploded" scene (S1) from the Cadena Triangle Motion Set,
// ported verbatim into a self-contained auto-looping React/canvas component.
// Only the surrounding structure (useEffect/useRef/canvas/RAF/resize) is new;
// the drawing math, colours and timing are copied exactly from the source HTML.

type Pt = [number, number]
interface Poly { f: number; ci: number; p: Pt[] }
interface Penrose { polys: Poly[]; h: number; apexOff: number }
interface Face { f: number; ci: number; p: Pt[]; c: Pt; i: number }

export default function PenroseLogo({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const cvEl = ref.current
    if (!cvEl) return
    const ctxEl = cvEl.getContext('2d')
    if (!ctxEl) return
    const cv: HTMLCanvasElement = cvEl
    const ctx: CanvasRenderingContext2D = ctxEl

    /* ---------- ported verbatim ---------- */
    const W = 1920, H = 1080, TAU = Math.PI * 2, R3 = Math.sqrt(3) / 2
    const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v)), prog = (t: number, a: number, b: number) => clamp((t - a) / (b - a)), lerp = (a: number, b: number, x: number) => a + (b - a) * x
    const eio = (x: number) => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2, eout = (x: number) => 1 - Math.pow(1 - x, 3), eout5 = (x: number) => 1 - Math.pow(1 - x, 5)
    const back = (x: number) => { const c1 = 1.4, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2) }
    /* seeded random so every loop is identical */
    let seed = 7; const rnd = () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646 }
    const GREEN = ["#28e09c", "#16695b", "#279e88"], DIM = "#1d4846"

    /* ---------- Penrose triangle: isometric cube chain, first cube drawn last ---------- */
    function penrose(n: number, S: number): Penrose {
      const c30 = Math.cos(Math.PI / 6), P = (x: number, y: number, z: number): Pt => [(x - y) * c30 * S, ((x + y) / 2 - z) * S]
      const cubes: number[][] = []; for (let i = 0; i < n; i++) cubes.push([i, 0, 0]); for (let j = 0; j < n; j++) cubes.push([n, j, 0]); for (let k = 0; k < n; k++) cubes.push([n, n, k])
      const order = cubes.slice(1).concat([cubes[0]]), polys: Poly[] = []
      order.forEach(([x, y, z]) => {
        const ci = cubes.findIndex(c => c[0] === x && c[1] === y && c[2] === z)
        polys.push({ f: 0, ci, p: [P(x, y, z + 1), P(x + 1, y, z + 1), P(x + 1, y + 1, z + 1), P(x, y + 1, z + 1)] })
        polys.push({ f: 1, ci, p: [P(x + 1, y, z), P(x + 1, y + 1, z), P(x + 1, y + 1, z + 1), P(x + 1, y, z + 1)] })
        polys.push({ f: 2, ci, p: [P(x, y + 1, z), P(x + 1, y + 1, z), P(x + 1, y + 1, z + 1), P(x, y + 1, z + 1)] })
      })
      polys.forEach(o => o.p = o.p.map(([x, y]): Pt => [y, -x]))
      const all = polys.flatMap(o => o.p), minY = Math.min(...all.map(p => p[1])), maxY = Math.max(...all.map(p => p[1]))
      const apex = all.find(p => Math.abs(p[1] - minY) < 1e-6) as Pt, cx = apex[0], cy = minY + (maxY - minY) * 2 / 3
      polys.forEach(o => o.p = o.p.map(([x, y]): Pt => [x - cx, y - cy]))
      return { polys, h: maxY - minY, apexOff: minY - cy }
    }
    /* the big triangle every scene resolves into */
    const L = 54, TH = L * R3, N = 4
    const BG = penrose(N, L * 3)
    const apexX = W / 2, apexY = Math.round(H / 2 - BG.h / 2), BX = apexX, BY = apexY - BG.apexOff
    const FACES: Face[] = BG.polys.map((o, i) => { const p = o.p.map(([x, y]): Pt => [x + BX, y + BY]); const c: Pt = [p.reduce((s, q) => s + q[0], 0) / 4, p.reduce((s, q) => s + q[1], 0) / 4]; return { f: o.f, ci: o.ci, p, c, i } })
    const path = (p: Pt[]) => { ctx.beginPath(); p.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath() }
    function solid(alpha: number, glow: number, scale: number) {
      if (alpha <= 0) return; ctx.save(); ctx.globalAlpha = alpha
      if (scale && scale !== 1) { ctx.translate(BX, BY); ctx.scale(scale, scale); ctx.translate(-BX, -BY) }
      if (glow > 0) { ctx.shadowColor = "rgba(40,224,156," + (0.4 * glow) + ")"; ctx.shadowBlur = 70 }
      FACES.forEach(o => { path(o.p); ctx.fillStyle = GREEN[o.f]; ctx.fill(); ctx.strokeStyle = GREEN[o.f]; ctx.lineWidth = 1.2; ctx.lineJoin = "round"; ctx.stroke() })
      ctx.restore()
    }

    /* ---------- timing: hold, build in, hold the triangle, play it back out ---------- */
    const LOOP = 7, HOLD0 = 0.35, IN = 2.8, HOLD1 = 1.05
    function phase(t: number) {
      if (t < HOLD0) return 0
      if (t < HOLD0 + IN) return (t - HOLD0) / IN
      if (t < HOLD0 + IN + HOLD1) return 1
      return clamp(1 - (t - HOLD0 - IN - HOLD1) / IN)
    }
    const holdGlow = (t: number) => Math.sin(Math.PI * prog(t, HOLD0 + IN - 0.15, HOLD0 + IN + HOLD1 + 0.15))
    const bg = () => { ctx.fillStyle = "#0a1214"; ctx.fillRect(0, 0, W, H) }

    /* ============ 1. EXPLODED: the 36 faces fly in from an exploded view ============ */
    const S1 = (function () {
      seed = 11
      const parts = FACES.map(o => {
        const dx = o.c[0] - BX, dy = o.c[1] - BY, d = Math.hypot(dx, dy) || 1, dist = 260 + rnd() * 340
        const n: Pt = o.f === 0 ? [0, -1] : o.f === 1 ? [R3, 0.5] : [-R3, 0.5]  /* push each face along its own normal */
        return { o, ox: dx / d * dist + n[0] * 220, oy: dy / d * dist * 0.85 + n[1] * 220, rot: (rnd() - 0.5) * 2.4, sc: 0.55 + rnd() * 0.3, delay: o.ci / 11 * 0.36 + rnd() * 0.06 }
      })
      return function (t: number) {
        bg(); const p = phase(t), g = holdGlow(t)
        /* faint isometric dot grid */
        ctx.fillStyle = "#253d3d"; for (let y = TH / 2; y < H; y += TH) for (let x = ((Math.round(y / TH)) % 2) * L / 2; x < W; x += L) { ctx.fillRect(x - 1.2, y - 1.2, 2.4, 2.4) }
        if (p >= 1) { solid(1, g, 1 + 0.012 * g); return }
        parts.forEach(q => {
          const e = back(clamp((p - q.delay) / 0.58)), k = 1 - e
          ctx.save(); ctx.translate(q.o.c[0] + q.ox * k, q.o.c[1] + q.oy * k); ctx.rotate(q.rot * k); ctx.scale(lerp(1, q.sc, k), lerp(1, q.sc, k)); ctx.translate(-q.o.c[0], -q.o.c[1])
          ctx.globalAlpha = clamp(0.35 + e * 0.65); path(q.o.p); ctx.fillStyle = GREEN[q.o.f]; ctx.fill(); ctx.strokeStyle = GREEN[q.o.f]; ctx.lineWidth = 1.2; ctx.stroke()
          const lock = Math.max(0, 1 - Math.abs(clamp((p - q.delay) / 0.55) - 0.92) * 10)
          if (lock > 0) { ctx.globalAlpha = lock * 0.8; ctx.fillStyle = "#ffffff"; ctx.fill() }
          ctx.restore()
        })
      }
    })()

    /* ---------- resize / render loop ---------- */
    function resize() { const r = cv.getBoundingClientRect(), d = Math.min(window.devicePixelRatio || 1, 2); cv.width = Math.round(r.width * d); cv.height = Math.round(r.height * d) }
    window.addEventListener("resize", resize); resize()

    const start = performance.now()
    let raf = 0
    const loop = (now: number) => {
      const k = cv.width / W; ctx.setTransform(k, 0, 0, k, 0, 0); ctx.globalAlpha = 1
      S1(((now - start) / 1000) % LOOP)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener("resize", resize)
    }
    // TAU / eio / eout / eout5 / DIM are ported for fidelity with the source scene
  }, [])

  return (
    <canvas
      ref={ref}
      className={className}
      role="img"
      aria-label="Penrose triangle motion graphic"
      style={{ width: '100%', height: '100%', display: 'block' }}
    />
  )
}
