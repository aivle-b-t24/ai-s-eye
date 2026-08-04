import assert from 'node:assert/strict'
import test from 'node:test'

import {
  defaultCameraId,
  evaluateNeedsOnboarding,
} from './storeSetupLogic.js'

test('defaultCameraId는 storeId-cam1 형식을 쓴다', () => {
  assert.equal(defaultCameraId('store-003'), 'store-003-cam1')
})

test('scene 또는 ROI가 있으면 온보딩이 필요 없다', () => {
  assert.equal(
    evaluateNeedsOnboarding({
      hasSceneConfig: true,
      hasRoiConfig: false,
      state: null,
    }),
    false,
  )
  assert.equal(
    evaluateNeedsOnboarding({
      hasSceneConfig: false,
      hasRoiConfig: true,
      state: { source: 'empty' },
    }),
    false,
  )
})

test('실비전 state가 있으면 설정이 없어도 온보딩을 건너뛴다', () => {
  assert.equal(
    evaluateNeedsOnboarding({
      hasSceneConfig: false,
      hasRoiConfig: false,
      state: { source: 'cafe_replay', visible_person_count: 3 },
    }),
    false,
  )
})

test('설정 없고 state가 없거나 empty면 온보딩이 필요하다', () => {
  assert.equal(
    evaluateNeedsOnboarding({
      hasSceneConfig: false,
      hasRoiConfig: false,
      state: null,
    }),
    true,
  )
  assert.equal(
    evaluateNeedsOnboarding({
      hasSceneConfig: false,
      hasRoiConfig: false,
      state: { source: 'empty', visible_person_count: 0 },
    }),
    true,
  )
})
