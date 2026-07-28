import assert from 'node:assert/strict'

import { test } from 'vitest'

import { applyLegacyProductEnvAliases } from './product-env'

test('legacy product variables populate their Hermes equivalents', () => {
  const env: NodeJS.ProcessEnv = {
    KUMO_HOME: 'C:\\Kumo',
    KUMO_DESKTOP_REMOTE_URL: 'https://example.test',
    KUMO_DESKTOP_REMOTE_TOKEN: 'secret',
    KUMO_DESKTOP_APP_NAME: 'Chandra',
    KUMO_DESKTOP_USER_DATA_DIR: 'C:\\ChandraData'
  }

  applyLegacyProductEnvAliases(env)

  assert.equal(env.HERMES_HOME, 'C:\\Kumo')
  assert.equal(env.HERMES_DESKTOP_REMOTE_URL, 'https://example.test')
  assert.equal(env.HERMES_DESKTOP_REMOTE_TOKEN, 'secret')
  assert.equal(env.HERMES_DESKTOP_APP_NAME, 'Chandra')
  assert.equal(env.HERMES_DESKTOP_USER_DATA_DIR, 'C:\\ChandraData')
})

test('canonical variables win even when explicitly empty', () => {
  const env: NodeJS.ProcessEnv = {
    KUMO_HOME: 'C:\\Kumo',
    HERMES_HOME: '',
    KUMO_DESKTOP_APP_NAME: 'Chandra',
    HERMES_DESKTOP_APP_NAME: 'Hermes'
  }

  applyLegacyProductEnvAliases(env)

  assert.equal(env.HERMES_HOME, '')
  assert.equal(env.HERMES_DESKTOP_APP_NAME, 'Hermes')
})
