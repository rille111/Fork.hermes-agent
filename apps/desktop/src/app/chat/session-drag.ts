/**
 * Sidebar session drag — the session RESOLVER over the shared pointer drag
 * session (pane-shell drag-session.ts). Same machinery as a pane drag
 * (threshold, rAF moves, snapshots, Esc-as-top-layer with synchronous
 * teardown), session-specific targeting:
 *
 *   - a chat zone's TAB STRIP  → stack: open the session as a tab at the
 *     divider's slot (the strip caret shows it);
 *   - a chat zone's EDGE band  → split: open the session as a tile docked on
 *     that edge (the zone sheet morphs to the half);
 *   - a chat zone's CENTER / the composer → link: insert an `@session` chip
 *     into that surface's composer (ChatDropOverlay owns the visual);
 *   - a sidebar PROJECT row (`data-sessions-project`) → re-home the session
 *     via `session.workspace.move` (same as the row's "Move to project" menu);
 *   - anything else (sidebar empty space, terminal, gutters) → deny.
 *
 * Zones that don't host a chat surface are NOT targets — the overlay never
 * lights them, so a release there must not commit either (one truth).
 *
 * This replaced the native-HTML5 drag + SessionTileDropBridge: riding the
 * native DnD layer meant macOS's cancel snap-back animation, a `dragend`
 * held hostage until that animation finished, an Esc the page never even
 * saw, and window-level armor against react-dnd/dnd-kit. A pointer session
 * has none of those failure modes. Native DnD remains only at the true OS
 * boundary (Finder file drops). Known trade: a session can no longer be
 * dragged into a separate BrowserWindow (native DnD was the only transport
 * that crossed windows).
 */

import type { PointerEvent as ReactPointerEvent } from 'react'

import { queryAllVisible } from '@/components/pane-shell/pane-visibility'
import { findGroup } from '@/components/pane-shell/tree/model'
import {
  type DoubleTapContext,
  rectContains,
  slotBefore,
  snapshotStrips,
  snapshotZones,
  startDragSession,
  type StripSnapshot,
  subZonePosition
} from '@/components/pane-shell/tree/renderer/drag-session'
import {
  $layoutTree,
  $treeDragging,
  type DropHint,
  isMainStripPane,
  isSessionStripPane,
  revealTreePane,
  SESSION_TILE_DRAG
} from '@/components/pane-shell/tree/store'
import type { EngineZone, ZoneRect } from '@/components/pane-shell/tree/zones-engine'
import { translateNow } from '@/i18n'
import { notify, notifyError } from '@/store/notifications'
import { $projectTree, moveSessionToProject, projectIdForCwd, projectRootCwd } from '@/store/projects'
import { openSessionTile, type TileDock } from '@/store/session-states'

import { requestComposerInsertRefs } from './composer/focus'
import { type SessionDragPayload, sessionInlineRef, sessionLabel } from './composer/inline-refs'

/** A chat surface's drag-start geometry: the anchor pane id it advertises
 *  (`data-session-anchor`) and the composer a link drop routes to
 *  (`data-composer-target`). */
interface SurfaceSnapshot {
  anchor: string
  composerTarget: string
  rect: ZoneRect
}

const snapRect = (el: HTMLElement): ZoneRect => {
  const r = el.getBoundingClientRect()

  return { left: r.left, top: r.top, right: r.right, bottom: r.bottom }
}

/** Chat surfaces the pointer can land on. Inactive tabs are excluded: they stay
 *  mounted with their layout box intact, so their rect is identical to the
 *  visible tab's and a hit-test alone would pick whichever came first. */
function snapshotSurfaces(): SurfaceSnapshot[] {
  return queryAllVisible('[data-session-anchor]').map(el => ({
    anchor: el.dataset.sessionAnchor || 'workspace',
    composerTarget: el.dataset.composerTarget || 'main',
    rect: snapRect(el)
  }))
}

interface ProjectDropTarget {
  el: HTMLElement
  id: string
  label: string
  rect: ZoneRect
}

/** Folder-bearing project rows currently on screen. Home has no folder, so it
 *  is never a drop target — same rule as the session menu's Move-to-project
 *  submenu. */
function snapshotProjectDrops(excludedProjectId: null | string): ProjectDropTarget[] {
  const tree = $projectTree.get()

  return [...document.querySelectorAll<HTMLElement>('[data-sessions-project]')].flatMap(el => {
    const id = el.dataset.sessionsProject?.trim() || ''
    const project = tree.find(node => node.id === id)

    if (!id || id === excludedProjectId || !project || project.isNoProject || !projectRootCwd(project)) {
      return []
    }

    return [{ el, id, label: project.label, rect: snapRect(el) }]
  })
}

