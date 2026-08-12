export const MIN_STAFF_COUNT = 1
export const MAX_STAFF_COUNT = 10

function clampStaffCount(value) {
  const number = Number.isFinite(Number(value)) ? Math.round(Number(value)) : MIN_STAFF_COUNT
  return Math.min(Math.max(number, MIN_STAFF_COUNT), MAX_STAFF_COUNT)
}

export function updateStaffingCondition(conditions, key, value) {
  const count = clampStaffCount(value)
  if (key === 'current_staff_count') {
    return {
      ...conditions,
      current_staff_count: count,
      max_staff_count: Math.max(count, conditions.max_staff_count),
    }
  }
  if (key === 'max_staff_count') {
    return {
      ...conditions,
      current_staff_count: Math.min(conditions.current_staff_count, count),
      max_staff_count: count,
    }
  }
  return conditions
}

export function getRecommendedSimulation(comparison) {
  if (!comparison) return null
  const recommended = comparison.recommended_staff_count
  if (comparison.event_one?.scenario?.staff_count === recommended) {
    return comparison.event_one
  }
  if (comparison.event_two?.scenario?.staff_count === recommended) {
    return comparison.event_two
  }
  return comparison.event_recommended ?? null
}

export function staffingOptionState(option, comparison) {
  if (option.staff_count === comparison.recommended_staff_count) {
    return comparison.capacity_sufficient ? 'recommended' : 'capacity-limit'
  }
  if (option.staff_count === comparison.current_staff_count) return 'current'
  return option.meets_targets ? 'sufficient' : 'insufficient'
}
