import assert from 'node:assert/strict'
import test from 'node:test'

import {
  HQ_NAVIGATION_ITEMS,
  hqSectionFromHash,
} from './hqNavigation.js'

test('본사 메뉴는 운영·시뮬레이션·AI·계정 관리 4개 화면으로 구성한다', () => {
  assert.deepEqual(
    HQ_NAVIGATION_ITEMS.map(({ id }) => id),
    ['hq-overview', 'hq-simulation', 'hq-ai', 'hq-accounts'],
  )
})

test('지원하는 해시는 해당 화면을 열고 나머지는 운영 개요로 돌아간다', () => {
  assert.equal(hqSectionFromHash('#hq-simulation'), 'hq-simulation')
  assert.equal(hqSectionFromHash('hq-ai'), 'hq-ai')
  assert.equal(hqSectionFromHash('#hq-stores'), 'hq-overview')
  assert.equal(hqSectionFromHash(''), 'hq-overview')
})
