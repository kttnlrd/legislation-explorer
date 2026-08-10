# Merge Background Generator into Social Composer

> **Goal:** Replace the social composer's solid-fill card canvas with the background generator's 7 procedural renderers, bringing all the generator's controls into the composer as a single-page tool.

**Files:**
- Modify: `frontend/dist/social-composer.html` — single merge target
- Keep: `frontend/dist/card-background-generator.html` — leave untouched as standalone tool

---

### Task 1: Add renderer code, helpers, and state from generator into composer's `<script>`

**Objective:** Import the 7 background renderers, palette/seed/grain infrastructure into the composer so `draw()` can call them instead of solid fill.

**Files:** Modify `frontend/dist/social-composer.html` (JS section)

**_Inlines to paste into the composer's `<script>` section, before the existing card editor code (before the `// Image card editor` comment at line 480):_**

Copy these from the generator (`card-background-generator.html` lines 226–465):

1. `STYLES` array (7 style definitions)
2. `PALETTES` array (6 palette definitions)
3. `RATIOS` array — *but only keep the 3 generator ratios, we'll merge differently*
4. `state` object — add `style`, `palette`, `ratio` (from generator), keep `seed`, `grain`
5. `mulberry32()` seeded RNG function
6. `getGrainTile()` + `grainTile` cache variable
7. `hexToRgb()`, `luminance()`, `hexA()`, `roundRect()` helpers
8. All 7 renderer functions: `drawAurora`, `drawGrainGradient`, `drawGlass`, `drawBrutal`, `drawSpotlight`, `drawDots`, `drawDuo`
9. `RENDERERS` map object

**Do NOT copy:** `drawText()` from generator (composer has its own text rendering with Poppins) or the generator's `render()` function (composer's `draw()` is the equivalent).

**State additions to composer:**

```js
// Add after existing state vars (line 484-485)
let style = 'aurora';
let palette = PALETTES[0];
let grain = 35;
let seed = 1234;
let vpos = 'bottom';
let subtext = '';
```

---

### Task 2: Rewrite composer's `draw()` function to use procedural renderers

**Objective:** Replace the solid-fill approach with the renderer pipeline.

**Files:** Modify `frontend/dist/social-composer.html` lines 514-539

**Replace the entire `draw()` function:**

```js
function draw() {
  const W = canvas.width, H = canvas.height, pad = W * 0.075;
  const rng = mulberry32(seed);

  // 1. Draw background style
  const meta = RENDERERS[style](ctx, W, H, palette, rng) || {};

  // 2. Apply grain overlay
  if (grain > 0) {
    const tile = getGrainTile();
    const pat = ctx.createPattern(tile, 'repeat');
    ctx.save();
    ctx.globalAlpha = (grain / 100) * 0.13;
    ctx.globalCompositeOperation = 'overlay';
    ctx.fillStyle = pat;
    ctx.fillRect(0, 0, W, H);
    ctx.restore();
  }

  // 3. Determine text colour: manual override if user picked one, else auto
  const effectiveFg = manualTextColor || meta.textColor || '#F9FAFB';

  // 4. Draw headline
  const weight = 700;
  ctx.font = `${weight} ${fontPx}px Poppins, sans-serif`;
  ctx.fillStyle = effectiveFg;
  ctx.textAlign = align;
  ctx.textBaseline = 'middle';

  if (pos.x === null) { pos = defaultPos(); }
  const headlineText = $('cText').value || '';
  const lines = wrap(headlineText, W - pad * 2);
  const lh = fontPx * 1.15;
  const blockH = lines.length * lh + (subtext ? fontPx * 1.2 : 0);

  // Use vpos to determine Y position (instead of always centering)
  let y;
  if (vpos === 'top') {
    y = pad + fontPx;
  } else if (vpos === 'center') {
    y = (H - blockH) / 2 + fontPx / 2;
  } else { // bottom
    y = H - pad - blockH + fontPx;
  }

  for (const ln of lines) { ctx.fillText(ln, pos.x, y); y += lh; }

  // 5. Draw subtext
  if (subtext) {
    const subtitleSize = Math.round(fontPx * 0.55);
    ctx.font = `500 ${subtitleSize}px Poppins, sans-serif`;
    ctx.globalAlpha = 0.82;
    ctx.fillText(subtext, pos.x, y + subtitleSize * 0.8);
    ctx.globalAlpha = 1;
  }

  // 6. Draw BLACKSHEEP wordmark
  if (showMark) {
    ctx.font = `800 ${Math.round(W * 0.026)}px Poppins, sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'alphabetic';
    // Adapt wordmark colour based on bg — use palette[4] for auto, keep override
    const markColor = manualTextColor || meta.textColor || '#BCFF2F';
    ctx.fillStyle = (style === 'solid' || (!RENDERERS[style])) ? 
      ((bg === '#BCFF2F') ? '#0F0F13' : '#BCFF2F') : markColor;
    ctx.fillText('BLACKSHEEP', pad, H - pad * 0.7);
  }

  // Remember bounds for hit testing
  draw._bounds = { top: pos.y - blockH / 2 - 20, bottom: pos.y + blockH / 2 + 20 };
}
```

Add a `manualTextColor` flag — when the user clicks a text colour swatch, it sets `manualTextColor` and that overrides the renderer's auto colour. When style/palette changes, reset `manualTextColor` to null so auto colour re-engages.

---

### Task 3: Restructure card section HTML to add new controls

**Objective:** Replace the simple solid-colour bg swatches with style chips, palette swatches, grain slider, subtext, vpos, and reshuffle.

**Files:** Modify `frontend/dist/social-composer.html` lines 231-263

**New card controls layout (replace lines 231–263):**

```html
<div class="field">
  <label>Background style</label>
  <div class="chips" id="styleChips"></div>
