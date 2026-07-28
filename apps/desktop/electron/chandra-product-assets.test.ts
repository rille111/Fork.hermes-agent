import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { test } from 'vitest'

const indexHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8')
const productShim = readFileSync(new URL('../public/kumo-shim.js', import.meta.url), 'utf8')

test('desktop loads the versioned Chandra product shim', () => {
  assert.match(indexHtml, /<script defer src="\.\/kumo-shim\.js\?v=42"><\/script>/)
  assert.match(productShim, /SHIM_BUILD = 'v42-chandra-embercrust'/)
})

test('Chandra product shim retains the source-controlled ambience', () => {
  assert.match(productShim, /function startStormSky\(/)
  assert.match(productShim, /function startPixelFire\(/)
  assert.match(productShim, /function startEmberCrust\(/)
  assert.match(productShim, /function startPixelBolts\(/)
  assert.match(productShim, /function ensureAmbience\(/)
})
