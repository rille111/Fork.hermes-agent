// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'

import { applyChandraBootstrap, CHANDRA_BOOTSTRAP_BUILD } from './chandra-bootstrap'

describe('applyChandraBootstrap', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-chandra-brand')
    document.body.innerHTML = ''
  })

  it('persists the Chandra theme without rewriting user-visible content', () => {
    document.body.innerHTML = `
      <article title="Hermes Agent comparison">
        User asked about Hermes and Nous Research.
      </article>
    `
    const before = document.body.innerHTML

    applyChandraBootstrap()

    expect(document.body.innerHTML).toBe(before)
    expect(localStorage.getItem('hermes-desktop-theme-v2')).toBe('chandra')
    expect(localStorage.getItem('hermes-desktop-mode-v1')).toBe('dark')
    expect(localStorage.getItem('hermes-boot-background')).toBe('#070B18')
    expect(localStorage.getItem('hermes-boot-color-scheme')).toBe('dark')
    expect(document.documentElement.dataset.chandraBrand).toBe(CHANDRA_BOOTSTRAP_BUILD)
  })
})
