import type { BrowserWindow } from 'electron'

const DEFAULT_PRODUCT_NAME = 'Hermes'

/** Keep a custom product name from being replaced by the renderer page title. */
export function installCustomProductTitle(
  win: BrowserWindow,
  appName: string,
  defaultProductName = DEFAULT_PRODUCT_NAME
): void {
  if (!appName || appName === defaultProductName) {
    return
  }

  const applyTitle = () => {
    if (!win.isDestroyed()) {
      win.setTitle(appName)
    }
  }

  applyTitle()
  win.on('page-title-updated', (event) => {
    event.preventDefault()
    applyTitle()
  })
}
