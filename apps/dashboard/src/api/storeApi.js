// Centralized Store API Client
import { API_BASE_URL } from '../constants/env'
import { authenticatedFetch } from './authenticatedFetch'

export async function fetchStoreState(storeId) {
  const response = await authenticatedFetch(`${API_BASE_URL}/api/stores/${storeId}/state`)
  if (!response.ok) {
    throw new Error(`API 요청 실패 (${response.status})`)
  }
  return response.json()
}

export async function fetchStoreEta(storeId) {
  const response = await authenticatedFetch(`${API_BASE_URL}/api/stores/${storeId}/eta`)
  if (!response.ok) return null
  return response.json()
}

export async function fetchStoreMenus(storeId) {
  const response = await authenticatedFetch(`${API_BASE_URL}/api/stores/${storeId}/menus`)
  if (!response.ok) return { menus: [] }
  return response.json()
}

export async function fetchStorePolicies(storeId) {
  const response = await authenticatedFetch(`${API_BASE_URL}/api/stores/${storeId}/policies`)
  if (!response.ok) return { policies: [] }
  return response.json()
}

export async function fetchStoreSettings(storeId) {
  const response = await authenticatedFetch(`${API_BASE_URL}/api/stores/${storeId}/settings`)
  if (!response.ok) return null
  return response.json()
}

export async function saveStoreSettings(storeId, maxCapacity) {
  const response = await authenticatedFetch(
    `${API_BASE_URL}/api/stores/${storeId}/settings`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max_capacity: maxCapacity }),
    },
  )
  if (!response.ok) {
    throw new Error(`수용 인원 저장 실패 (${response.status})`)
  }
  return response.json()
}
