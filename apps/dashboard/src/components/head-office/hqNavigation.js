export const HQ_NAVIGATION_ITEMS = Object.freeze([
  Object.freeze({ id: 'hq-overview', label: '운영 개요' }),
  Object.freeze({ id: 'hq-simulation', label: '운영 시뮬레이션' }),
  Object.freeze({ id: 'hq-ai', label: 'AI 인사이트' }),
  Object.freeze({ id: 'hq-accounts', label: '계정 관리' }),
])

export function hqSectionFromHash(hash = '') {
  const section = String(hash).replace(/^#/, '')
  return HQ_NAVIGATION_ITEMS.some(({ id }) => id === section)
    ? section
    : HQ_NAVIGATION_ITEMS[0].id
}

export function currentHqSection() {
  return hqSectionFromHash(
    typeof window === 'undefined' ? '' : window.location.hash,
  )
}
