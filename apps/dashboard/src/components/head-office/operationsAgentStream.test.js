import assert from 'node:assert/strict'
import test from 'node:test'

import {
  consumeSse,
  frameIndexAtMinute,
  nextOrderAtMinute,
  nextPlaybackMinute,
  recentEventsAtMinute,
} from './operationsAgentStream.js'

test('SSE 청크가 나뉘어 와도 이벤트를 순서대로 읽는다', async () => {
  const chunks = [
    'data: {"event":"run_started"}\n\n' + 'data: {"event":',
    '"run_completed","result":{"ok":true}}\n\n',
  ]
  const response = new Response(new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(new TextEncoder().encode(chunk)))
      controller.close()
    },
  }))
  const seen = []
  const last = await consumeSse(response, (event) => seen.push(event.event))

  assert.deepEqual(seen, ['run_started', 'run_completed'])
  assert.equal(last.result.ok, true)
})

test('같은 재생 시각에 두 결과의 프레임 위치를 독립적으로 찾는다', () => {
  const frames = [{ at_minute: 0 }, { at_minute: 0.5 }, { at_minute: 2 }]
  assert.equal(frameIndexAtMinute(frames, 1.2), 1)
  assert.equal(frameIndexAtMinute(frames, 99), 2)
})

test('현재 시각 기준 최근 이벤트와 다음 주문을 찾는다', () => {
  const events = [
    { event_type: 'order_received', at_minute: 1, order_id: '1' },
    { event_type: 'preparing', at_minute: 2, order_id: '1' },
    { event_type: 'order_received', at_minute: 3, order_id: '2' },
  ]
  assert.deepEqual(
    recentEventsAtMinute(events, 2.5).map((event) => event.order_id),
    ['1', '1'],
  )
  assert.equal(nextOrderAtMinute(events, 2.5).order_id, '2')
})

test('100ms 450회면 3시간 시뮬레이션이 정확히 45초에 끝난다', () => {
  let minute = 0
  for (let tick = 0; tick < 450; tick += 1) {
    minute = nextPlaybackMinute(minute, 180)
  }

  assert.equal(minute, 180)
  assert.equal(nextPlaybackMinute(minute, 180), 180)
})
