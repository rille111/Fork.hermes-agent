import { textWithoutEmbeddedImages } from '@/lib/embedded-images'

import { chatMessageText } from './parts'
import type { ChatMessage, ChatMessagePart } from './types'

const USER_CONTEXT_TAIL_RE = /(?:^|\n)--- (?:Attached Context|Context Warnings) ---[\s\S]*$/i
const USER_SCREENSHOT_TAIL_RE = /(?:\s*\[screenshot\]\s*)+$/i

/** Reduce local, projected, and persisted forms of one user turn to its visible prompt. */
export function comparableUserMessageText(text: string): string {
  return textWithoutEmbeddedImages(text)
    .replaceAll(String.fromCharCode(13), '')
    .replace(USER_CONTEXT_TAIL_RE, '')
    .replace(/\n?\[Image attached(?: at)?:[\s\S]*?\]/gi, '')
    .replace(/\n?\[IMAGE:[\s\S]*?\]/gi, '')
    .replace(/\n?@image:[^\s]+/gi, '')
    .replace(/\n?@file:[^\s]+/gi, '')
    .replace(/\n?\[The user (?:sent|attached) an image[\s\S]*?\]/gi, '')
    .replace(/\n?\[(?:If you need a closer look|You can examine it)[\s\S]*?\]/gi, '')
    .replace(USER_SCREENSHOT_TAIL_RE, '')
    .trim()
}

const validTimelineBoundary = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value > 0

const earliestBoundary = (...values: (number | undefined)[]) => {
  const valid = values.filter(validTimelineBoundary)

  return valid.length ? Math.min(...valid) : undefined
}

const latestBoundary = (...values: (number | undefined)[]) => {
  const valid = values.filter(validTimelineBoundary)

  return valid.length ? Math.max(...valid) : undefined
}

const normalizedTimelineText = (message: ChatMessage) => chatMessageText(message).replace(/\s+/g, ' ').trim()

const assistantTimelineMatch = (stored: ChatMessage, local: ChatMessage) => {
  if (stored.id === local.id) {
    return true
  }

  const localToolIds = new Set(
    local.parts
      .filter(part => part.type === 'tool-call')
      .map(part => (part.type === 'tool-call' ? part.toolCallId : ''))
  )

  const toolMatch = stored.parts.some(part => part.type === 'tool-call' && localToolIds.has(part.toolCallId))

  if (toolMatch) {
    return true
  }

  const storedText = normalizedTimelineText(stored)

  return Boolean(storedText) && storedText === normalizedTimelineText(local)
}

const timelinePartMatch = (stored: ChatMessagePart, local: ChatMessagePart) => {
  if (stored.type !== local.type) {
    return false
  }

  if (stored.type === 'tool-call' && local.type === 'tool-call') {
    return stored.toolCallId === local.toolCallId
  }

  if ((stored.type === 'text' || stored.type === 'reasoning') && local.type === stored.type) {
    return stored.text.replace(/\s+/g, ' ').trim() === local.text.replace(/\s+/g, ' ').trim()
  }

  return false
}

/** Keep richer live timing when durable hydration has only one timestamp per row. */
function reconcileLocalAssistantTimeline(nextMessages: ChatMessage[], currentMessages: ChatMessage[]): ChatMessage[] {
  const localAssistants = currentMessages.filter(message => message.role === 'assistant' && !message.hidden)
  const matches = new Map<number, ChatMessage>()
  let localCursor = localAssistants.length - 1

  for (let nextIndex = nextMessages.length - 1; nextIndex >= 0; nextIndex -= 1) {
    const message = nextMessages[nextIndex]

    if (message.role !== 'assistant' || message.hidden) {
      continue
    }

    for (let localIndex = localCursor; localIndex >= 0; localIndex -= 1) {
      const local = localAssistants[localIndex]

      if (assistantTimelineMatch(message, local)) {
        matches.set(nextIndex, local)
        localCursor = localIndex - 1

        break
      }
    }
  }

  return nextMessages.map((message, messageIndex) => {
    const local = matches.get(messageIndex)

    if (!local) {
      return message
    }

    const unusedLocalParts = new Set(local.parts.map((_, index) => index))

    const parts = message.parts.map(part => {
      const localIndex = local.parts.findIndex(
        (candidate, index) => unusedLocalParts.has(index) && timelinePartMatch(part, candidate)
      )

      if (localIndex === -1) {
        return part
      }

      unusedLocalParts.delete(localIndex)
      const localPart = local.parts[localIndex]

      return {
        ...part,
        completedAt: latestBoundary(part.completedAt, localPart.completedAt),
        timestamp: earliestBoundary(part.timestamp, localPart.timestamp)
      } as ChatMessagePart
    })

    return {
      ...message,
      completedAt: latestBoundary(message.completedAt, local.completedAt, ...parts.map(part => part.completedAt)),
      parts,
      timestamp: earliestBoundary(message.timestamp, local.timestamp, ...parts.map(part => part.timestamp))
    }
  })
}

