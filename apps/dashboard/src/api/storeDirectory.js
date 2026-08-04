import { authenticatedFetch } from './authenticatedFetch'
import {
  STORE_CHART_COLORS,
  chartColorFor,
  storeDisplayName,
  toStoreNameMap,
} from './storeNames'

export {
  STORE_CHART_COLORS,
  chartColorFor,
  storeDisplayName,
  toStoreNameMap,
}

/** 본사 관리자용 매장 마스터 목록 (`GET /api/admin/stores`). */
export async function fetchAdminStores(apiBaseUrl, { signal } = {}) {
  const response = await authenticatedFetch(`${apiBaseUrl}/api/admin/stores`, {
    signal,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `매장 목록을 불러오지 못했습니다 (${response.status})`)
  }
  const stores = await response.json()
  if (!Array.isArray(stores)) {
    throw new Error('매장 목록 응답 형식이 올바르지 않습니다')
  }
  return stores
}
