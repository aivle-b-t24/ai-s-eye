export const DEFAULT_PERSPECTIVE = {
  far_y: 260,
  near_y: 960,
  far_scale: 0.68,
  near_scale: 1.3,
}

export const SEAT_SNAP_DISTANCE = 150

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

export function allocateRenderPositions(tracks, seatAnchors) {
  const usedSeats = new Set()
  return tracks.map((track) => {
    if (track.state !== 'seated' || seatAnchors.length === 0) {
      return { ...track, renderX: track.x, renderY: track.y, seatAnchorId: null }
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
