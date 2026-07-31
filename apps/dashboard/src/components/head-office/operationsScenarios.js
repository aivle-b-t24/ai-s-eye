export const PRESENTATION_SCENARIOS = [
  {
    key: 'normalOne',
    shortLabel: '평상시 · 1명',
    name: '평상시 · 직원 1명',
    eventMultiplier: 1,
    staffCount: 1,
  },
  {
    key: 'eventOne',
    shortLabel: '행사 · 1명',
    name: '행사 ×1.6 · 직원 1명',
    eventMultiplier: 1.6,
    staffCount: 1,
  },
  {
    key: 'eventTwo',
    shortLabel: '행사 · 2명',
    name: '행사 ×1.6 · 직원 2명',
    eventMultiplier: 1.6,
    staffCount: 2,
  },
]

export function buildPresentationScenarios(conditions) {
  return PRESENTATION_SCENARIOS.map((scenario) => ({
    key: scenario.key,
    payload: {
      ...conditions,
      name: scenario.name,
      event_multiplier: scenario.eventMultiplier,
      staff_count: scenario.staffCount,
      service_variability: 0.25,
    },
  }))
}
