export const ONBOARDING_ZONE_TYPES = Object.freeze([
  { value: 'staff', label: '직원 작업 구역', required: false },
  { value: 'waiting', label: '고객 대기 구역', required: false },
  { value: 'entrance', label: '출입구', required: false },
  { value: 'seating', label: '좌석 구역', required: false },
])

export const REQUIRED_ONBOARDING_ZONE_TYPES = ONBOARDING_ZONE_TYPES
  .filter((zone) => zone.required)
  .map((zone) => zone.value)

export function onboardingZoneLabel(type) {
  return ONBOARDING_ZONE_TYPES.find((zone) => zone.value === type)?.label ?? type
}

function clampCoordinate(value) {
  return Math.max(0, Math.min(1000, Math.round(Number(value))))
}

export function normalizePolygon(polygon = []) {
  return polygon.map((point) => ({
    x: clampCoordinate(point.x),
    y: clampCoordinate(point.y),
  }))
}

export function validateOnboardingDraft({ imageSize, sceneObjects, floorPoints }) {
  const errors = []
  if (!imageSize?.width || !imageSize?.height) {
    errors.push('매장 대표 사진을 먼저 등록해 주세요.')
  }
  if (!sceneObjects?.some((object) => object.type === 'table')) {
    errors.push('AI가 찾은 테이블을 한 개 이상 확인해 주세요.')
  }
  if (!floorPoints || floorPoints.length < 3) {
    errors.push('바닥 영역을 꼭짓점 3개 이상으로 지정해 주세요.')
  }

  return errors
}

export function buildOnboardingPayloads({
  imageSize,
  sceneObjects,
  floorPoints,
  zones,
}) {
  const errors = validateOnboardingDraft({
    imageSize,
    sceneObjects,
    floorPoints,
    zones,
  })
  if (errors.length) throw new Error(errors[0])

  const objects = sceneObjects.map((object, index) => ({
    id: object.id || `${object.type}-${index + 1}`,
    type: object.type,
    label: object.label || (object.type === 'table' ? `테이블 ${index + 1}` : object.type),
    polygon: normalizePolygon(object.polygon),
  }))
  objects.push({
    id: 'onboarding-floor',
    type: 'floor',
    label: '매장 바닥',
    polygon: normalizePolygon(floorPoints),
  })

  return {
    scene: {
      coordinate_space: 'normalized_1000',
      image_size: imageSize,
      source: 'manual',
      objects,
      seat_anchors: [],
      projection: null,
    },
    roi: zones.length ? {
      coordinate_space: 'normalized_1000',
      image_size: imageSize,
      source: 'manual',
      zones: zones.map((zone, index) => ({
        id: zone.id || `${zone.type}-${index + 1}`,
        type: zone.type,
        label: zone.label || onboardingZoneLabel(zone.type),
        polygon: normalizePolygon(zone.polygon),
      })),
    } : null,
  }
}
