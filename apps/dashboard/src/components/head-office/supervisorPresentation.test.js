import assert from 'node:assert/strict'
import test from 'node:test'

import {
  orderDataLabel,
  orderDataMode,
  timelineIntervalForPeriod,
} from './supervisorPresentation.js'

test('24시간만 시간 단위이고 나머지 기간은 일 단위다', () => {
  assert.equal(timelineIntervalForPeriod('24h'), '1h')
  assert.equal(timelineIntervalForPeriod('7d'), '1d')
  assert.equal(timelineIntervalForPeriod('30d'), '1d')
  assert.equal(timelineIntervalForPeriod('custom'), '1d')
})

test('주문 출처를 합성·혼합으로 구분한다', () => {
  const syntheticStore = {
    order_summary: { data_sources: ['synthetic_order_simulator'] },
  }
  const observedStore = {
    order_summary: { data_sources: ['order_event'] },
  }

  assert.equal(orderDataMode([syntheticStore]), 'synthetic')
  assert.equal(orderDataMode([syntheticStore, observedStore]), 'mixed')
  assert.equal(orderDataLabel('synthetic'), '합성 데모 주문')
})
