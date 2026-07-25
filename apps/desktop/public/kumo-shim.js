(function () {
  if (window.__kumoShim) return
  window.__kumoShim = true

  // Inferno v12 — cinematic furnace + blue thunder (thin electric veins, not clip-art).
  function dsAsset(name) {
    var probe = document.querySelector('img[src*="ds-assets/"]')
    if (probe) {
      var src = probe.getAttribute('src') || ''
      var i = src.indexOf('ds-assets/')
      if (i >= 0) return src.slice(0, i + 'ds-assets/'.length) + name
    }
    var base = document.querySelector('base')
    if (base && base.href) return new URL('ds-assets/' + name, base.href).href
    return './ds-assets/' + name
  }

  function stripUglyOverlays() {
    ;[
      'chandra-fire-bottom',
      'chandra-fire-left',
      'chandra-fire-right',
      'chandra-fire-top',
      'chandra-bolts',
      'chandra-heat-haze',
      'chandra-edge-layer',
      'chandra-edge-png',
      'chandra-lightning-flash',
      'chandra-vignette',
      'chandra-thunder',
      'chandra-inferno-css'
    ].forEach(function (id) {
      var el = document.getElementById(id)
      if (el) el.remove()
    })
  }

  function injectStyles() {
    if (document.getElementById('chandra-inferno-css')) return
    var css = document.createElement('style')
    css.id = 'chandra-inferno-css'
    css.textContent = [
      '@keyframes chandra-ember{',
      '0%,100%{opacity:.55}',
      '50%{opacity:.8}',
      '}',
      '@keyframes chandra-sky-glow{',
      '0%,100%{opacity:.45}',
      '50%{opacity:.75}',
      '}',
      '@keyframes chandra-flash{',
      '0%,91%,100%{opacity:0}',
      '92%{opacity:.55}',
      '93%{opacity:0}',
      '94%{opacity:.4}',
      '95.5%{opacity:0}',
      '}',
      '@keyframes chandra-bolt-a{',
      '0%,88%,100%{opacity:0}',
      '89%{opacity:1}',
      '90.5%{opacity:0}',
      '}',
      '@keyframes chandra-bolt-b{',
      '0%,40%,100%{opacity:0}',
      '42%{opacity:.9}',
      '43.5%{opacity:0}',
      '72%{opacity:0}',
      '73%{opacity:.7}',
      '74%{opacity:0}',
      '}',
      '@keyframes chandra-bolt-idle{',
      '0%,100%{opacity:.22}',
      '50%{opacity:.4}',
      '}',
      'html,body,#root{background-color:transparent!important;}',
      ':root{',
      '--background:#1A070A!important;',
      '--foreground:#F8E6E2!important;',
      '--card:#261015!important;',
      '--card-foreground:#F8E6E2!important;',
      '--muted:#32151C!important;',
      '--muted-foreground:#C99A94!important;',
      '--popover:#221014!important;',
      '--primary:#E83A24!important;',
      '--primary-foreground:#1A0406!important;',
      '--secondary:#4A1820!important;',
      '--accent:#5C1C28!important;',
      '--border:#5A2430!important;',
      '--input:#140508!important;',
      '--ring:#F05A2A!important;',
      '--midground:#E84520!important;',
      '--composer-ring:#F05A2A!important;',
      '--sidebar-background:#120408!important;',
      '--sidebar-border:#3A1820!important;',
      '}',
      '#chandra-storm-layer{',
      'pointer-events:none;position:fixed;inset:0;z-index:0;',
      'background-color:#1A070A;background-size:cover;background-position:center;',
      '}',
      '#chandra-hero-layer{',
      'pointer-events:none;position:fixed;inset:0;z-index:1;',
      'opacity:.05;background-repeat:no-repeat;background-size:min(88vh,920px);',
      'background-position:72% 8%;filter:saturate(1.1);',
      '}',
      /* Fire heat bottom/sides + storm-blue sky wash on top */
      '#chandra-rim{',
      'pointer-events:none;position:fixed;inset:0;z-index:2147483000;',
      'animation:chandra-ember 6s ease-in-out infinite;',
      'background:',
      'radial-gradient(120% 42% at 50% 100%,rgba(232,58,36,.28),transparent 58%),',
      'radial-gradient(40% 55% at 0% 70%,rgba(200,40,20,.16),transparent 70%),',
      'radial-gradient(40% 55% at 100% 70%,rgba(200,40,20,.16),transparent 70%),',
      'linear-gradient(180deg,rgba(255,80,40,.07),transparent 12%,transparent 86%,rgba(255,50,20,.12));',
      '}',
      '#chandra-sky{',
      'pointer-events:none;position:fixed;inset:0;z-index:2147483001;',
      'animation:chandra-sky-glow 5.5s ease-in-out infinite;',
      'background:',
      'radial-gradient(95% 38% at 50% -2%,rgba(90,170,255,.22),transparent 58%),',
      'radial-gradient(45% 35% at 8% 8%,rgba(70,150,255,.16),transparent 62%),',
      'radial-gradient(45% 35% at 92% 10%,rgba(70,150,255,.16),transparent 62%);',
      '}',
      '#chandra-flash{',
      'pointer-events:none;position:fixed;inset:0;z-index:2147483002;',
      'animation:chandra-flash 9.5s ease-in-out infinite;',
      'background:',
      'radial-gradient(90% 50% at 65% 0%,rgba(170,220,255,.45),transparent 55%),',
      'radial-gradient(70% 40% at 20% 5%,rgba(120,190,255,.28),transparent 50%),',
      'linear-gradient(180deg,rgba(140,200,255,.12),transparent 35%);',
      '}',
      '#chandra-thunder{',
      'pointer-events:none;position:fixed;inset:0;z-index:2147483003;',
      '}',
      '#chandra-thunder svg{width:100%;height:100%;display:block;}',
      '#chandra-thunder .vein{',
      'fill:none;stroke-linecap:round;stroke-linejoin:round;',
      'stroke:#B8E0FF;stroke-width:1.1;',
      'filter:drop-shadow(0 0 3px #5AB0FF) drop-shadow(0 0 8px #2A7CFF);',
      '}',
      '#chandra-thunder .vein-idle{',
      'animation:chandra-bolt-idle 3.4s ease-in-out infinite;',
      'opacity:.28;',
      '}',
      '#chandra-thunder .vein-a{animation:chandra-bolt-a 8.2s steps(1,end) infinite;}',
      '#chandra-thunder .vein-b{animation:chandra-bolt-b 11s steps(1,end) infinite;}',
      '#chandra-thunder .vein-c{animation:chandra-bolt-a 13.5s steps(1,end) infinite;animation-delay:3.2s;}',
      'textarea:focus,input:focus,[contenteditable="true"]:focus{',
      'box-shadow:0 0 0 1px #F05A2A,0 0 18px rgba(232,58,36,.28)!important;',
      '}',
      '::selection{background:rgba(232,58,36,.4);color:#fff;}',
      '*{scrollbar-color:#E83A24 #1A070A;}'
    ].join('')
    ;(document.head || document.documentElement).appendChild(css)
  }

  function thunderSvg() {
    // Thin branched veins — cinematic, not chunky game bolts
    return [
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">',
      '<path class="vein vein-idle" d="M12,1 L15,8 12.5,8 17,18 13.5,13 16,13 11,22"/>',
      '<path class="vein vein-idle" d="M88,2 L84,9 87,9 81,20 85,14 82,14 89,24"/>',
      '<path class="vein vein-idle" d="M48,0 L50,7 47.5,7 52,15 49,11 51,11 47,20"/>',
      '<path class="vein vein-a" d="M22,0 L26,10 22,10 30,24 25,17 28,17 20,32 24,26 22,38"/>',
      '<path class="vein vein-a" d="M30,14 L34,19 31,22"/>',
      '<path class="vein vein-b" d="M78,1 L73,12 77,12 68,28 74,20 70,20 76,36 72,30 74,42"/>',
      '<path class="vein vein-b" d="M70,16 L66,22 69,25"/>',
      '<path class="vein vein-c" d="M55,0 L52,11 55,11 48,26 53,18 50,18 56,34"/>',
      '<path class="vein vein-c" d="M6,8 L11,16 8,16 14,28"/>',
      '<path class="vein vein-b" d="M94,10 L89,20 92,20 85,34"/>',
      '</svg>'
    ].join('')
  }

  function mount() {
    stripUglyOverlays()
    injectStyles()
    var host = document.body || document.documentElement
    if (!document.getElementById('chandra-storm-layer')) {
      var storm = document.createElement('div')
      storm.id = 'chandra-storm-layer'
      storm.setAttribute('aria-hidden', 'true')
      storm.style.backgroundImage =
        "url('" +
        dsAsset('filler-bg0.jpg') +
        "'),linear-gradient(165deg,#2a0c12 0%,#1A070A 50%,#0e0406 100%)"
      host.insertBefore(storm, host.firstChild)
    }
    if (!document.getElementById('chandra-hero-layer')) {
      var wm = document.createElement('div')
      wm.id = 'chandra-hero-layer'
      wm.setAttribute('aria-hidden', 'true')
      wm.style.backgroundImage = "url('" + dsAsset('chandra-watermark.png') + "')"
      host.insertBefore(wm, host.firstChild.nextSibling)
    }
    if (!document.getElementById('chandra-rim')) {
      var rim = document.createElement('div')
      rim.id = 'chandra-rim'
      rim.setAttribute('aria-hidden', 'true')
      host.appendChild(rim)
    }
    if (!document.getElementById('chandra-sky')) {
      var sky = document.createElement('div')
      sky.id = 'chandra-sky'
      sky.setAttribute('aria-hidden', 'true')
      host.appendChild(sky)
    }
    if (!document.getElementById('chandra-flash')) {
      var flash = document.createElement('div')
      flash.id = 'chandra-flash'
      flash.setAttribute('aria-hidden', 'true')
      host.appendChild(flash)
    }
    if (!document.getElementById('chandra-thunder')) {
      var thunder = document.createElement('div')
      thunder.id = 'chandra-thunder'
      thunder.setAttribute('aria-hidden', 'true')
      thunder.innerHTML = thunderSvg()
      host.appendChild(thunder)
    }
  }

  try {
    mount()
  } catch (e) {}

  function tuneNativeBackdrop() {
    var img = document.querySelector('img[src*="filler-bg0"]')
    if (!img || img.dataset.chandraBackdrop) return
    img.dataset.chandraBackdrop = '1'
    var wrap = img.parentElement
    if (wrap) {
      wrap.style.opacity = '0.18'
      wrap.style.mixBlendMode = 'soft-light'
    }
    img.style.filter = 'saturate(1.25) brightness(1.05)'
  }

  function schedule() {
    tuneNativeBackdrop()
    var tries = 0
    var iv = setInterval(function () {
      try {
        mount()
      } catch (e) {}
      tuneNativeBackdrop()
      if (++tries > 40) clearInterval(iv)
    }, 250)
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', schedule)
  } else {
    schedule()
  }

  try {
    var THEME_VERSION = 'v12-chandra-thunder'
    var installedNow = false
    if (localStorage.getItem('kumo-theme-installed') !== THEME_VERSION) {
      var pal = {
        background: '#1A070A',
        foreground: '#F8E6E2',
        card: '#261015',
        cardForeground: '#F8E6E2',
        muted: '#32151C',
        mutedForeground: '#C99A94',
        popover: '#221014',
        popoverForeground: '#F8E6E2',
        primary: '#E83A24',
        primaryForeground: '#1A0406',
        secondary: '#4A1820',
        secondaryForeground: '#F0D0CA',
        accent: '#5C1C28',
        accentForeground: '#F0C8C0',
        border: '#5A2430',
        input: '#140508',
        ring: '#F05A2A',
        midground: '#E84520',
        composerRing: '#F05A2A',
        destructive: '#E82030',
        destructiveForeground: '#FFFFFF',
        sidebarBackground: '#120408',
        sidebarBorder: '#3A1820',
        userBubble: '#B82014',
        userBubbleBorder: '#F05A2A'
      }
      var reg = {}
      try {
        reg = JSON.parse(localStorage.getItem('hermes-desktop-user-themes-v1') || '{}') || {}
      } catch (e) {
        reg = {}
      }
      reg.chandra = {
        name: 'chandra',
        label: 'Chandra',
        description: 'Chandra — cinematic inferno (Kumobits)',
        colors: pal,
        darkColors: pal
      }
      localStorage.setItem('hermes-desktop-user-themes-v1', JSON.stringify(reg))
      localStorage.setItem('hermes-desktop-theme-v2', 'chandra')
      localStorage.setItem('hermes-desktop-mode-v1', 'dark')
      localStorage.setItem('hermes-boot-background', '#1A070A')
      localStorage.setItem('hermes-boot-color-scheme', 'dark')
      try {
        var lastProf = localStorage.getItem('hermes-desktop-active-profile-v1')
        if (lastProf && lastProf !== 'default') {
          var profRec = JSON.parse(localStorage.getItem('hermes-desktop-profile-themes-v1') || '{}') || {}
          profRec[lastProf] = 'chandra'
          localStorage.setItem('hermes-desktop-profile-themes-v1', JSON.stringify(profRec))
        }
      } catch (e) {}
      localStorage.setItem('kumo-theme-installed', THEME_VERSION)
      installedNow = true
    }
    if (installedNow && !sessionStorage.getItem('kumo-theme-reloaded')) {
      sessionStorage.setItem('kumo-theme-reloaded', '1')
      setTimeout(function () {
        try {
          location.reload()
        } catch (e) {}
      }, 350)
    }
  } catch (e) {}

  var MAP = [
    ['Hermes Agent', 'Chandra'],
    ['HERMES', 'CHANDRA'],
    ['Hermes', 'Chandra'],
    ['Kumo Agent', 'Chandra'],
    ['Nous Research', 'Kumobits'],
    ['NOUS', 'KUMOBITS']
  ]
  var HIT = /Hermes|HERMES|Kumo(?!bits)|KUMO(?!BITS)|Nous Research|NOUS/
  var SKIP = { CODE: 1, PRE: 1, SCRIPT: 1, STYLE: 1 }
  var ATTRS = ['title', 'aria-label', 'placeholder', 'alt', 'data-placeholder']

  function fix(s) {
    if (!s || !HIT.test(s)) return s
    for (var i = 0; i < MAP.length; i++) s = s.split(MAP[i][0]).join(MAP[i][1])
    s = s.replace(/Kumo(?!bits)/g, 'Chandra').replace(/KUMO(?!BITS)/g, 'CHANDRA')
    return s
  }
  function inSkipped(el) {
    for (var n = el; n; n = n.parentElement) {
      if (SKIP[n.nodeName]) return true
    }
    return false
  }
  function fixText(node) {
    var v = node.nodeValue
    var f = fix(v)
    if (f !== v) node.nodeValue = f
  }
  function fixAttrs(el) {
    for (var i = 0; i < ATTRS.length; i++) {
      var a = ATTRS[i]
      if (el.hasAttribute && el.hasAttribute(a)) {
        var v = el.getAttribute(a)
        var f = fix(v)
        if (f !== v) el.setAttribute(a, f)
      }
    }
  }
  function sweep(root) {
    if (!root) return
    if (root.nodeType === 3) {
      if (!root.parentElement || !inSkipped(root.parentElement)) fixText(root)
      return
    }
    if (root.nodeType !== 1 || SKIP[root.nodeName]) return
    fixAttrs(root)
    var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        return n.parentElement && inSkipped(n.parentElement)
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT
      }
    })
    var t
    while ((t = w.nextNode())) fixText(t)
    if (root.querySelectorAll) {
      var els = root.querySelectorAll('[title],[aria-label],[placeholder],[alt],[data-placeholder]')
      for (var i = 0; i < els.length; i++) fixAttrs(els[i])
    }
  }
  function enforceTitle() {
    var f = fix(document.title)
    if (f !== document.title) document.title = f
  }
  var mo = new MutationObserver(function (muts) {
    for (var i = 0; i < muts.length; i++) {
      var m = muts[i]
      if (m.type === 'characterData') {
        if (!m.target.parentElement || !inSkipped(m.target.parentElement)) fixText(m.target)
      } else if (m.type === 'attributes') {
        fixAttrs(m.target)
      } else {
        for (var j = 0; j < m.addedNodes.length; j++) sweep(m.addedNodes[j])
      }
    }
    enforceTitle()
  })
  mo.observe(document.documentElement, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: ATTRS
  })
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      sweep(document.body)
      enforceTitle()
    })
  } else {
    sweep(document.body)
    enforceTitle()
  }
})()
