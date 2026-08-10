export async function consumeSse(response, onEvent) {
  if (!response.ok) throw new Error(`운영 Agent 요청 실패 (${response.status})`)
  if (!response.body) throw new Error('운영 Agent 스트림을 읽을 수 없습니다.')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let lastEvent = null

  const consumeBlock = (block) => {
    const data = block
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n')
    if (!data) return
    const parsed = JSON.parse(data)
    lastEvent = parsed
    onEvent(parsed)
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() ?? ''
    blocks.forEach(consumeBlock)
    if (done) break
  }
  if (buffer.trim()) consumeBlock(buffer)
  return lastEvent
}

export function frameIndexAtMinute(frames, minute) {
  if (!frames?.length) return 0
  let low = 0
  let high = frames.length - 1
  while (low <= high) {
    const middle = Math.floor((low + high) / 2)
    if (frames[middle].at_minute <= minute) low = middle + 1
    else high = middle - 1
  }
  return Math.max(0, Math.min(high, frames.length - 1))
}

export function recentEventsAtMinute(events, minute, limit = 4) {
  return (events ?? [])
    .filter((event) => event.at_minute <= minute)
    .slice(-limit)
    .reverse()
}

export function nextOrderAtMinute(events, minute) {
  return (events ?? []).find(
    (event) => event.event_type === 'order_received' && event.at_minute > minute,
  ) ?? null
}

export function nextPlaybackMinute(currentMinute, durationMinutes) {
  return Math.min(currentMinute + durationMinutes / 450, durationMinutes)
}
