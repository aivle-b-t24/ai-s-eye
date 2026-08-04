import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildOnboardingPayloads,
  validateOnboardingDraft,
} from './storeOnboarding.js'

const imageSize = { width: 1920, height: 1080 }
const sceneObjects = [{
  id: 'table-1',
  type: 'table',
  label: '테이블 1',
  polygon: [
    { x: 100.3, y: 100.8 },
    { x: 300, y: 100 },
    { x: 300, y: 300 },
  ],
}]
const floorPoints = [
  { x: 50, y: 50 },
  { x: 950, y: 50 },
  { x: 950, y: 950 },
  { x: 50, y: 950 },
]
const zones = ['staff', 'waiting', 'entrance'].map((type, index) => ({
  id: `${type}-1`,
  type,
  label: type,
  polygon: [
    { x: 100 + index * 200, y: 600 },
    { x: 220 + index * 200, y: 600 },
    { x: 220 + index * 200, y: 800 },
  ],
}))

test('buildOnboardingPayloads maps the wizard draft to scene and ROI contracts', () => {
  const payloads = buildOnboardingPayloads({
    imageSize,
    sceneObjects,
    floorPoints,
    zones,
  })

  assert.equal(payloads.scene.source, 'manual')
  assert.equal(payloads.scene.objects.length, 2)
  assert.equal(payloads.scene.objects[0].polygon[0].x, 100)
  assert.equal(payloads.scene.objects[0].polygon[0].y, 101)
  assert.equal(payloads.scene.objects[1].type, 'floor')
  assert.equal(payloads.roi.source, 'manual')
  assert.deepEqual(
    payloads.roi.zones.map((zone) => zone.type),
    ['staff', 'waiting', 'entrance'],
  )
})

test('operational zones are optional for digital twin onboarding', () => {
  const errors = validateOnboardingDraft({
    imageSize,
    sceneObjects,
    floorPoints,
    zones: [],
  })
  const payloads = buildOnboardingPayloads({
    imageSize,
    sceneObjects,
    floorPoints,
    zones: [],
  })

  assert.deepEqual(errors, [])
  assert.equal(payloads.roi, null)
})
