import { API_BASE_URL } from '../constants/env'
import { authenticatedFetch } from './authenticatedFetch'

export async function uploadStoreMedia(storeId, file) {
  const body = new FormData()
  body.append('file', file)
  const response = await authenticatedFetch(
    `${API_BASE_URL}/api/stores/${storeId}/media`,
    { method: 'POST', body },
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    const message = detail?.detail ?? `미디어 업로드 실패 (${response.status})`
    throw new Error(typeof message === 'string' ? message : '미디어 업로드 실패')
  }
  return response.json()
}

export async function listStoreMedia(storeId) {
  const response = await authenticatedFetch(
    `${API_BASE_URL}/api/stores/${storeId}/media`,
  )
  if (!response.ok) return []
  return response.json()
}

export async function createAnalysisJob(storeId, mediaId) {
  const response = await authenticatedFetch(
    `${API_BASE_URL}/api/stores/${storeId}/analysis-jobs`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(mediaId ? { media_id: mediaId } : {}),
    },
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    const message = detail?.detail ?? `분석 job 생성 실패 (${response.status})`
    throw new Error(typeof message === 'string' ? message : '분석 job 생성 실패')
  }
  return response.json()
}
