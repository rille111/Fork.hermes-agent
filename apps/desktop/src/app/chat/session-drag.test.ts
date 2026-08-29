import type { PointerEvent as ReactPointerEvent } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { group, split } from '@/components/pane-shell/tree/model'
import { $layoutTree } from '@/components/pane-shell/tree/store'
import { $projectTree, moveSessionToProject } from '@/store/projects'
import { openSessionTile } from '@/store/session-states'

import { requestComposerInsertRefs } from './composer/focus'
import { startSessionDrag } from './session-drag'

/**
 * A session drop resolves its target by rect-testing the chat surfaces in the
 * document. A tab group keeps inactive tabs MOUNTED with their layout box
 * intact, so a background tab's rect is identical to the foreground tab's —
 * the drop has to land on the tab the user can actually see.
 */

vi.mock('@/store/session-states', () => ({ openSessionTile: vi.fn() }))
vi.mock('./composer/focus', () => ({ requestComposerInsertRefs: vi.fn() }))
vi.mock('@/store/notifications', () => ({ notify: vi.fn(), notifyError: vi.fn() }))
vi.mock('@/store/projects', async () => {
  const { atom } = await import('nanostores')

  return {
    $projectTree: atom([]),
    moveSessionToProject: vi.fn(() => Promise.resolve()),
    projectIdForCwd: (cwd: string) => (cwd.includes('Temporary') ? 'p_temp' : null),
    projectRootCwd: (project?: { path?: null | string }) => (project?.path || '').trim()
  }
})

const ZONE = { left: 0, top: 0, right: 1000, bottom: 800 }
const COMPOSER = { left: 100, top: 700, right: 900, bottom: 780 }

const stubRect = (el: Element, box: { left: number; top: number; right: number; bottom: number }) => {
  el.getBoundingClientRect = () =>
    ({ ...box, width: box.right - box.left, height: box.bottom - box.top, x: box.left, y: box.top }) as DOMRect
}

/** The workspace tab kept alive behind an active session tile tab. */
function mountStackedTabs() {
  document.body.innerHTML = `
    <div data-tree-group="g1">
      <div data-pane-hidden>
        <div data-session-anchor="workspace" data-composer-target="main">
          <div data-slot="composer-root"></div>
        </div>
      </div>
      <div>
        <div data-session-anchor="session-tile:visible" data-composer-target="tile:visible">
          <div data-slot="composer-root"></div>
        </div>
      </div>
    </div>
    <div id="row"></div>
  `

  stubRect(document.querySelector('[data-tree-group]')!, ZONE)

  for (const surface of document.querySelectorAll('[data-session-anchor]')) {
    stubRect(surface, ZONE)
  }

  for (const composer of document.querySelectorAll('[data-slot="composer-root"]')) {
    stubRect(composer, COMPOSER)
  }

  $layoutTree.set(group(['workspace', 'session-tile:visible'], { id: 'g1' }))

  return document.getElementById('row')!
}

/** Press on `source`, drag to (x, y), release. The drag session flushes its
 *  pending move synchronously on release, so no frame wait is needed. */
function startTestDrag(source: HTMLElement, payload: { cwd?: string } = {}) {
  startSessionDrag({ id: 'dragged', profile: 'default', title: 'Dragged chat', ...payload }, {
    button: 0,
    clientX: 0,
    clientY: 0,
    currentTarget: source,
    pointerId: 1
  } as unknown as ReactPointerEvent<HTMLElement>)
}

function movePointer(x: number, y: number) {
  window.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: x, clientY: y }))
}

function releasePointer(x: number, y: number) {
  window.dispatchEvent(new MouseEvent('pointerup', { bubbles: true, clientX: x, clientY: y }))
}

const nextFrame = () => new Promise<void>(resolve => requestAnimationFrame(() => resolve()))

function dragTo(source: HTMLElement, x: number, y: number, payload: { cwd?: string } = {}) {
  startTestDrag(source, payload)

  movePointer(x, y)
  releasePointer(x, y)
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  document.body.innerHTML = ''
  $layoutTree.set(null)
})

describe('session drop targeting across stacked tabs', () => {
  it('links into the visible tab’s composer, not the tab kept alive behind it', () => {
    const row = mountStackedTabs()

    dragTo(row, 500, 740)

    expect(requestComposerInsertRefs).toHaveBeenCalledWith(expect.anything(), { target: 'tile:visible' })
  })

  it('docks a split against the visible tab’s pane', () => {
    const row = mountStackedTabs()

    dragTo(row, 980, 400)

    expect(openSessionTile).toHaveBeenCalledWith('dragged', 'right', 'session-tile:visible', undefined)
    expect(requestComposerInsertRefs).not.toHaveBeenCalled()
  })

  it('commits nothing over a zone that hosts no chat surface', () => {
    mountStackedTabs()
    $layoutTree.set(group(['terminal'], { id: 'g1' }))

    dragTo(document.getElementById('row')!, 500, 740)

    expect(requestComposerInsertRefs).not.toHaveBeenCalled()
    expect(openSessionTile).not.toHaveBeenCalled()
  })

  // Standing side chrome hosts no main tile, so a session has nowhere to land
  // there. That refusal is load-bearing twice over: the sidebar row runs the
  // reorder off the SAME press, so the deny is what leaves the list to it,
  // and ZoneDropOverlay keys off the same test to stay dark over those zones
  // instead of outlining a drop that would only be refused.
  it('commits nothing over the sidebar, leaving the region to the reorder', () => {
    mountStackedTabs()
    $layoutTree.set(group(['sessions'], { id: 'g1' }))

    dragTo(document.getElementById('row')!, 120, 400)

    expect(requestComposerInsertRefs).not.toHaveBeenCalled()
    expect(openSessionTile).not.toHaveBeenCalled()
    expect(moveSessionToProject).not.toHaveBeenCalled()
  })
})

