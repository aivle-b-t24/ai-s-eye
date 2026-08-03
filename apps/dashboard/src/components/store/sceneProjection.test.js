import assert from 'node:assert/strict'
import test from 'node:test'

import {
  SEAT_SNAP_DISTANCE,
  agentDepth,
  agentScale,
  allocateRenderPositions,
  objectDepth,
  perspectiveScale,
  stabilizeTrackPosition,
  stabilizeTrackState,
} from './sceneProjection.js'

test('사람 크기는 원거리에서 근거리로 갈수록 단조롭게 커진다', () => {
  const scales = [0.2, 0.5, 0.8, 0.98].map((y) => perspectiveScale(y))

  assert.ok(scales.every((scale, index) => index === 0 || scale >= scales[index - 1]))
  assert.ok(scales[0] < scales.at(-1))
})

test('같은 발 위치에서는 YOLO bbox가 큰 사람을 더 크게 표시한다', () => {
  const small = agentScale({
    y: 0.6,
    bbox: { y1: 0.35, y2: 0.57 },
    confidence: 0.9,
    state: 'unknown',
  })
  const large = agentScale({
    y: 0.6,
    bbox: { y1: 0.15, y2: 0.57 },
    confidence: 0.9,
    state: 'unknown',
  })

  assert.ok(large > small)
})

test('bbox가 없는 시뮬레이션 고객은 기존 원근 곡선을 그대로 사용한다', () => {
  const agent = { y: 0.7, state: 'queue' }

  assert.equal(agentScale(agent), perspectiveScale(agent.y))
})

test('발 위치가 테이블 뒤면 테이블이 가리고 앞이면 사람이 가린다', () => {
  const table = {
    type: 'table',
    polygon: [[100, 400], [300, 400], [300, 600], [100, 600]],
  }
  const tableZ = objectDepth(table)

  assert.ok(agentDepth(0.5) < tableZ)
  assert.ok(agentDepth(0.7) > tableZ)
})

test('착석 고객은 150px 이내 좌석에만 붙는다', () => {
  const anchors = [{ id: 'seat-1', x: 500, y: 500 }]
  const inside = allocateRenderPositions(
    [{ id: 'inside', x: 0.5, y: 0.5 + (SEAT_SNAP_DISTANCE - 1) / 1000, state: 'seated' }],
    anchors,
  )[0]
  const outside = allocateRenderPositions(
    [{ id: 'outside', x: 0.5, y: 0.5 + (SEAT_SNAP_DISTANCE + 1) / 1000, state: 'seated' }],
    anchors,
  )[0]

  assert.equal(inside.seatAnchorId, 'seat-1')
  assert.equal(outside.seatAnchorId, null)
})

test('15px 이내 좌표 흔들림은 화면 위치를 바꾸지 않는다', () => {
  const previous = {
    x: 0.5,
    y: 0.5,
    movementStreak: 0,
  }
  const stabilized = stabilizeTrackPosition(previous, { x: 0.509, y: 0.508 })

  assert.equal(stabilized.x, 0.5)
  assert.equal(stabilized.y, 0.5)
  assert.equal(stabilized.isMoving, false)
  assert.equal(stabilized.movementStreak, 0)
})

test('유의미한 이동이 두 번 연속 확인되어야 화면 위치를 갱신한다', () => {
  const previous = {
    x: 0.5,
    y: 0.5,
    movementStreak: 0,
  }
  const first = stabilizeTrackPosition(previous, { x: 0.54, y: 0.5 })
  const second = stabilizeTrackPosition(first, { x: 0.55, y: 0.5 })

  assert.equal(first.x, 0.5)
  assert.equal(first.isMoving, false)
  assert.equal(first.movementStreak, 1)
  assert.ok(second.x > 0.5 && second.x < 0.55)
  assert.equal(second.isMoving, true)
  assert.equal(second.movementStreak, 2)
})

test('착석 고객은 기존 좌석이 범위 안이면 같은 앵커를 유지한다', () => {
  const tracks = [{ id: 'customer-1', x: 0.56, y: 0.5, state: 'seated' }]
  const seats = [
    { id: 'seat-a', x: 550, y: 500 },
    { id: 'seat-b', x: 600, y: 500 },
  ]
  const [position] = allocateRenderPositions(
    tracks,
    seats,
    { 'customer-1': 'seat-b' },
  )

  assert.equal(position.seatAnchorId, 'seat-b')
  assert.equal(position.renderX, 0.6)
})

test('정지 고객은 pose 착석 판정이 계속 누락돼도 좌석 상태를 유지한다', () => {
  const previous = { state: 'seated' }
  const observation = { state: 'unknown' }
  const position = { isMoving: false }

  const first = stabilizeTrackState(previous, observation, position)
  const second = stabilizeTrackState({ ...previous, ...first }, observation, position)
  const third = stabilizeTrackState({ ...previous, ...second }, observation, position)

  assert.equal(first.state, 'seated')
  assert.equal(second.state, 'seated')
  assert.equal(third.state, 'seated')
})

test('착석 고객이 실제로 움직이면 좌석 상태를 바로 해제한다', () => {
  const result = stabilizeTrackState(
    { state: 'seated' },
    { state: 'unknown' },
    { isMoving: true },
  )

  assert.equal(result.state, 'unknown')
})
