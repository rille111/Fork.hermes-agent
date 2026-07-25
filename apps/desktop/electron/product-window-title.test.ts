import assert from 'node:assert/strict'

import type { BrowserWindow } from 'electron'
import { test } from 'vitest'

import { installCustomProductTitle } from './product-window-title'

type PageTitleEvent = { preventDefault(): void }
type PageTitleListener = (event: PageTitleEvent) => void

function fakeWindow() {
  let destroyed = false
  let listener: PageTitleListener | undefined
  const titles: string[] = []

  const win = {
    isDestroyed: () => destroyed,
    setTitle: (title: string) => titles.push(title),
    on: (event: string, callback: PageTitleListener) => {
      if (event === 'page-title-updated') {
        listener = callback
      }

      return win
    }
  } as unknown as BrowserWindow

  return {
    win,
    titles,
    destroy: () => {
      destroyed = true
    },
    pageTitleUpdated: (event: PageTitleEvent) => listener?.(event),
    hasListener: () => Boolean(listener)
  }
}

test('custom product title survives renderer title updates', () => {
  const fixture = fakeWindow()
  let prevented = false

  installCustomProductTitle(fixture.win, 'Chandra')
  fixture.pageTitleUpdated({ preventDefault: () => (prevented = true) })

  assert.deepEqual(fixture.titles, ['Chandra', 'Chandra'])
  assert.equal(prevented, true)
})

test('upstream default keeps Electron page-title behavior unchanged', () => {
  const fixture = fakeWindow()

  installCustomProductTitle(fixture.win, 'Hermes')

  assert.deepEqual(fixture.titles, [])
  assert.equal(fixture.hasListener(), false)
})

test('custom title is not written after the window is destroyed', () => {
  const fixture = fakeWindow()
  installCustomProductTitle(fixture.win, 'Chandra')

  fixture.destroy()
  fixture.pageTitleUpdated({ preventDefault() {} })

  assert.deepEqual(fixture.titles, ['Chandra'])
})
