import assert from 'node:assert/strict'
import test from 'node:test'

import {
  hasInsightData,
  insightSourceLabel,
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

test('AI 분석 가능한 매장과 집계가 전혀 없는 매장을 구분한다', () => {
  assert.equal(hasInsightData({ traffic_summary: { peak_visible_person_count: 3 } }), true)
  assert.equal(hasInsightData({ order_summary: { total_order_count: 12 } }), true)
  assert.equal(hasInsightData({
    traffic_summary: null,
    order_summary: {
      total_order_count: 0,
      order_event_count: 0,
      data_sources: [],
      latest_status_counts: {},
      top_menu_items: [],
    },
    video_summary: null,
  }), false)
})

test('Gemini 장애 시 규칙 기반 대체 분석임을 명확히 표시한다', () => {
  assert.equal(insightSourceLabel('gemini'), '데모 데이터 기반 분석')
  assert.equal(insightSourceLabel('rule_based_fallback'), '규칙 기반 대체 분석')
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
