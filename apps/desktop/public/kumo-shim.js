(function () {
  var SHIM_BUILD = 'v42-chandra-embercrust'

  if (window.__kumoShimBuild === SHIM_BUILD) return
  window.__kumoShimBuild = SHIM_BUILD
  window.__kumoShim = true

  // v22: standalone Chandra branding on stock upstream. Owns text identity
  // (Hermes -> Chandra), the Chandra desktop theme (user-theme registry), AND
  // the fire/lightning ambience overlay (chandra-ambience.css + DOM mounted
  // here — the old source-native build that owned visuals is gone).
  // NOTE: v19/v21 stripped [id^="chandra-"] nodes; v22 MOUNTS them instead.
  try {
    var THEME_VERSION = 'v21'
    var pal = {
      background: '#0B162A',
      foreground: '#E8F0FF',
      card: '#101D33',
      cardForeground: '#E8F0FF',
      muted: '#16233C',
      mutedForeground: '#8FA3C4',
      popover: '#122038',
      popoverForeground: '#E8F0FF',
      primary: '#FF7A1A',
      primaryForeground: '#140B04',
      secondary: '#1A2A45',
      secondaryForeground: '#B8D4FF',
      accent: '#152540',
      accentForeground: '#CFE0F5',
      border: '#2A3F63',
      input: '#16263F',
      ring: '#FF7A1A',
      midground: '#FF7A1A',
      composerRing: '#FF7A1A',
      destructive: '#E5534B',
      destructiveForeground: '#FEF2F2',
      sidebarBackground: '#070E1C',
      sidebarBorder: '#1C2C49',
      userBubble: '#14243E',
      userBubbleBorder: '#2C4468'
    }
    var reg = {}
    try {
      reg = JSON.parse(localStorage.getItem('hermes-desktop-user-themes-v1') || '{}') || {}
    } catch (e) {
      reg = {}
    }
    if (localStorage.getItem('chandra-theme-installed') !== THEME_VERSION || !reg.chandra) {
      reg.chandra = {
        name: 'chandra',
        label: 'Chandra',
        description: 'Chandra pixel storm - midnight canvas, ember accent',
        colors: pal,
        darkColors: pal
      }
      localStorage.setItem('hermes-desktop-user-themes-v1', JSON.stringify(reg))
      localStorage.setItem('chandra-theme-installed', THEME_VERSION)
    }
    localStorage.setItem('hermes-desktop-theme-v2', 'chandra')
    localStorage.setItem('hermes-desktop-mode-v1', 'dark')
    localStorage.setItem('hermes-boot-background', '#070B18')
    localStorage.setItem('hermes-boot-color-scheme', 'dark')
    try {
      var lastProf = localStorage.getItem('hermes-desktop-active-profile-v1')
      if (lastProf && lastProf !== 'default') {
        var profRec = JSON.parse(localStorage.getItem('hermes-desktop-profile-themes-v1') || '{}') || {}
        profRec[lastProf] = 'chandra'
        localStorage.setItem('hermes-desktop-profile-themes-v1', JSON.stringify(profRec))
      }
    } catch (e) {}
  } catch (e) {}

  document.documentElement.dataset.chandraBrand = SHIM_BUILD

  // ── v30: Storm-concept sky — drifting pixel cloud banks + sparse rain ─────
  function startStormSky(cv) {
    try {
      if (!cv) return
      var W = cv.width, H = cv.height
      var ctx = cv.getContext('2d')
      var reduced = false
      try { reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch (e) {}
      function mkBank(n, ymin, ymax) {
        // v37: thin dashed streak-clouds like the Lightning mock — 1 cell high
        var blobs = []
        for (var i = 0; i < n; i++) {
          blobs.push({ x: Math.random() * W, y: ymin + ((Math.random() * (ymax - ymin)) | 0), w: 10 + ((Math.random() * 24) | 0), h: 1 })
        }
        return blobs
      }
      var far = mkBank(8, 0, 14), near = mkBank(6, 4, 24)
      var stars = []
      for (var st2 = 0; st2 < 40; st2++) {
        stars.push({
          x: (Math.random() * W) | 0,
          y: (Math.random() * H) | 0,
          c: Math.random() < 0.5 ? '232,240,255' : '184,212,255',
          b: 0.1 + Math.random() * 0.2,
          p: Math.random() * 6.28,
          s: 0.02 + Math.random() * 0.05
        })
      }
      var t9 = 0
      function draw() {
        ctx.clearRect(0, 0, W, H)
        t9++
        var i2, b2, xx
        for (i2 = 0; i2 < stars.length; i2++) {
          var st3 = stars[i2]
          var a9 = st3.b + 0.12 * Math.sin(t9 * st3.s + st3.p)
          if (a9 < 0.05) a9 = 0.05
          ctx.fillStyle = 'rgba(' + st3.c + ',' + a9.toFixed(3) + ')'
          ctx.fillRect(st3.x, st3.y, 1, 1)
        }
        for (i2 = 0; i2 < far.length; i2++) {
          b2 = far[i2]; b2.x = (b2.x + 0.12) % (W + b2.w)
          xx = (b2.x | 0) - b2.w
          ctx.fillStyle = 'rgba(140,170,215,0.28)'
          ctx.fillRect(xx, b2.y, b2.w, 1)
        }
        for (i2 = 0; i2 < near.length; i2++) {
          b2 = near[i2]; b2.x = (b2.x + 0.25) % (W + b2.w)
          xx = (b2.x | 0) - b2.w
          ctx.fillStyle = 'rgba(100,132,180,0.38)'
          ctx.fillRect(xx, b2.y, b2.w, 1)
        }
      }
      draw()
      if (!reduced) setInterval(function () { if (!document.hidden) draw() }, 120)
    } catch (e) {}
  }

  // ── v25: live pixel-art fire (classic demoscene heat propagation, low-res
  // canvas upscaled with image-rendering:pixelated) ─────────────────────────
  function startPixelFire(cv) {
    try {
      if (!cv) return
      var W = cv.width, H = cv.height
      var ctx = cv.getContext('2d')
      var heat = new Array(W * H)
      for (var i = 0; i < heat.length; i++) heat[i] = 0
      var img = ctx.createImageData(W, H)
      var reduced = false
      try { reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch (e) {}
      // v29: flame TONGUES — weighted hotspots that wander, over a low ember bed.
      var spots = [0.02, 0.05, 0.08, 0.92, 0.95, 0.98].map(function (f) { return (W * f) | 0 })
      var drift = [0, 0, 0, 0, 0, 0]
      var emberBits = []
      function tick() {
        var x, y, idx
        var edge = (W * 0.08) | 0
        for (var s2 = 0; s2 < spots.length; s2++) {
          if (Math.random() < 0.4) drift[s2] += Math.random() < 0.5 ? -2 : 2
          if (drift[s2] > 12) drift[s2] = 12
          if (drift[s2] < -12) drift[s2] = -12
        }
        for (x = 0; x < W; x++) {
          if (x > edge && x < W - edge) { heat[(H - 1) * W + x] = 0; continue }
          var h3 = 8 + Math.random() * 8
          for (var s3 = 0; s3 < spots.length; s3++) {
            var dx2 = Math.abs(x - (spots[s3] + drift[s3]))
            if (dx2 < 10) { var hh = 34 - dx2 * 1.2 + Math.random() * 4; if (hh > h3) h3 = hh }
          }
          heat[(H - 1) * W + x] = h3
        }
        for (y = 0; y < H - 1; y++) {
          for (x = 0; x < W; x++) {
            var sx = x + ((Math.random() * 3) | 0) - 1
            if (sx < 0) sx = 0
            if (sx > W - 1) sx = W - 1
            var v = heat[(y + 1) * W + sx] - Math.random() * 6.2
            heat[y * W + x] = v > 0 ? v : 0
          }
        }
        var d = img.data
        for (idx = 0; idx < W * H; idx++) {
          var h2 = heat[idx], p = idx * 4
          if (h2 < 1) { d[p + 3] = 0; continue }
          if (h2 < 7) { d[p] = 60; d[p + 1] = 16; d[p + 2] = 4; d[p + 3] = 110 }
          else if (h2 < 13) { d[p] = 150; d[p + 1] = 38; d[p + 2] = 6; d[p + 3] = 170 }
          else if (h2 < 19) { d[p] = 222; d[p + 1] = 84; d[p + 2] = 12; d[p + 3] = 210 }
          else if (h2 < 27) { d[p] = 255; d[p + 1] = 140; d[p + 2] = 30; d[p + 3] = 235 }
          else { d[p] = 255; d[p + 1] = 208; d[p + 2] = 96; d[p + 3] = 250 }
        }
        ctx.putImageData(img, 0, 0)
        // v40: rising embers removed — they drifted over sidebar text
      }
      tick()
      if (!reduced) setInterval(function () { if (!document.hidden) tick() }, 83)
    } catch (e) {}
  }

  // ── v42: ember-crust ground — a thin charred pixel strip the corner fires
  // sit on. Static mottled charcoal base + breathing ember cracks: dense gold
  // near the corners, sparse dim crimson along the center. Replaces the muddy
  // horizon wash as the "scorched earth" element (wash kept, much subtler).
  function startEmberCrust(cv) {
    try {
      if (!cv) return
      var W = cv.width, H = cv.height
      var ctx = cv.getContext('2d')
      var reduced = false
      try { reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch (e) {}
      var base = []
      for (var x = 0; x < W; x++) {
        var shade = Math.random()
        base.push(shade < 0.6 ? '#120C09' : shade < 0.9 ? '#1A100A' : '#22140C')
      }
      var embers = []
      for (var i = 0; i < W; i++) {
        var edgeDist = Math.min(i, W - 1 - i) / W
        var density = edgeDist < 0.1 ? 0.3 : edgeDist < 0.2 ? 0.1 : 0.025
        if (Math.random() < density) {
          embers.push({
            x: i,
            y: (Math.random() * H) | 0,
            hot: edgeDist < 0.12 ? 1 : 0,
            b: 0.25 + Math.random() * 0.5,
            p: Math.random() * 6.28,
            s: 0.05 + Math.random() * 0.15
          })
        }
      }
      var t = 0
      function draw() {
        t++
        for (var x2 = 0; x2 < W; x2++) {
          ctx.fillStyle = base[x2]
          ctx.fillRect(x2, 0, 1, H)
        }
        for (var e2 = 0; e2 < embers.length; e2++) {
          var em = embers[e2]
          var a = em.b + 0.35 * Math.sin(t * em.s + em.p)
          if (a < 0.06) a = 0.06
          if (em.hot) {
            ctx.fillStyle = 'rgba(255,170,60,' + a.toFixed(3) + ')'
            ctx.fillRect(em.x, em.y, 1, 1)
            if (a > 0.6) {
              ctx.fillStyle = 'rgba(255,120,26,' + ((a - 0.5) * 0.5).toFixed(3) + ')'
              ctx.fillRect(em.x - 1, em.y, 1, 1)
              ctx.fillRect(em.x + 1, em.y, 1, 1)
            }
          } else {
            ctx.fillStyle = 'rgba(190,52,16,' + (a * 0.8).toFixed(3) + ')'
            ctx.fillRect(em.x, em.y, 1, 1)
          }
        }
      }
      draw()
      if (!reduced) setInterval(function () { if (!document.hidden) draw() }, 160)
    } catch (e) {}
  }

  // ── v25: procedural pixel lightning bolts (jagged stepped walk + branch) ──
  function startPixelBolts(cv, fireCv) {
    try {
      if (!cv) return
      var W = cv.width, H = cv.height
      var ctx = cv.getContext('2d')
      var reduced = false
      try { reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches } catch (e) {}
      if (reduced) return
      function strike() {
        // v29: the strike lights up the ground fire for a beat
        try {
          if (fireCv) {
            fireCv.style.opacity = '.8'
            setTimeout(function () { fireCv.style.opacity = '.5' }, 350)
          }
          var crustFlare = document.getElementById('chandra-pixel-crust')
          if (crustFlare) {
            crustFlare.style.opacity = '1'
            setTimeout(function () { crustFlare.style.opacity = '.75' }, 350)
          }
        } catch (e2) {}
        var cells = []
        // v39: strike in the outer thirds only — never down the reading line
        var x = Math.random() < 0.5 ? ((W * 0.08 + Math.random() * W * 0.27) | 0) : ((W * 0.65 + Math.random() * W * 0.27) | 0)
        var len = (H * (0.55 + Math.random() * 0.4)) | 0
        var bx = -1, by = -1
        for (var y = 0; y < len; y++) {
          cells.push([x, y])
          if (bx < 0 && y > 6 && Math.random() < 0.25) { bx = x; by = y }
          var r = Math.random()
          x += r < 0.38 ? -1 : r < 0.76 ? 1 : 0
          if (x < 2) x = 2
          if (x > W - 3) x = W - 3
        }
        if (bx >= 0) {
          var b = bx
          for (var y2 = by; y2 < Math.min(len, by + 14); y2++) {
            b += Math.random() < 0.5 ? -1 : 1
            cells.push([b, y2])
          }
        }
        var frame = 0
        var iv = setInterval(function () {
          ctx.clearRect(0, 0, W, H)
          frame++
          if (frame > 8) { clearInterval(iv); return }
          for (var i = 0; i < cells.length; i++) {
            var c = cells[i]
            if (frame === 1 || frame === 3 || frame === 5) {
              // pulse-bright frames
              ctx.fillStyle = 'rgba(120,168,230,0.4)'
              ctx.fillRect(c[0] - 1, c[1], 3, 1)
              ctx.fillStyle = '#F2F8FF'
              ctx.fillRect(c[0], c[1], 1, 1)
            } else if (frame === 2 || frame === 4) {
              // pulse-dim frames
              ctx.fillStyle = 'rgba(120,168,230,0.18)'
              ctx.fillRect(c[0], c[1], 1, 1)
            } else {
              ctx.fillStyle = 'rgba(140,190,245,' + (0.35 * (8 - frame) / 3).toFixed(3) + ')'
              ctx.fillRect(c[0], c[1], 1, 1)
            }
          }
        }, 80)
        setTimeout(strike, 8000 + Math.random() * 8000)
      }
      setTimeout(strike, 3000)
    } catch (e) {}
  }

  // ── Fire + lightning ambience (chandra-ambience.css provides the animations)
  function ensureAmbience() {
    try {
      if (!document.body) return
      if (document.getElementById('chandra-ambience')) return
      var wrap = document.createElement('div')
      wrap.id = 'chandra-ambience'
      wrap.setAttribute('data-chandra-backdrop', '')
      wrap.setAttribute('aria-hidden', 'true')
      wrap.style.cssText = 'position:fixed;inset:0;z-index:2147480000;pointer-events:none;overflow:hidden'

      // v30 "stormhearth": Storm-concept sky (drifting pixel clouds + rain) up top,
      // Fire-concept hearth palette in the corners, 26px status-bar protection zone.
      // v36 "mockscene": the Lightning mock's atmosphere — deep sky tint, stars
      // across the upper window, wispy clouds, calm warm gradient horizon.
      // Bonfire mounds removed; the horizon glow IS the fire element now.
      var topTint = document.createElement('div')
      topTint.className = 'chandra-sky-tint'
      topTint.style.cssText = 'position:absolute;left:0;right:0;top:0;height:22vh;background:linear-gradient(to bottom, rgba(4,7,18,.45), transparent)'
      wrap.appendChild(topTint)

      var horizon = document.createElement('div')
      horizon.className = 'chandra-horizon'
      horizon.style.cssText = 'position:absolute;left:0;right:0;bottom:0;height:16vh;background:linear-gradient(to top, rgba(122,48,22,.20), rgba(80,32,16,.08) 55%, transparent 100%)'
      wrap.appendChild(horizon)

      var skyCv = document.createElement('canvas')
      skyCv.id = 'chandra-pixel-sky'
      skyCv.width = 704
      skyCv.height = 172
      skyCv.style.cssText = 'position:absolute;left:0;top:34px;width:100%;height:30vh;image-rendering:pixelated;opacity:.5;-webkit-mask-image:linear-gradient(to bottom, black 0%, rgba(0,0,0,.6) 45%, transparent 85%);mask-image:linear-gradient(to bottom, black 0%, rgba(0,0,0,.6) 45%, transparent 85%)'
      wrap.appendChild(skyCv)

      var fireCv = document.createElement('canvas')
      fireCv.id = 'chandra-pixel-fire'
      fireCv.width = 784
      fireCv.height = 22
      fireCv.style.cssText = 'position:absolute;left:0;bottom:30px;width:100%;height:40px;image-rendering:pixelated;opacity:.6'
      wrap.appendChild(fireCv)

      var crustCv = document.createElement('canvas')
      crustCv.id = 'chandra-pixel-crust'
      crustCv.width = 784
      crustCv.height = 4
      crustCv.style.cssText = 'position:absolute;left:0;bottom:26px;width:100%;height:8px;image-rendering:pixelated;opacity:.75'
      wrap.appendChild(crustCv)

      var boltCv = document.createElement('canvas')
      boltCv.id = 'chandra-pixel-bolts'
      boltCv.width = 720
      boltCv.height = 162
      boltCv.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:40vh;image-rendering:pixelated;mix-blend-mode:screen;opacity:.9'
      wrap.appendChild(boltCv)

      var mark = document.createElement('div')
      mark.className = 'chandra-ambience-watermark'
      mark.style.cssText = 'position:absolute;right:14px;bottom:10px;width:48px;height:48px;background:url(./ds-assets/chandra-watermark.png) center/contain no-repeat;opacity:.12'
      wrap.appendChild(mark)

      document.body.appendChild(wrap)
      startStormSky(skyCv)
      startPixelFire(fireCv)
      startEmberCrust(crustCv)
      startPixelBolts(boltCv, fireCv)
    } catch (e) {}
  }

  var MAP = [
    ['Hermes Agent', 'Chandra'],
    ['Hermes', 'Chandra'],
    ['Kumo Agent', 'Chandra'],
    ['Nous Research', 'Kumobits']
  ]
  // v40: ALL-CAPS brand tokens swap only as standalone words — never inside
  // env-var-style identifiers (HERMES_HOME, HERMES_BACKEND_READY, NOUS_API_KEY
  // etc. render untouched in transcripts).
  var CAPS = [
    [/(?<![A-Z0-9_])HERMES(?![A-Z0-9_])/g, 'CHANDRA'],
    [/(?<![A-Z0-9_])NOUS(?![A-Z0-9_])/g, 'KUMOBITS']
  ]
  var HIT = /Hermes|HERMES|\bKumo\b|\bKUMO\b|Nous Research|NOUS/
  var SKIP = { CODE: 1, PRE: 1, SCRIPT: 1, STYLE: 1 }
  var ATTRS = ['title', 'aria-label', 'placeholder', 'alt', 'data-placeholder']

  function fix(value) {
    if (!value || !HIT.test(value)) return value
    var next = value
    for (var i = 0; i < MAP.length; i++) next = next.split(MAP[i][0]).join(MAP[i][1])
    for (var c = 0; c < CAPS.length; c++) next = next.replace(CAPS[c][0], CAPS[c][1])
    return next.replace(/\bKUMO\b/g, 'CHANDRA').replace(/\bKumo\b/g, 'Chandra')
  }

  function inSkipped(element) {
    for (var node = element; node; node = node.parentElement) {
      if (SKIP[node.nodeName]) return true
    }
    return false
  }

  function fixText(node) {
    var before = node.nodeValue
    var after = fix(before)
    if (after !== before) node.nodeValue = after
  }

  function fixAttrs(element) {
    for (var i = 0; i < ATTRS.length; i++) {
      var attr = ATTRS[i]
      if (!element.hasAttribute || !element.hasAttribute(attr)) continue
      var before = element.getAttribute(attr)
      var after = fix(before)
      if (after !== before) element.setAttribute(attr, after)
    }
  }

  function sweep(root) {
    if (!root) return
    if (root.nodeType === 3) {
      if (!root.parentElement || !inSkipped(root.parentElement)) fixText(root)
      return
    }
    if (root.nodeType !== 1 || SKIP[root.nodeName]) return
    if (root.id === 'chandra-ambience') return

    fixAttrs(root)
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        return node.parentElement && inSkipped(node.parentElement)
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT
      }
    })
    var textNode
    while ((textNode = walker.nextNode())) fixText(textNode)

    if (root.querySelectorAll) {
      var elements = root.querySelectorAll('[title],[aria-label],[placeholder],[alt],[data-placeholder]')
      for (var i = 0; i < elements.length; i++) fixAttrs(elements[i])
    }
  }

  function enforceTitle() {
    var next = fix(document.title)
    if (next !== document.title) document.title = next
    if (document.title.indexOf('Chandra') === -1 && document.title.trim() === '') {
      document.title = 'Chandra'
    }
  }

  var observer = new MutationObserver(function (mutations) {
    for (var i = 0; i < mutations.length; i++) {
      var mutation = mutations[i]
      if (mutation.type === 'characterData') {
        if (!mutation.target.parentElement || !inSkipped(mutation.target.parentElement)) fixText(mutation.target)
      } else if (mutation.type === 'attributes') {
        fixAttrs(mutation.target)
      } else {
        for (var j = 0; j < mutation.addedNodes.length; j++) sweep(mutation.addedNodes[j])
      }
    }
    enforceTitle()
    ensureAmbience()
  })

  observer.observe(document.documentElement, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: ATTRS
  })

  function boot() {
    sweep(document.body)
    enforceTitle()
    ensureAmbience()
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot)
  } else {
    boot()
  }
})()
