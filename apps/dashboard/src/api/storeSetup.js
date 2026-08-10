import { API_BASE_URL } from '../constants/env'
import { authenticatedFetch } from './authenticatedFetch'
import { fetchStoreState } from './storeApi'
import {
  defaultCameraId,
  evaluateNeedsOnboarding,
} from './storeSetupLogic'

export { defaultCameraId, evaluateNeedsOnboarding }

async function configExists(url) {
  const response = await authenticatedFetch(url)
  return response.ok
}

export async function fetchStoreSetupStatus(storeId) {
  if (!storeId) {
    return {
      needsOnboarding: false,
      hasSceneConfig: false,
      hasRoiConfig: false,
      state: null,
    }
  }

  const cameraId = defaultCameraId(storeId)
  const sceneUrl = `${API_BASE_URL}/api/stores/${storeId}/cameras/${cameraId}/scene-config`
  const roiUrl = `${API_BASE_URL}/api/stores/${storeId}/cameras/${cameraId}/roi-config`

  const [hasSceneConfig, hasRoiConfig, state] = await Promise.all([
    configExists(sceneUrl),
    configExists(roiUrl),
    fetchStoreState(storeId).catch(() => null),
  ])

  return {
    hasSceneConfig,
    hasRoiConfig,
    state,
    needsOnboarding: evaluateNeedsOnboarding({
      hasSceneConfig,
      hasRoiConfig,
      state,
    }),
  }
}
