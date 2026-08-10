export function defaultCameraId(storeId) {
  return `${storeId}-cam1`
}

/**
 * scene/ROI가 없고 vision state도 없거나 empty일 때만 온보딩이 필요하다.
 * (store-002처럼 파일 기반 비전만 있는 매장은 state.source !== 'empty'로 통과)
 */
export function evaluateNeedsOnboarding({
  hasSceneConfig,
  hasRoiConfig,
  state,
}) {
  if (hasSceneConfig || hasRoiConfig) return false
  if (state && state.source !== 'empty') return false
  return true
}
