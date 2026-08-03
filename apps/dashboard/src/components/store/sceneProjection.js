export const DEFAULT_PERSPECTIVE = {
  far_y: 260,
  near_y: 960,
  far_scale: 0.68,
  near_scale: 1.3,
}

export const SEAT_SNAP_DISTANCE = 150
export const SEAT_RELEASE_DISTANCE = 220
export const POSITION_DEAD_ZONE = 0.015
export const POSITION_SMOOTHING_ALPHA = 0.55
export const MOVEMENT_CONFIRMATION_SAMPLES = 2
export const DEFAULT_BBOX_SCALE = {
  reference_height: 0.32,
  weight: 0.68,
  minimum: 0.55,
  maximum: 1.65,
}

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum)
}

export function perspectiveScale(y, perspective = DEFAULT_PERSPECTIVE) {
  const depthY = y * 1000
  const range = Math.max(perspective.near_y - perspective.far_y, 1)
  const depth = clamp((depthY - perspective.far_y) / range, 0, 1)
  const easedDepth = depth ** 1.18
  return perspective.far_scale
    + (perspective.near_scale - perspective.far_scale) * easedDepth
}

export function agentScale(
  agent,
  perspective = DEFAULT_PERSPECTIVE,
  calibration = DEFAULT_BBOX_SCALE,
) {
  const depthScale = perspectiveScale(agent.renderY ?? agent.y, perspective)
  const bboxHeight = (agent.bbox?.y2 ?? 0) - (agent.bbox?.y1 ?? 0)
  if (!Number.isFinite(bboxHeight) || bboxHeight <= 0) return depthScale

  const referenceHeight = Math.max(
    calibration.reference_height ?? DEFAULT_BBOX_SCALE.reference_height,
    0.01,
  )
  const bboxScale = clamp(
    bboxHeight / referenceHeight,
    calibration.minimum ?? DEFAULT_BBOX_SCALE.minimum,
    calibration.maximum ?? DEFAULT_BBOX_SCALE.maximum,
  )
  const confidence = clamp(agent.confidence ?? 1, 0, 1)
  const confidenceWeight = 0.35 + confidence * 0.65
  const postureWeight = agent.state === 'seated' ? 0.35 : 1
  const weight = clamp(
    (calibration.weight ?? DEFAULT_BBOX_SCALE.weight)
      * confidenceWeight
      * postureWeight,
    0,
    1,
  )
  return clamp(
    depthScale * (1 - weight) + bboxScale * weight,
    calibration.minimum ?? DEFAULT_BBOX_SCALE.minimum,
    calibration.maximum ?? DEFAULT_BBOX_SCALE.maximum,
  )
}

export function objectDepth(object) {
  const frontY = Math.max(...object.polygon.map(([, y]) => y))
  return frontY + (object.type === 'occluder' ? 115 : 85)
}

export function agentDepth(y) {
  return Math.round(y * 1000) + 100
}

export function stabilizeTrackPosition(previous, observation) {
  if (!previous) {
    return {
      x: observation.x,
      y: observation.y,
      rawX: observation.x,
      rawY: observation.y,
      movementStreak: 0,
      isMoving: false,
    }
  }

  const distance = Math.hypot(
    observation.x - previous.x,
    observation.y - previous.y,
  )
  if (distance <= POSITION_DEAD_ZONE) {
    return {
      x: previous.x,
      y: previous.y,
      rawX: observation.x,
      rawY: observation.y,
      movementStreak: 0,
      isMoving: false,
    }
  }

  const movementStreak = (previous.movementStreak ?? 0) + 1
  if (movementStreak < MOVEMENT_CONFIRMATION_SAMPLES) {
    return {
      x: previous.x,
      y: previous.y,
      rawX: observation.x,
      rawY: observation.y,
      movementStreak,
      isMoving: false,
    }
  }

  return {
    x: previous.x + (observation.x - previous.x) * POSITION_SMOOTHING_ALPHA,
    y: previous.y + (observation.y - previous.y) * POSITION_SMOOTHING_ALPHA,
    rawX: observation.x,
    rawY: observation.y,
    movementStreak,
    isMoving: true,
  }
}

export function stabilizeTrackState(previous, observation, stabilizedPosition) {
  if (observation.state === 'seated') {
    return { state: 'seated' }
  }
  // Pose가 여러 프레임 흔들려도 발 위치가 실제로 이동하기 전에는 좌석을
  // 유지한다. 일어서거나 이동해 두 번 연속 움직임이 확인되면 즉시 해제한다.
  const holdSeated = (
    previous?.state === 'seated'
    && !stabilizedPosition.isMoving
  )
  return {
    state: holdSeated ? 'seated' : observation.state,
  }
}

function previousSeatId(previousAssignments, trackId) {
  if (previousAssignments instanceof Map) return previousAssignments.get(trackId)
  return previousAssignments?.[trackId]
}

export function allocateRenderPositions(tracks, seatAnchors, previousAssignments = {}) {
  const usedSeats = new Set()
  const seatById = new Map(seatAnchors.map((anchor) => [anchor.id, anchor]))
  const preservedSeats = new Map()

  tracks.forEach((track) => {
    if (track.state !== 'seated' || !track.id) return
    const anchor = seatById.get(previousSeatId(previousAssignments, track.id))
    if (!anchor || usedSeats.has(anchor.id)) return
    const distance = Math.hypot(
      anchor.x / 1000 - track.x,
      anchor.y / 1000 - track.y,
    ) * 1000
    if (distance > SEAT_RELEASE_DISTANCE) return
    usedSeats.add(anchor.id)
    preservedSeats.set(track.id, anchor)
  })

  return tracks.map((track) => {
    if (track.state !== 'seated' || seatAnchors.length === 0) {
      return { ...track, renderX: track.x, renderY: track.y, seatAnchorId: null }
    }
    const preserved = preservedSeats.get(track.id)
    if (preserved) {
      return {
        ...track,
        renderX: preserved.x / 1000,
        renderY: preserved.y / 1000,
        seatAnchorId: preserved.id,
      }
    }
    const candidates = seatAnchors
      .filter((anchor) => !usedSeats.has(anchor.id))
      .map((anchor) => ({
        anchor,
        distance: Math.hypot(anchor.x / 1000 - track.x, anchor.y / 1000 - track.y) * 1000,
      }))
      .filter(({ distance }) => distance <= SEAT_SNAP_DISTANCE)
      .sort((left, right) => left.distance - right.distance)
    const nearest = candidates[0]?.anchor
    if (!nearest) {
      return { ...track, renderX: track.x, renderY: track.y, seatAnchorId: null }
    }
    usedSeats.add(nearest.id)
    return {
      ...track,
      renderX: nearest.x / 1000,
      renderY: nearest.y / 1000,
      seatAnchorId: nearest.id,
    }
  })
}
