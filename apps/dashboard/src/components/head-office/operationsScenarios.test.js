import assert from 'node:assert/strict'
import test from 'node:test'

import { buildPresentationScenarios } from './operationsScenarios.js'

test('발표용 세 조건은 같은 seed와 행사 조건을 공유한다', () => {
  const scenarios = buildPresentationScenarios({
    store_id: 'store-001',
    duration_minutes: 180,
    arrivals_per_hour: 24,
    average_service_minutes: 4,
    patience_minutes: 8,
    seat_count: 16,
    dine_in_rate: 0.65,
    seed: 20260730,
  })

  assert.equal(scenarios.length, 3)
  assert.deepEqual(
    scenarios.map(({ payload }) => payload.staff_count),
    [1, 1, 2],
  )
  assert.deepEqual(
    scenarios.map(({ payload }) => payload.event_multiplier),
    [1, 1.6, 1.6],
  )
  assert.ok(scenarios.every(({ payload }) => payload.seed === 20260730))
  assert.equal(scenarios[1].payload.arrivals_per_hour, scenarios[2].payload.arrivals_per_hour)
})
