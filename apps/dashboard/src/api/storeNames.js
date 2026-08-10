/** 차트용 색상. 매장 수와 무관하게 인덱스만으로 고른다. */
export const STORE_CHART_COLORS = [
  '#0f62fe',
  '#8a3ffc',
  '#007d79',
  '#b28600',
  '#da1e28',
  '#198038',
]

export function storeDisplayName(storeId, storeNames = {}) {
  if (!storeId) return ''
  return storeNames[storeId] ?? storeId
}

export function chartColorFor(index) {
  return STORE_CHART_COLORS[index % STORE_CHART_COLORS.length]
}

export function toStoreNameMap(stores = []) {
  return Object.fromEntries(
    stores
      .filter((store) => store?.id)
      .map((store) => [store.id, store.name || store.id]),
  )
}
