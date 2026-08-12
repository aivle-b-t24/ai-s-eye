import assert from 'node:assert/strict'
import test from 'node:test'

import {
  getRecommendedSimulation,
  staffingOptionState,
  updateStaffingCondition,
} from './operationsStaffing.js'

test('현재 인원이 최대 인원을 넘으면 최대 인원을 함께 올린다', () => {
  const result = updateStaffingCondition(
    { current_staff_count: 1, max_staff_count: 4 },
    'current_staff_count',
    6,
  )

  assert.deepEqual(result, { current_staff_count: 6, max_staff_count: 6 })
})

test('최대 인원을 현재 인원 아래로 내리면 현재 인원도 맞춘다', () => {
  const result = updateStaffingCondition(
    { current_staff_count: 5, max_staff_count: 8 },
    'max_staff_count',
    3,
  )

  assert.deepEqual(result, { current_staff_count: 3, max_staff_count: 3 })
})

test('중간 인원이 권장되면 별도 권장 시뮬레이션을 선택한다', () => {
  const comparison = {
    recommended_staff_count: 3,
    event_one: { scenario: { staff_count: 1 } },
    event_two: { scenario: { staff_count: 6 } },
    event_recommended: { scenario: { staff_count: 3 } },
  }

  assert.equal(getRecommendedSimulation(comparison).scenario.staff_count, 3)
})

test('최대 인원으로도 목표 미달이면 경고 상태로 표시한다', () => {
  const comparison = {
    current_staff_count: 1,
    recommended_staff_count: 4,
    capacity_sufficient: false,
  }
  const option = { staff_count: 4, meets_targets: false }

  assert.equal(staffingOptionState(option, comparison), 'capacity-limit')
})