function setProjectDropHot(el: HTMLElement | null, hot: HTMLElement | null): HTMLElement | null {
  if (hot === el) {
    return hot
  }

  if (hot) {
    hot.style.background = ''
    hot.style.outline = ''
  }

  if (el) {
    el.style.background = 'var(--ui-row-active-background)'
    el.style.outline = '1px solid var(--ui-accent)'
  }

  return el
}

const RAIL_PAD = 8
const RAIL_ITEM_H = 32

function folderProjects(excludedProjectId: null | string) {
  return $projectTree
    .get()
    .filter(project => project.id !== excludedProjectId && !project.isNoProject && projectRootCwd(project))
}

function createProjectDropRail(
  projects: ReturnType<typeof folderProjects>,
  sidebar: ZoneRect
): { destroy: () => void; targets: ProjectDropTarget[] } {
  const root = document.createElement('div')
  const width = Math.max(0, sidebar.right - sidebar.left)

  root.dataset.sessionProjectRail = ''
  root.style.cssText =
    `position:fixed;left:${sidebar.left}px;top:${sidebar.top}px;width:${width}px;` +
    'z-index:9998;pointer-events:none;padding:8px;box-sizing:border-box;' +
    'background:var(--ui-sidebar-surface-background,var(--dt-card));' +
    'color:var(--ui-text-primary);font-size:0.75rem;'

  const heading = document.createElement('div')

  heading.textContent = translateNow('sidebar.projects.moveToProject')
  heading.style.cssText =
    'position:absolute;left:8px;top:-18px;color:var(--ui-text-tertiary);font-weight:500;white-space:nowrap'
  root.appendChild(heading)

  const targets = projects.map((project, index) => {
    const el = document.createElement('div')
    const top = sidebar.top + RAIL_PAD + index * RAIL_ITEM_H
    const bottom = top + RAIL_ITEM_H

    el.textContent = project.label
    el.style.cssText = `height:${RAIL_ITEM_H}px;display:flex;align-items:center;padding:0 8px;`
    root.appendChild(el)

    return {
      el,
      id: project.id,
      label: project.label,
      rect: { bottom, left: sidebar.left + RAIL_PAD, right: sidebar.right - RAIL_PAD, top }
    }
  })

  document.body.appendChild(root)

  return { destroy: () => root.remove(), targets }
}

function resolveProjectDropTargets(
  sidebar: ZoneRect | null,
  excludedProjectId: null | string
): { destroy: () => void; targets: ProjectDropTarget[] } {
  const visible = snapshotProjectDrops(excludedProjectId)
  const folders = folderProjects(excludedProjectId)

  if (visible.length >= 2 || !sidebar) {
    return { destroy: () => undefined, targets: visible }
  }

  const others = folders.filter(project => project.id !== visible[0]?.id)

  if (!others.length) {
    return { destroy: () => undefined, targets: visible }
  }

  return createProjectDropRail(others, sidebar)
}

function sessionsZoneRect(zones: EngineZone[]): ZoneRect | null {
  const tree = $layoutTree.get()

  if (!tree) {
    return null
  }

  return zones.find(zone => findGroup(tree, zone.id)?.panes.includes('sessions'))?.rect ?? null
}

const PROJECT_DROP_HINT: DropHint = { kind: 'group' }

/** A session may land in any zone hosting a MAIN tile — another chat stack, a
 *  Browser tile, a page — never the sidebar/terminal zones. Returns the pane a
 *  stack anchors to, plus whether the zone hosts a CHAT surface (only those
 *  offer the link-to-composer center; a preview zone's center stacks). */
function tileZoneHost(groupId: string): { chat: boolean; pane: string } | null {
  const tree = $layoutTree.get()
  const panes = tree ? (findGroup(tree, groupId)?.panes ?? []) : []
  const pane = panes.find(isSessionStripPane) ?? panes.find(isMainStripPane)

  return pane ? { chat: panes.some(isSessionStripPane), pane } : null
}

/**
 * Begin dragging a session — a sidebar row OR a tile's own tab (same drop
 * language either way: stack, split, or composer link). Sub-threshold releases
 * stay ordinary clicks, so `opts.onTap` (activate the tile) and `opts.double`
 * (hide the tab bar) ride the tab's gestures; Esc aborts instantly. A stack/
 * split commits through `openSessionTile`, which OPENS a new tile from a sidebar
 * row and MOVES the existing one when its tab is the drag source.
 */
