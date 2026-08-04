import assert from 'node:assert/strict'
import test from 'node:test'

import {
  chartColorFor,
  storeDisplayName,
  toStoreNameMap,
} from './storeNames.js'

test('storeDisplayName은 마스터 이름을 쓰고 없으면 store_id를 쓴다', () => {
  assert.equal(
    storeDisplayName('store-001', { 'store-001': '동명점' }),
    '동명점',
  )
  assert.equal(storeDisplayName('store-003', {}), 'store-003')
})

test('toStoreNameMap은 id→name 맵을 만든다', () => {
  assert.deepEqual(
    toStoreNameMap([
      { id: 'store-001', name: '동명점' },
      { id: 'store-002', name: '수완점' },
    ]),
    {
      'store-001': '동명점',
      'store-002': '수완점',
    },
  )
})

test('chartColorFor는 인덱스를 순환한다', () => {
  assert.equal(chartColorFor(0), chartColorFor(6))
  assert.notEqual(chartColorFor(0), chartColorFor(1))
})
