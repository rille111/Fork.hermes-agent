import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { test } from 'vitest'

import { buildRceditOptions, resolveProductIdentity, stampExeIdentity } from './set-exe-identity.mjs'

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

function makeDesktopRoot() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-exe-identity-'))
  fs.mkdirSync(path.join(root, 'assets'))
  fs.writeFileSync(path.join(root, 'assets', 'icon.ico'), 'icon')
  const exe = path.join(root, 'Hermes.exe')
  fs.writeFileSync(exe, 'exe')
  return { exe, root }
}

test('retries transient rcedit commit failures with bounded backoff', async () => {
  const { exe, root } = makeDesktopRoot()
  const delays = []
  let attempts = 0

  try {
    await stampExeIdentity(exe, root, {
      rcedit: async () => {
        attempts += 1
        if (attempts < 3) throw new Error('Unable to commit changes')
      },
      sleep: async delay => delays.push(delay)
    })

    assert.equal(attempts, 3)
    assert.equal(delays.length, 2)
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test('stops retrying after the bounded rcedit retry budget is exhausted', async () => {
  const { exe, root } = makeDesktopRoot()
  let attempts = 0

  try {
    await assert.rejects(
      stampExeIdentity(exe, root, {
        rcedit: async () => {
          attempts += 1
          throw new Error('Unable to commit changes')
        },
        sleep: async () => {}
      }),
      /Unable to commit changes/
    )
    assert.equal(attempts, 4)
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})

test('does not retry when the rcedit binary itself cannot be spawned (ENOENT/EACCES)', async () => {
  // #112544 follow-up: the npm rcedit wrapper reports a spawn failure via
  // `originalError`; that toolchain breakage is permanent, so the 3.5 s
  // transient-lock retry budget must not be spent on it.
  const { exe, root } = makeDesktopRoot()
  let attempts = 0
  const delays = []
  const spawnFailure = Object.assign(new Error('Error executing command (rcedit-x64.exe):\nspawn rcedit-x64.exe ENOENT'), {
    originalError: Object.assign(new Error('spawn rcedit-x64.exe ENOENT'), { code: 'ENOENT' })
  })

  try {
    await assert.rejects(
      stampExeIdentity(exe, root, {
        rcedit: async () => {
          attempts += 1
          throw spawnFailure
        },
        sleep: async delay => delays.push(delay)
      }),
      /ENOENT/
    )
    assert.equal(attempts, 1)
    assert.deepEqual(delays, [])
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})
