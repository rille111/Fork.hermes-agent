export const CHANDRA_BOOTSTRAP_BUILD = 'v42-chandra-source-bootstrap'

interface ChandraBootstrapOptions {
  root?: HTMLElement
  storage?: Pick<Storage, 'setItem'>
}

/** Apply Chandra's first-party theme defaults without touching rendered content. */
export function applyChandraBootstrap(options: ChandraBootstrapOptions = {}): void {
  const root = options.root ?? document.documentElement

  try {
    const storage = options.storage ?? window.localStorage
    storage.setItem('hermes-desktop-theme-v2', 'chandra')
    storage.setItem('hermes-desktop-mode-v1', 'dark')
    storage.setItem('hermes-boot-background', '#070B18')
    storage.setItem('hermes-boot-color-scheme', 'dark')
  } catch {
    // Storage may be unavailable in restricted renderer contexts.
  }

  root.dataset.chandraBrand = CHANDRA_BOOTSTRAP_BUILD
}