describe('session drop onto a sidebar project', () => {
  const PROJECT = { left: 8, top: 80, right: 270, bottom: 112 }

  function mountSidebarWithProject(id = 'p_health', label = 'Health', path: null | string = 'C:/proj/Health') {
    document.body.innerHTML = `
      <div data-tree-group="g1">
        <div data-sessions-project="${id}">${label}</div>
        <div id="row"></div>
      </div>
    `
    stubRect(document.querySelector('[data-tree-group]')!, { left: 0, top: 0, right: 280, bottom: 800 })
    stubRect(document.querySelector('[data-sessions-project]')!, PROJECT)
    $layoutTree.set(group(['sessions'], { id: 'g1' }))
    $projectTree.set([{ id, isNoProject: id === '__no_project__', label, path, repos: [], sessionCount: 0 }])

    return document.getElementById('row')!
  }

  afterEach(() => {
    $projectTree.set([])
  })

  it('re-homes the session when dropped on another project row', () => {
    const row = mountSidebarWithProject()

    dragTo(row, 120, 96)

    expect(moveSessionToProject).toHaveBeenCalledWith('dragged', 'p_health', 'default')
    expect(openSessionTile).not.toHaveBeenCalled()
    expect(requestComposerInsertRefs).not.toHaveBeenCalled()
  })

  it('does not re-home a session when released over its current project', () => {
    document.body.innerHTML = `
      <div data-tree-group="g1">
        <div data-sessions-project="p_temp"><div id="row"></div></div>
        <div data-sessions-project="p_health">Health</div>
      </div>
    `
    stubRect(document.querySelector('[data-tree-group]')!, { left: 0, top: 0, right: 280, bottom: 800 })
    stubRect(document.querySelector('[data-sessions-project="p_temp"]')!, {
      left: 0,
      top: 0,
      right: 280,
      bottom: 100
    })
    stubRect(document.querySelector('[data-sessions-project="p_health"]')!, {
      left: 0,
      top: 100,
      right: 280,
      bottom: 140
    })
    $layoutTree.set(group(['sessions'], { id: 'g1' }))
    $projectTree.set([
      { id: 'p_temp', label: 'Temporary', path: 'C:/proj/Temporary', repos: [], sessionCount: 0 },
      { id: 'p_health', label: 'Health', path: 'C:/proj/Health', repos: [], sessionCount: 0 }
    ])

    dragTo(document.getElementById('row')!, 120, 50, { cwd: 'C:/proj/Temporary/worktree' })

    expect(moveSessionToProject).not.toHaveBeenCalled()
  })

  it('shows a valid drag cursor over a project target', async () => {
    const row = mountSidebarWithProject()

    startTestDrag(row)
    movePointer(120, 96)
    await nextFrame()

    expect(document.body.style.cursor).toBe('grabbing')
    releasePointer(120, 96)
  })

  it('does not move onto the folderless Home bucket', () => {
    const row = mountSidebarWithProject('__no_project__', 'Home', null)

    dragTo(row, 120, 96)

    expect(moveSessionToProject).not.toHaveBeenCalled()
  })

  it('opens a project rail when only the entered project is tagged', () => {
    document.body.innerHTML = `
      <div data-tree-group="g1">
        <div data-sessions-project="p_temp">Temporary</div>
        <div id="row"></div>
      </div>
    `
    stubRect(document.querySelector('[data-tree-group]')!, { left: 0, top: 0, right: 280, bottom: 800 })
    stubRect(document.querySelector('[data-sessions-project]')!, { left: 0, top: 0, right: 280, bottom: 800 })
    $layoutTree.set(group(['sessions'], { id: 'g1' }))
    $projectTree.set([
      { id: 'p_temp', label: 'Temporary', path: 'C:/proj/Temporary', repos: [], sessionCount: 0 },
      { id: 'p_health', label: 'Health', path: 'C:/proj/Health', repos: [], sessionCount: 0 }
    ])

    dragTo(document.getElementById('row')!, 140, 20)

    expect(moveSessionToProject).toHaveBeenCalledWith('dragged', 'p_health', 'default')
    expect(document.querySelector('[data-session-project-rail]')).toBeNull()
  })

  it('anchors the project rail to the sessions zone in a custom layout', async () => {
    document.body.innerHTML = `
      <div data-tree-group="g-files"></div>
      <div data-tree-group="g-sessions">
        <div data-sessions-project="p_temp">Temporary</div>
        <div id="row"></div>
      </div>
    `
    stubRect(document.querySelector('[data-tree-group="g-files"]')!, { left: 0, top: 0, right: 1000, bottom: 800 })
    stubRect(document.querySelector('[data-tree-group="g-sessions"]')!, {
      left: 1000,
      top: 0,
      right: 1280,
      bottom: 800
    })
    stubRect(document.querySelector('[data-sessions-project]')!, { left: 1000, top: 0, right: 1280, bottom: 800 })
    $layoutTree.set(
      split('row', [group(['files'], { id: 'g-files' }), group(['sessions'], { id: 'g-sessions' })])
    )
    $projectTree.set([
      { id: 'p_temp', label: 'Temporary', path: 'C:/proj/Temporary', repos: [], sessionCount: 0 },
      { id: 'p_health', label: 'Health', path: 'C:/proj/Health', repos: [], sessionCount: 0 }
    ])

    startTestDrag(document.getElementById('row')!, { cwd: 'C:/proj/Temporary' })
    movePointer(1010, 10)
    await nextFrame()

    const rail = document.querySelector<HTMLElement>('[data-session-project-rail]')

    expect(rail?.style.left).toBe('1000px')
    releasePointer(1010, 10)
  })
})
