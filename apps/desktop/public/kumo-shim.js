(function () {
  var SHIM_BUILD = 'v18-chandra-source-native'
  if (window.__kumoShimBuild === SHIM_BUILD) return
  window.__kumoShimBuild = SHIM_BUILD
  window.__kumoShim = true

  // Source owns Chandra's colors, surfaces, and backdrop. This compatibility
  // shim now has one job: keep the local product identity consistent in text
  // that still arrives from the upstream Hermes renderer/backend.
  try {
    localStorage.setItem('hermes-desktop-theme-v2', 'chandra')
    localStorage.setItem('hermes-desktop-mode-v1', 'dark')
    localStorage.setItem('hermes-boot-background', '#070B18')
    localStorage.setItem('hermes-boot-color-scheme', 'dark')
  } catch (e) {}

  document.documentElement.dataset.chandraBrand = SHIM_BUILD

  var MAP = [
    ['Hermes Agent', 'Chandra'],
    ['HERMES', 'CHANDRA'],
    ['Hermes', 'Chandra'],
    ['Kumo Agent', 'Chandra'],
    ['Nous Research', 'Kumobits'],
    ['NOUS', 'KUMOBITS']
  ]
  var HIT = /Hermes|HERMES|\bKumo\b|\bKUMO\b|Nous Research|NOUS/
  var SKIP = { CODE: 1, PRE: 1, SCRIPT: 1, STYLE: 1 }
  var ATTRS = ['title', 'aria-label', 'placeholder', 'alt', 'data-placeholder']

  function fix(value) {
    if (!value || !HIT.test(value)) return value
    var next = value
    for (var i = 0; i < MAP.length; i++) next = next.split(MAP[i][0]).join(MAP[i][1])
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
  })

  observer.observe(document.documentElement, {
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
