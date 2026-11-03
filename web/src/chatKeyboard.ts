type ChatKey = Pick<KeyboardEvent, 'key' | 'shiftKey' | 'isComposing' | 'keyCode' | 'repeat' | 'preventDefault'>

/** Enter sends; composition confirmation and Shift+Enter belong to editing. */
export function handleChatKeydown(event: ChatKey, send: () => unknown, composing = false): void {
  if (event.key !== 'Enter' || event.shiftKey || composing || event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  if (!event.repeat) void send()
}
