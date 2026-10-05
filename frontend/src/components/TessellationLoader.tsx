import { useEffect, useRef } from 'react'

// TessellationLoader — the Cadena Triangle Tessellation, ported verbatim into a
// self-contained auto-looping React/canvas component. Only the surrounding
// React structure (useEffect/useRef/canvas/RAF/resize) is new; the drawing math,
// palettes, sprites and timing are copied exactly from the source HTML.

type Pt = [number, number]
interface Poly { f: number; ci: number; p: Pt[] }
interface PenroseFull { polys: Poly[]; n: number; S: number; w: number; h: number; apexOff: number }
interface Tile { x: number; y: number; up: boolean; face: number; ci: number; d: number; ang: number; rnd: number; tgt?: Tile }

export default function TessellationLoader({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const cvEl = ref.current
    if (!cvEl) return
    const ctxEl = cvEl.getContext('2d')
    if (!ctxEl) return
    const cv: HTMLCanvasElement = cvEl
    const ctx: CanvasRenderingContext2D = ctxEl

    /* ---------- ported verbatim ---------- */
    const W = 1920, H = 1080, LOOP = 13
    const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v)), prog = (t: number, a: number, b: number) => clamp((t - a) / (b - a))
    const eio = (x: number) => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2, eout = (x: number) => 1 - Math.pow(1 - x, 3), ein = (x: number) => x * x * x, lerp = (a: number, b: number, x: number) => a + (b - a) * x
    const c30 = Math.cos(Math.PI / 6)

    /* Penrose mark: isometric cube chain, x then y then z, first cube drawn last for the impossible join */
    function penrose(n: number, S: number): PenroseFull {
      const P = (x: number, y: number, z: number): Pt => [(x - y) * c30 * S, ((x + y) / 2 - z) * S]
      const cubes: number[][] = []; for (let i = 0; i < n; i++) cubes.push([i, 0, 0]); for (let j = 0; j < n; j++) cubes.push([n, j, 0]); for (let k = 0; k < n; k++) cubes.push([n, n, k])
      const order = cubes.slice(1).concat([cubes[0]])
      const polys: Poly[] = []
      order.forEach(([x, y, z]) => {
        const ci = cubes.findIndex(c => c[0] === x && c[1] === y && c[2] === z)
        polys.push({ f: 0, ci, p: [P(x, y, z + 1), P(x + 1, y, z + 1), P(x + 1, y + 1, z + 1), P(x, y + 1, z + 1)] })
        polys.push({ f: 1, ci, p: [P(x + 1, y, z), P(x + 1, y + 1, z), P(x + 1, y + 1, z + 1), P(x + 1, y, z + 1)] })
        polys.push({ f: 2, ci, p: [P(x, y + 1, z), P(x + 1, y + 1, z), P(x + 1, y + 1, z + 1), P(x, y + 1, z + 1)] })
      })
      /* rotate -90 so the apex points up: (x,y)->(y,-x) */
      polys.forEach(o => o.p = o.p.map(([x, y]): Pt => [y, -x]))
      const all = polys.flatMap(o => o.p)
      const minY = Math.min(...all.map(p => p[1])), maxY = Math.max(...all.map(p => p[1])), minX = Math.min(...all.map(p => p[0])), maxX = Math.max(...all.map(p => p[0]))
      const apex = all.find(p => Math.abs(p[1] - minY) < 1e-6) as Pt
      const cx = apex[0], cy = minY + (maxY - minY) * 2 / 3 /* triangle centroid */
      polys.forEach(o => o.p = o.p.map(([x, y]): Pt => [x - cx, y - cy]))
      return { polys, n, S, w: maxX - minX, h: maxY - minY, apexOff: minY - cy }
    }

    /* palettes: tones for top / right / left faces */
    const PAL: Record<string, string[]> = {
      full: ["#28e09c", "#16695b", "#279e88"],
      dim: ["#24605a", "#163436", "#1d4846"],
      f0: ["#5cf0bb", "#28e09c", "#3fe8a9"],
      f1: ["#1c8270", "#0f4c42", "#16695b"],
      f2: ["#30b59a", "#1d7766", "#279e88"]
    }

    /* small mark sprites */
    const small = penrose(3, 30)
    const SPR = 256, sprites: Record<string, { c: HTMLCanvasElement; sc: number }> = {}
    for (const k in PAL) {
      const c = document.createElement("canvas"); c.width = c.height = SPR; const g = c.getContext("2d") as CanvasRenderingContext2D
      const sc = SPR / (small.h * 1.25); g.translate(SPR / 2, SPR / 2); g.scale(sc, sc)
      small.polys.forEach(o => { g.beginPath(); o.p.forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y)); g.closePath(); g.fillStyle = PAL[k][o.f]; g.fill() })
      sprites[k] = { c, sc }
    }

    /* triangular lattice */
    const L = 54, TH = L * Math.sqrt(3) / 2            /* cell side and height */
    const big = penrose(4, L * 3)                       /* each cube edge = 2 cells, so faces align with the lattice */
    /* place big mark so its apex sits on a lattice vertex near screen centre */
    const apexX = W / 2, apexY = Math.round(H / 2 - big.h / 2)
    const BX = apexX, BY = apexY - big.apexOff        /* big centroid on screen */
    const bigPolys = big.polys.map(o => ({ f: o.f, ci: o.ci, p: o.p.map(([x, y]): Pt => [x + BX, y + BY]) }))
    function inPoly(px: number, py: number, p: Pt[]) { let c = false; for (let i = 0, j = p.length - 1; i < p.length; j = i++) { const [xi, yi] = p[i], [xj, yj] = p[j]; if (((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi)) c = !c } return c }

    const tiles: Tile[] = []
    const r0 = Math.floor((0 - apexY) / TH) - 2, r1 = Math.ceil((H - apexY) / TH) + 2
    for (let r = r0; r <= r1; r++) {
      const rowY = apexY + r * TH            /* top edge of row */
      const shift = (r % 2) * L / 2            /* lattice vertex x offset for this row */
      for (let k = Math.floor(-W / L) - 4; k <= Math.ceil(W / L) + 4; k++) {
        const vx = apexX + shift + k * L / 2     /* step half a cell: alternate up / down */
        const up = (((k % 2) + 2) % 2) === 0
        const cx = vx + L / 2 * 0, cy = rowY + (up ? TH * 2 / 3 : TH / 3)
        const x = vx                      /* centroid x sits on vx for both orientations with this indexing */
        if (x < -L || x > W + L || cy < -L || cy > H + L) continue
        let face = -1, ci = -1
        for (const o of bigPolys) { if (inPoly(x, cy, o.p)) { face = o.f; ci = o.ci } }
        const dx = x - W / 2, dy = cy - H / 2, d = Math.hypot(dx, dy)
        tiles.push({ x, y: cy, up, face, ci, d, ang: Math.atan2(dy, dx), rnd: Math.random() })
      }
    }
    const maxD = Math.max(...tiles.map(t => t.d))
    const inside = tiles.filter(t => t.face >= 0)
    tiles.forEach(t => { if (t.face < 0) t.tgt = inside[Math.floor(t.rnd * inside.length)] })

    function drawSprite(key: string, x: number, y: number, rot: number, s: number, a: number) {
      if (a <= 0.003 || s <= 0.01) return; const sp = sprites[key]
      const size = L * 0.80 / (small.w / (small.h * 1.25)) /* scale so mark width fits cell */
      ctx.save(); ctx.globalAlpha = a; ctx.translate(x, y); ctx.rotate(rot); ctx.scale(s, s)
      ctx.drawImage(sp.c, -size / 2, -size / 2, size, size); ctx.restore()
    }

    function drawBig(alpha: number, scale: number, glow: number) {
      if (alpha <= 0) return
      ctx.save(); ctx.globalAlpha = alpha; ctx.translate(BX, BY); ctx.scale(scale, scale); ctx.translate(-BX, -BY)
      if (glow > 0) { ctx.shadowColor = "rgba(40,224,156," + (0.35 * glow) + ")"; ctx.shadowBlur = 60 }
      bigPolys.forEach(o => { ctx.beginPath(); o.p.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath(); ctx.fillStyle = PAL.full[o.f]; ctx.fill(); ctx.strokeStyle = PAL.full[o.f]; ctx.lineWidth = 1.2; ctx.lineJoin = 'round'; ctx.stroke() })
      ctx.restore()
    }

    function frame(t: number) {
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, cv.width, cv.height)
      const k = cv.width / W; ctx.setTransform(k, 0, 0, k, 0, 0)
      ctx.fillStyle = "#0a1214"; ctx.fillRect(0, 0, W, H)

      const collapse = (t: number) => t /* readability */
      const solidIn = eio(prog(t, 6.6, 7.6)), solidOut = eio(prog(t, 9.4, 10.2))
      const solid = solidIn * (1 - solidOut)

      for (const tl of tiles) {
        const base = tl.up ? 0 : Math.PI
        /* ripple from centre: each tile turns 120 degrees as the wave passes (twice per loop) */
        const w1 = eio(prog(t, 0.4 + tl.d / maxD * 1.8, 0.4 + tl.d / maxD * 1.8 + 0.7))
        const w2 = eio(prog(t, 10.6 + tl.d / maxD * 1.6, 10.6 + tl.d / maxD * 1.6 + 0.7))
        const rot = base + (w1 + w2) * 2 * Math.PI / 3
        const flash = Math.max(Math.sin(w1 * Math.PI), Math.sin(w2 * Math.PI))
        if (tl.face < 0) {
          /* outside tiles: fall away (far first), return (near first) */
          const outA = ein(prog(t, 3.0 + (1 - tl.d / maxD) * 1.2, 3.0 + (1 - tl.d / maxD) * 1.2 + 0.8))
          const back = eout(prog(t, 9.8 + tl.d / maxD * 1.0, 9.8 + tl.d / maxD * 1.0 + 0.9))
          const gone = outA * (1 - back)
          const tg = tl.tgt as Tile
          const x = lerp(tl.x, tg.x, gone), y = lerp(tl.y, tg.y, gone)
          const sc = 1 - 0.75 * gone, al = gone < 0.85 ? 1 : 1 - (gone - 0.85) / 0.15
          drawSprite("dim", x, y, rot + gone * 2 * Math.PI / 3, sc, al)
          if (flash > 0) drawSprite("full", x, y, rot, sc, flash * al)
          if (gone > 0.05 && gone < 0.999) drawSprite("full", x, y, rot + gone * 2 * Math.PI / 3, sc, 0.35 * Math.sin(gone * Math.PI))
        } else {
          /* inside tiles: take the colour of the big face they sit on */
          const st = 3.6 + (tl.y - BY + 600) / 1200 * 1.0
          const tint = eio(prog(t, st, st + 0.7)) * (1 - eio(prog(t, 10.4, 11.2)))
          /* chain shimmer: light runs along the cube path */
          const ph = prog(t, 5.0, 6.6), chain = Math.exp(-Math.pow((ph * 13 - tl.ci) / 1.2, 2)) * (ph > 0 && ph < 1 ? 1 : 0)
          const pop = 1 + 0.18 * chain
          const a = 1 - solid
          drawSprite("dim", tl.x, tl.y, rot, pop, a * (1 - tint))
          drawSprite("f" + tl.face, tl.x, tl.y, rot, pop, a * tint)
          if (flash > 0) drawSprite("full", tl.x, tl.y, rot, 1, flash * a * (1 - tint))
          if (chain > 0.02) drawSprite("full", tl.x, tl.y, rot, pop, chain * 0.7 * a)
        }
      }
      /* solid mark: tiles merge into one large Penrose triangle */
      const breathe = 1 + 0.015 * Math.sin((t - 7.6) * 2.2) * prog(t, 7.6, 8)
      drawBig(solid, lerp(0.97, 1, solidIn) * breathe, solid)
    }

    /* ---------- resize / render loop ---------- */
    function resize() { const r = cv.getBoundingClientRect(), d = Math.min(window.devicePixelRatio || 1, 2); cv.width = Math.round(r.width * d); cv.height = Math.round(r.height * d) }
    window.addEventListener("resize", resize); resize()

    const start = performance.now()
    let raf = 0
    const loop = (now: number) => {
      frame(((now - start) / 1000) % LOOP)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener("resize", resize)
    }
    // collapse is a no-op kept for fidelity with the source frame()
  }, [])

  return (
    <div className={className} style={{ width: '100%', maxWidth: 'calc(100vh * 16 / 9)', aspectRatio: '16 / 9' }}>
      <canvas
        ref={ref}
        role="img"
        aria-label="Tessellated Penrose triangles assembling into one large Penrose triangle"
        style={{ width: '100%', height: '100%', display: 'block' }}
      />
    </div>
  )
}
