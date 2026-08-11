export const SUPERVISOR_STORE_IDS = ['store-001', 'store-002']

export function timelineIntervalForPeriod(periodKey) {
  return periodKey === '24h' ? '1h' : '1d'
}

export function orderDataMode(stores = []) {
  const sources = new Set(
    stores.flatMap((store) => store.order_summary?.data_sources ?? []),
  )
  const hasSynthetic = sources.has('synthetic_order_simulator')
  const hasOrderEvent = sources.has('order_event')
  if (hasSynthetic && hasOrderEvent) return 'mixed'
  if (hasSynthetic) return 'synthetic'
  if (hasOrderEvent) return 'order-event'
  return 'empty'
}

export function orderDataLabel(mode) {
  if (mode === 'synthetic') return '합성 데모 주문'
  if (mode === 'mixed') return '합성·외부 주문 혼합'
  if (mode === 'order-event') return '외부 주문 이벤트'
  return '주문 데이터 없음'
}

export function hasInsightData(store) {
  if (!store || typeof store !== 'object') return false
  if (store.traffic_summary || store.video_summary) return true

  const orders = store.order_summary
  if (!orders || typeof orders !== 'object') return false
  return Number(orders.total_order_count ?? 0) > 0
    || Number(orders.order_event_count ?? 0) > 0
    || (orders.data_sources?.length ?? 0) > 0
    || (orders.top_menu_items?.length ?? 0) > 0
    || Object.values(orders.latest_status_counts ?? {}).some((count) => Number(count) > 0)
}
