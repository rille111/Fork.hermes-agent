import { afterEach, describe, expect, it } from 'vitest'

import type { SessionInfo } from '@/hermes'

import { clearMovedSessions, markSessionMoved, sessionRecency } from './workspace-groups'

const session = (id: string, lastActive: number): SessionInfo =>
  ({ id, last_active: lastActive, started_at: 0 }) as unknown as SessionInfo

afterEach(() => {
  clearMovedSessions()
})

describe('sessionRecency after a project move', () => {
  it('reads plain last_active for a session that never moved', () => {
    expect(sessionRecency(session('s1', 1_000))).toBe(1_000)
  })

  it('floats a just-moved session above a more recently active one', () => {
    const moved = session('s1', 1_000)
    const busy = session('s2', 5_000)

    markSessionMoved('s1', 9_000)

    expect(sessionRecency(moved)).toBe(9_000)
    expect([busy, moved].sort((a, b) => sessionRecency(b) - sessionRecency(a))[0]).toBe(moved)
  })

  it('keeps real activity when it is newer than the move', () => {
    markSessionMoved('s1', 2_000)

    expect(sessionRecency(session('s1', 8_000))).toBe(8_000)
  })

  // The whole reason the marker is client-side: the backend leaves last_active
  // alone, so a fresh row from `session.list` must not sink the moved session.
  it('survives an authoritative refresh that restores the original row', () => {
    markSessionMoved('s1', 9_000)

    expect(sessionRecency(session('s1', 1_000))).toBe(9_000)
  })

  it('floats only the session that moved', () => {
    markSessionMoved('s1', 9_000)

    expect(sessionRecency(session('s2', 1_000))).toBe(1_000)
  })

  it('forgets moves once cleared', () => {
    markSessionMoved('s1', 9_000)
    clearMovedSessions()

    expect(sessionRecency(session('s1', 1_000))).toBe(1_000)
  })
})