</div>

<div class="field">
  <label>Palette</label>
  <div class="palettes" id="paletteChips"></div>
</div>

<div class="field">
  <label>Grain <span class="hint" id="grainVal">35%</span></label>
  <input type="range" id="grainSlider" min="0" max="100" value="35">
</div>

<div class="field">
  <label for="cText">Headline (drag on canvas to position)</label>
  <textarea id="cText" placeholder="Type the card headline. Line breaks are respected.">ATO loses appeal on s 99B</textarea>
</div>

<div class="field">
  <label for="cSub">Subtext (optional)</label>
  <input type="text" id="cSub" placeholder="e.g. Tax Lore, Episode 12">
</div>

<div class="field">
  <label>Text colour</label>
  <div class="swatches" id="fgSw">
    <button class="sw on" style="background:#F9FAFB" data-fg="#F9FAFB" title="White"></button>
    <button class="sw" style="background:#BCFF2F" data-fg="#BCFF2F" title="Lime"></button>
    <button class="sw" style="background:#0F0F13" data-fg="#0F0F13" title="Black"></button>
  </div>
</div>

<div class="field">
  <label for="cAlign">Alignment</label>
  <select id="cAlign">
    <option value="left">Left</option>
    <option value="center">Center</option>
    <option value="right">Right</option>
  </select>
</div>

<div class="field">
  <label>Vertical position</label>
  <div class="chips" id="vposChips"></div>
</div>

<div class="field">
  <label>Text size <span id="cSizeVal" class="hint"></span></label>
  <input type="range" id="cFont" min="36" max="150" value="84">
</div>

<label class="chk"><input type="checkbox" id="cMark" checked> Show BLACKSHEEP wordmark</label>

<div style="display:flex;gap:8px;margin-top:4px">
  <button class="btn btn-ghost btn-sm" id="shuffleBtn" style="flex:1">↻ Reshuffle</button>
