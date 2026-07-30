import assert from 'node:assert/strict'
import { test } from 'vitest'

import {
  buildRceditOptions,
  resolveProductIdentity
} from './set-exe-identity.mjs'

test('resolveProductIdentity carries the desktop application version', () => {
  assert.deepEqual(resolveProductIdentity({}, '0.17.0'), {
    productName: 'Hermes',
    companyName: 'Nous Research',
    legalCopyright: 'Copyright (c) 2026 Nous Research',
    version: '0.17.0'
  })
})

test('buildRceditOptions stamps application rather than Electron runtime versions', () => {
  const identity = resolveProductIdentity(
    {
      HERMES_DESKTOP_APP_NAME: 'Chandra',
      HERMES_DESKTOP_COMPANY_NAME: 'Kumobits',
      HERMES_DESKTOP_LEGAL_COPYRIGHT: 'Copyright (c) 2026 Kumobits'
    },
    '0.17.0'
  )

  assert.deepEqual(buildRceditOptions(identity, 'C:/icons/chandra.ico'), {
    icon: 'C:/icons/chandra.ico',
    'file-version': '0.17.0',
    'product-version': '0.17.0',
    'version-string': {
      ProductName: 'Chandra',
      CompanyName: 'Kumobits',
      FileDescription: 'Chandra',
      LegalCopyright: 'Copyright (c) 2026 Kumobits'
    }
  })
})
