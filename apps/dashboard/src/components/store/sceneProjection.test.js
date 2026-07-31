import assert from 'node:assert/strict'
import test from 'node:test'

import {
  SEAT_SNAP_DISTANCE,
  allocateRenderPositions,
  perspectiveScale,
} from './sceneProjection.js'

test('사람 크기는 원거리에서 근거리로 갈수록 단조롭게 커진다', () => {
  const scales = [0.2, 0.5, 0.8, 0.98].map((y) => perspectiveScale(y))

  assert.ok(scales.every((scale, index) => index === 0 || scale >= scales[index - 1]))
  assert.ok(scales[0] < scales.at(-1))
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