</div>
```

**CSS additions needed (add after existing styles):**

```css
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{
  border:1px solid var(--border);background:var(--surface2);color:var(--muted);
  font-size:12px;padding:6px 11px;border-radius:8px;cursor:pointer;font-family:inherit;
  transition:border-color .12s,background .12s;
}
.chip:hover{border-color:#3a4152}
.chip.active{border-color:var(--lime);background:rgba(188,255,47,0.12);color:var(--lime)}
.palettes{display:flex;flex-wrap:wrap;gap:7px}
.palette-sw{
  width:40px;height:28px;border-radius:7px;cursor:pointer;border:2px solid transparent;
  box-shadow:0 0 0 1px var(--border);overflow:hidden;display:flex;
}
.palette-sw span{flex:1}
.palette-sw.active{border-color:var(--lime)}
```

---

### Task 4: Wire up new UI controls in JS

**Objective:** Add event handlers for style chips, palette picker, grain slider, subtext, vpos chips, shuffle button.

**Files:** Modify `frontend/dist/social-composer.html` JS section

**Add after line 548 (`cSizeVal.textContent=fontPx+'px'`):**

```js
// ── Background style chips ──
function renderChips(containerId, items, currentId, onClick) {
  const el = $(containerId);
  el.innerHTML = '';
  items.forEach(item => {
    const b = document.createElement('button');
    b.className = 'chip' + (item.id === currentId ? ' active' : '');
    b.textContent = item.name || item;
    b.onclick = () => { onClick(item); draw(); renderAllChips(); };
    el.appendChild(b);
  });
}
function renderPalettes(containerId, items, currentId, onClick) {
  const el = $(containerId);
  el.innerHTML = '';
  items.forEach(p => {
    const s = document.createElement('div');
    s.className = 'palette-sw' + (p.id === currentId ? ' active' : '');
    p.colors.slice(0, 3).forEach(c => {
      const sp = document.createElement('span'); sp.style.background = c; s.appendChild(sp);
    });
    s.onclick = () => { palette = p; manualTextColor = null; draw(); renderAllChips(); };
    el.appendChild(s);
  });
}
function renderAllChips() {
  renderChips('styleChips', STYLES, style, it => { style = it.id; manualTextColor = null; });
  renderPalettes('paletteChips', PALETTES, palette.id);
  renderChips('vposChips', [{id:'top',name:'Top'},{id:'center',name:'Center'},{id:'bottom',name:'Bottom'}], vpos, it => { vpos = it.id; });
}

$('grainSlider').addEventListener('input', e => {
  grain = +e.target.value;
  $('grainVal').textContent = grain + '%';
  draw();
});

$('cSub').addEventListener('input', () => {
  subtext = $('cSub').value;
  draw();
});

$('shuffleBtn').addEventListener('click', () => {
  seed = Math.floor(Math.random() * 1e9);
  draw();
});

renderAllChips();
```

**Modify `setSize()` (line 487-495):** Keep as-is. The size selector already sets canvas width/height and triggers `draw()`.

**Remove old bg swatch handlers (lines 550-557):** The `bgSw` click handler is no longer needed. The bg is now driven by style + palette.

**Remove or adapt `manualTextColor` tracking** in `fgSw` click handler (lines 559-562) — change it to set `manualTextColor` and call `draw()`:

```js
$('fgSw').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  $('fgSw').querySelectorAll('button').forEach(x => x.classList.remove('on')); b.classList.add('on');
  manualTextColor = b.dataset.fg;
  draw();
});
```

---

### Task 5: Merge size options

**Objective:** Combine composer's 4 sizes with generator's 3 sizes. Keep all options.

**Replace the size `<select>` options (lines 224-230):**

```html
<select id="cSize">
  <option value="1080x1350">Portrait 1080 × 1350</option>
  <option value="1080x1080">Square 1080 × 1080</option>
  <option value="1200x627">Landscape 1200 × 627</option>
  <option value="1600x900">X / Twitter 1600 × 900</option>
  <option value="1080x1920">Story 9:16 1080 × 1920</option>
</select>
```

---

### Task 6: Keep font loading and existing interactions

**Objective:** Ensure everything still works together.

- Keep Poppins font link (already in `<head>`)
- Keep font-ready callback at line 594-597
- Keep drag-to-position, download, reset position, push buttons — unchanged
- Remove the "Background Generator →" link from header (line 162) since it's now built in, OR keep it as a link to the standalone tool

---

### Verification

1. Load `http://localhost:8765/social-composer.html` in browser
2. Card canvas should render with Aurora mesh style (default) instead of solid dark
3. Click each style chip — canvas redraws with that style
4. Click each palette swatch — colour scheme changes
5. Drag grain slider — grain intensity changes
6. Type subtext — it appears below headline
7. Change vpos — text block moves top/center/bottom
8. Click Reshuffle — procedural elements reposition (aurora blobs, spotlight, etc.)
9. Change size — canvas and text scale correctly
10. Download PNG — should work (canvas toDataURL)
11. Push to Buffer with image attached — should still work (reads canvas toDataURL)
12. All old features still work: generate, condense, format toolbar, copy/clear

---

### Risks

| Risk | Mitigation |
|------|-----------|
| Canvas `toDataURL` performance on complex backgrounds | Renderers are procedural canvas draws, same performance as old solid fill |
| Font mismatch (Poppins vs Space Grotesk) | Intentionally keeping Poppins — it's the Blacksheep brand face. Text may look different from generator but consistent with composer's visual identity |
| `manualTextColor` override can clash with auto palette colour | Auto resets on style/palette change. User override is deliberate choice |
| Grain tile cache uses `Math.random()` — different on each page load | Intentional: grain is organic noise, doesn't need determinism. Only procedural blobs/shapes use seeded RNG |