export function preserveLocalAssistantErrors(
  nextMessages: ChatMessage[],
  currentMessages: ChatMessage[]
): ChatMessage[] {
  nextMessages = reconcileLocalAssistantTimeline(nextMessages, currentMessages)
  const localById = new Map(currentMessages.map(message => [message.id, message]))

  const mergedNextMessages = nextMessages.map(message => {
    if (message.role !== 'assistant' || message.error || message.hidden) {
      return message
    }

    const local = localById.get(message.id)

    if (!local || local.role !== 'assistant' || !local.error || local.hidden) {
      return message
    }

    return {
      ...message,
      error: local.error,
      pending: false
    }
  })

  const existingIds = new Set(mergedNextMessages.map(message => message.id))
  const normalize = (value: string) => comparableUserMessageText(value).replace(/\s+/g, ' ')

  const currentUsers = currentMessages
    .map((message, index) => ({ index, message }))
    .filter(({ message }) => message.role === 'user' && !message.hidden)

  const authoritativeUsers = mergedNextMessages.filter(message => message.role === 'user' && !message.hidden)

  const errorsToPreserve: Array<{
    matchedUserId?: string
    message: ChatMessage
    precedingUser: ChatMessage | null
    userFromTail: number
  }> = []

  for (let index = 0; index < currentMessages.length; index += 1) {
    const message = currentMessages[index]

    if (message.role === 'assistant' && message.error && !message.hidden && !existingIds.has(message.id)) {
      const precedingUserOrdinal = currentUsers.findLastIndex(user => user.index < index)
      const precedingUser = precedingUserOrdinal >= 0 ? currentUsers[precedingUserOrdinal].message : null

      errorsToPreserve.push({
        message: { ...message, pending: false },
        precedingUser,
        userFromTail: precedingUserOrdinal >= 0 ? currentUsers.length - precedingUserOrdinal - 1 : -1
      })
    }
  }

  if (errorsToPreserve.length === 0) {
    return mergedNextMessages
  }

  // Align from the transcript tail, not by the first matching text. A repeated
  // prompt must not move the newest local error underneath an older equal turn.
  for (const localError of errorsToPreserve) {
    if (!localError.precedingUser || localError.userFromTail < 0) {
      continue
    }

    const candidate = authoritativeUsers.at(-(localError.userFromTail + 1))

    if (
      candidate &&
      normalize(chatMessageText(candidate)) === normalize(chatMessageText(localError.precedingUser)) &&
      (candidate.attachmentRefs ?? []).join('\n') === (localError.precedingUser.attachmentRefs ?? []).join('\n')
    ) {
      localError.matchedUserId = candidate.id
    }
  }

  const result: ChatMessage[] = []
  const consumedErrors = new Set<string>()

  for (const message of mergedNextMessages) {
    result.push(message)

    if (message.role === 'user' && !message.hidden) {
      for (const localError of errorsToPreserve) {
        if (!consumedErrors.has(localError.message.id) && localError.matchedUserId === message.id) {
          result.push(localError.message)
          consumedErrors.add(localError.message.id)
        }
      }
    }
  }

  for (const localError of errorsToPreserve) {
    if (!consumedErrors.has(localError.message.id)) {
      if (localError.precedingUser && !existingIds.has(localError.precedingUser.id)) {
        result.push(localError.precedingUser)
        existingIds.add(localError.precedingUser.id)
      }

      result.push(localError.message)
    }
  }

  return result
}

export function branchGroupForUser(userMessage: ChatMessage): string {
  return `branch:${userMessage.id}`
}