export function startSessionDrag(
  payload: SessionDragPayload,
  e: ReactPointerEvent<HTMLElement>,
  opts?: { double?: DoubleTapContext; onTap?: () => void }
) {
  const sourceProjectId = payload.cwd?.trim() ? projectIdForCwd(payload.cwd) : null
  let zones: EngineZone[] = []
  let strips: StripSnapshot[] = []
  let surfaces: SurfaceSnapshot[] = []
  let composers: ZoneRect[] = []
  let zoneHost = new Map<string, ReturnType<typeof tileZoneHost>>()
  let projects: ProjectDropTarget[] = []
  let hotProject: HTMLElement | null = null
  let destroyProjectRail: () => void = () => undefined

  // Commit intent, updated per resolved move (the machinery flushes the final
  // move before commit, so these always match the released-at position).
  let split: { anchor: string; before?: null | string; pos: TileDock } | null = null
  let link: null | string = null
  let move: ProjectDropTarget | null = null

  // The drag SOURCE (sidebar row or tile tab). Captured synchronously — React
  // clears `currentTarget` after the pointerdown handler returns, but this runs
  // inside it. Dimmed while lifted so the source reads as "picked up" — the
  // same in-place feedback pane-tab drags use, replacing the old cursor chip.
  const source = e.currentTarget
  const restoreOpacity = source?.style.opacity ?? ''

  startDragSession(e, {
    double: opts?.double,
    ghost: { label: sessionLabel(payload) },
    onTap: opts?.onTap,

    onEngage() {
      zones = snapshotZones()
      strips = snapshotStrips()
      surfaces = snapshotSurfaces()
      composers = queryAllVisible('[data-slot="composer-root"]').map(snapRect)
      zoneHost = new Map(zones.map(zone => [zone.id, tileZoneHost(zone.id)]))
      const resolved = resolveProjectDropTargets(sessionsZoneRect(zones), sourceProjectId)

      projects = resolved.targets
      destroyProjectRail = resolved.destroy
      source?.style.setProperty('opacity', '0.45')
      // The same sentinel the zone overlay + chat surfaces key off — the
      // whole drop language (sheets, pills, caret, link overlay) lights up.
      $treeDragging.set(SESSION_TILE_DRAG)
    },

    onEnd() {
      hotProject = setProjectDropHot(null, hotProject)
      destroyProjectRail()
      destroyProjectRail = () => undefined

      if (source) {
        source.style.opacity = restoreOpacity
      }
    },

    resolveMove(x, y): DropHint | null {
      const project = projects.find(target => rectContains(target.rect, x, y)) ?? null

      if (project) {
        split = null
        link = null
        move = project
        hotProject = setProjectDropHot(project.el, hotProject)

        return PROJECT_DROP_HINT
      }

      hotProject = setProjectDropHot(null, hotProject)
      move = null

      const zone = zones.find(z => rectContains(z.rect, x, y))
      const host = zone ? zoneHost.get(zone.id) : null

      if (!zone || !host) {
        split = null
        link = null

        return null
      }

      // The zone's TAB STRIP stacks the session at the divider's slot.
      const strip = strips.find(s => s.groupId === zone.id && rectContains(s.rect, x, y))

      if (strip) {
        // Exclude the tile's OWN tab from the slots so re-dropping it in its
        // home strip reorders cleanly (a no-op for a sidebar-row drag).
        const stack = slotBefore(strip.slots, x, `session-tile:${payload.id}`)
        split = { anchor: host.pane, before: stack.before, pos: 'center' }
        link = null

        return { kind: 'group', groupId: zone.id, groupIds: [zone.id], pos: 'center', stack }
      }

      // The composer (and everything in it) is always the link/attach drop;
      // elsewhere the shared radial targeting decides center vs edge.
      const pos = composers.some(rect => rectContains(rect, x, y)) ? 'center' : subZonePosition(zones, zone.id, x, y)
      const surface = surfaces.find(s => rectContains(s.rect, x, y))

      if (pos === 'center' && host.chat) {
        split = null
        link = surface?.composerTarget ?? 'main'
      } else if (pos === 'center') {
        // A preview/page zone has no composer to link to — its center stacks
        // the session as a tab, same as dropping on the strip's tail.
        split = { anchor: host.pane, pos: 'center' }
        link = null
      } else {
        split = { anchor: surface?.anchor ?? host.pane, pos }
        link = null
      }

      return { kind: 'group', groupId: zone.id, groupIds: [zone.id], pos }
    },

    onCommit() {
      if (move) {
        const target = move

        void moveSessionToProject(payload.id, target.id, payload.profile)
          .then(() =>
            notify({
              durationMs: 2_000,
              kind: 'success',
              message: translateNow('sidebar.projects.movedTo', target.label)
            })
          )
          .catch(err => notifyError(err, translateNow('sidebar.projects.moveFailed')))
      } else if (split) {
        openSessionTile(payload.id, split.pos, split.anchor, split.before)
        // A tile for this session may already exist (openSessionTile is
        // idempotent — e.g. persisted from an earlier run): a drop must never
        // feel dead, so front/unhide/un-dismiss it either way.
        revealTreePane(`session-tile:${payload.id}`)
      } else if (link) {
        // The "link to chat" drop: an @session chip in that surface's composer.
        requestComposerInsertRefs([sessionInlineRef(payload)], { target: link })
      }
    }
  })
}
