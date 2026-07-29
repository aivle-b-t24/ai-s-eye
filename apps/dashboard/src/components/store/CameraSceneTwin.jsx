import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { getCameraScene } from './cameraScenes'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const POLLING_INTERVAL_MS = 2000
const POSITION_TRANSITION_MS = 1600
const MISSING_RETENTION_MS = 4000
const STALE_AFTER_MS = 6000
const MAX_TRAIL_POINTS = 12

function formatCapturedAt(value) {
  if (!value) return '측정 시각 없음'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '측정 시각 없음'
  return date.toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function polygonPoints(polygon) {
  return polygon.map(([x, y]) => `${x},${y}`).join(' ')
}

function roiPolygonPoints(polygon = []) {
  return polygon.map(({ x, y }) => `${x},${y}`).join(' ')
}

function objectCenter(polygon) {
  if (!polygon.length) return { x: 0, y: 0 }
  const total = polygon.reduce(
    (result, [x, y]) => ({ x: result.x + x, y: result.y + y }),
    { x: 0, y: 0 },
  )
  return {
    x: total.x / polygon.length,
    y: total.y / polygon.length,
  }
}

function agentLabel(agent) {
  if (agent.role === 'staff') return '직원'
  if (agent.state === 'queue') return '대기 고객'
  if (agent.state === 'seated') return '착석 고객'
  return '고객'
}

function agentClass(agent) {
  if (agent.role === 'staff') return 'staff'
  if (agent.state === 'queue') return 'queue'
  return 'customer'
}

function agentMotion(agent) {
  const current = agent.trail.at(-1)
  const previous = agent.trail.at(-2)
  if (!current || !previous || agent.state === 'seated') {
    return { moving: false, direction: 1 }
  }
  const deltaX = current.x - previous.x
  const deltaY = current.y - previous.y
  return {
    moving: Math.hypot(deltaX, deltaY) > 0.006,
    direction: deltaX < -0.001 ? -1 : 1,
  }
}

function buildTrackKey(agent, index) {
  if (agent.id) return agent.id
  return `anonymous-${index}-${Math.round(agent.x * 100)}-${Math.round(agent.y * 100)}`
}

function updateTracks(current, agents, observedAt) {
  const observedIds = new Set()
  const next = {}

  Object.entries(current).forEach(([id, track]) => {
    if (observedAt - track.lastSeenAt <= MISSING_RETENTION_MS) {
      next[id] = { ...track, missing: true }
    }
  })

  agents.forEach((agent, index) => {
    const id = buildTrackKey(agent, index)
    observedIds.add(id)
    const previous = current[id]
    const point = { x: agent.x, y: agent.y }
    const lastPoint = previous?.trail.at(-1)
    const moved = (
      !lastPoint
      || Math.abs(lastPoint.x - point.x) > 0.001
      || Math.abs(lastPoint.y - point.y) > 0.001
    )

    next[id] = {
      ...agent,
      id,
      trail: moved
        ? [...(previous?.trail ?? []), point].slice(-MAX_TRAIL_POINTS)
        : (previous?.trail ?? [point]),
      lastSeenAt: observedAt,
      missing: false,
    }
  })

  Object.keys(next).forEach((id) => {
    if (!observedIds.has(id) && observedAt - next[id].lastSeenAt > MISSING_RETENTION_MS) {
      delete next[id]
    }
  })

  return next
}

export default function CameraSceneTwin({ storeId, onSummaryChange }) {
  const fallbackScene = useMemo(() => getCameraScene(storeId), [storeId])
  const [sceneConfig, setSceneConfig] = useState(null)
  const scene = useMemo(() => {
    if (!fallbackScene || !sceneConfig) return fallbackScene
    return {
      ...fallbackScene,
      objects: sceneConfig.objects.map((item) => ({
        ...item,
        polygon: item.polygon.map(({ x, y }) => [x, y]),
      })),
    }
  }, [fallbackScene, sceneConfig])
  const [tracks, setTracks] = useState({})
  const [roiConfig, setRoiConfig] = useState(null)
  const [status, setStatus] = useState('loading')
  const [capturedAt, setCapturedAt] = useState(null)
  const [viewMode, setViewMode] = useState('twin')
  const [imageTick, setImageTick] = useState(() => Date.now())
  const latestCapturedAtRef = useRef(null)

  const loadOccupancy = useCallback(async (signal) => {
    if (!scene) {
      setStatus('empty')
      return
    }

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/stores/${storeId}/occupancy/latest`,
        { signal },
      )
      if (response.status === 404) {
        latestCapturedAtRef.current = null
        setTracks({})
        setCapturedAt(null)
        setStatus('empty')
        return
      }
      if (!response.ok) throw new Error(`위치 API 요청 실패 (${response.status})`)

      const frame = await response.json()
      const frameTime = new Date(frame.captured_at).getTime()
      const isStale = !Number.isFinite(frameTime) || Date.now() - frameTime > STALE_AFTER_MS
      const isNewFrame = frame.captured_at !== latestCapturedAtRef.current

      if (isNewFrame) {
        latestCapturedAtRef.current = frame.captured_at
        setCapturedAt(frame.captured_at)
        setTracks((current) => updateTracks(current, frame.agents ?? [], Date.now()))
        setImageTick(Date.now())
      }

      setStatus(isStale ? 'stale' : 'ready')
    } catch (error) {
      if (error.name === 'AbortError') return
      setStatus('error')
    }
  }, [scene, storeId])

  useEffect(() => {
    latestCapturedAtRef.current = null
    setTracks({})
    setRoiConfig(null)
    setSceneConfig(null)
    setCapturedAt(null)
    setStatus('loading')
    setViewMode('twin')
  }, [storeId])

  useEffect(() => {
    if (!scene) return undefined
    const controller = new AbortController()
    loadOccupancy(controller.signal)
    const timer = setInterval(
      () => loadOccupancy(controller.signal),
      POLLING_INTERVAL_MS,
    )
    return () => {
      controller.abort()
      clearInterval(timer)
    }
  }, [loadOccupancy, scene])

  useEffect(() => {
    if (!fallbackScene) return undefined
    const controller = new AbortController()
    fetch(
      `${API_BASE_URL}/api/stores/${storeId}/cameras/${fallbackScene.cameraId}/roi-config`,
      { signal: controller.signal },
    )
      .then((response) => (response.ok ? response.json() : null))
      .then(setRoiConfig)
      .catch((error) => {
        if (error.name !== 'AbortError') setRoiConfig(null)
    })
    return () => controller.abort()
  }, [fallbackScene, storeId])

  useEffect(() => {
    if (!fallbackScene) return undefined
    const controller = new AbortController()
    fetch(
      `${API_BASE_URL}/api/stores/${storeId}/cameras/${fallbackScene.cameraId}/scene-config`,
      { signal: controller.signal },
    )
      .then((response) => (response.ok ? response.json() : null))
      .then(setSceneConfig)
      .catch((error) => {
        if (error.name !== 'AbortError') setSceneConfig(null)
      })
    return () => controller.abort()
  }, [fallbackScene, storeId])

  const trackList = useMemo(() => Object.values(tracks), [tracks])
  const roiZoneTypes = useMemo(
    () => [...new Set((roiConfig?.zones ?? []).map((zone) => zone.type))],
    [roiConfig],
  )
  const roiZoneTypeSet = useMemo(
    () => new Set(roiZoneTypes),
    [roiZoneTypes],
  )
  const displayTrackList = useMemo(() => {
    if (!roiConfig) return trackList
    return trackList.map((track) => {
      const hasApprovedZone = (
        (track.zone && roiZoneTypeSet.has(track.zone))
        || (track.role === 'staff' && roiZoneTypeSet.has('staff'))
      )
      if (hasApprovedZone) return track
      return {
        ...track,
        role: track.role === 'staff' ? 'customer' : track.role,
        state: 'unknown',
        zone: null,
      }
    })
  }, [roiConfig, roiZoneTypeSet, trackList])
  const activeTracks = useMemo(
    () => displayTrackList.filter((track) => !track.missing),
    [displayTrackList],
  )
  const counts = useMemo(
    () => activeTracks.reduce(
      (result, track) => {
        if (track.role === 'staff') result.staff += 1
        else if (track.state === 'queue') result.queue += 1
        else result.customer += 1
        return result
      },
      { customer: 0, queue: 0, staff: 0 },
    ),
    [activeTracks],
  )
  const liveZoneCounts = useMemo(
    () => activeTracks.reduce((result, track) => {
      const zone = track.zone ?? (
        track.role === 'customer' ? 'unassigned' : null
      )
      if (!zone) return result
      result[zone] = (result[zone] ?? 0) + 1
      return result
    }, {}),
    [activeTracks],
  )
  useEffect(() => {
    onSummaryChange?.({
      count: activeTracks.length,
      capturedAt,
      status,
      zoneCounts: liveZoneCounts,
      roiZoneTypes: roiConfig ? roiZoneTypes : null,
    })
  }, [
    activeTracks.length,
    capturedAt,
    liveZoneCounts,
    onSummaryChange,
    roiConfig,
    roiZoneTypes,
    status,
  ])

  if (!scene) {
    return (
      <div className="camera-scene-empty">
        이 매장의 디지털 트윈 장면이 아직 준비되지 않았습니다.
      </div>
    )
  }

  const imageEndpoint = (
    viewMode === 'analysis' ? 'vision/latest' : 'vision/raw/latest'
  )
  const imageUrl = `${API_BASE_URL}/api/stores/${storeId}/${imageEndpoint}?t=${imageTick}`
  const showSource = viewMode !== 'twin'

  return (
    <section
      className={`camera-scene-twin camera-scene-mode-${viewMode}`}
      aria-label={`${scene.label} 디지털 트윈`}
    >
      <div className="camera-scene-toolbar">
        <div>
          <span className={`camera-scene-live camera-scene-live-${status}`} />
          <strong>{scene.label}</strong>
          <small>
            {status === 'ready' && 'LIVE'}
            {status === 'stale' && '지연됨'}
            {status === 'loading' && '연결 중'}
            {status === 'empty' && '재생 대기'}
            {status === 'error' && '연결 오류'}
          </small>
        </div>
        <div className="camera-scene-view-switch" aria-label="카메라 화면 보기 방식">
          <button
            type="button"
            className={viewMode === 'twin' ? 'active' : ''}
            aria-pressed={viewMode === 'twin'}
            onClick={() => setViewMode('twin')}
          >
            디지털 트윈
          </button>
          <button
            type="button"
            className={viewMode === 'raw' ? 'active' : ''}
            aria-pressed={viewMode === 'raw'}
            onClick={() => setViewMode('raw')}
          >
            원본 CCTV
          </button>
          <button
            type="button"
            className={viewMode === 'analysis' ? 'active' : ''}
            aria-pressed={viewMode === 'analysis'}
            onClick={() => setViewMode('analysis')}
          >
            분석 영상
          </button>
        </div>
      </div>

      <div className="camera-scene-stage">
        {showSource && (
          <img
            className="camera-scene-source"
            src={imageUrl}
            alt={`${scene.label} 원본 CCTV`}
          />
        )}

        {viewMode !== 'analysis' && (
          <>
            <svg
              className="camera-scene-map"
              viewBox="0 0 1000 1000"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <defs>
                <linearGradient id={`${storeId}-floor`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#e7edf0" />
                  <stop offset="100%" stopColor="#aab8be" />
                </linearGradient>
                <pattern
                  id={`${storeId}-grid`}
                  width="62"
                  height="62"
                  patternUnits="userSpaceOnUse"
                >
                  <path d="M 62 0 L 0 0 0 62" fill="none" stroke="#4c626b" strokeWidth="1" opacity="0.16" />
                </pattern>
              </defs>

              <rect width="1000" height="1000" className="camera-scene-background" />
              {scene.objects.filter((object) => object.type !== 'occluder').map((object) => {
                const center = objectCenter(object.polygon)
                return (
                  <g key={object.id} className={`camera-scene-object camera-scene-${object.type}`}>
                    <polygon points={polygonPoints(object.polygon)} />
                    {object.label && (
                      <text x={center.x} y={center.y}>{object.label}</text>
                    )}
                  </g>
                )
              })}
              <rect width="1000" height="1000" fill={`url(#${storeId}-grid)`} />

              {(roiConfig?.zones ?? []).map((zone) => (
                <g key={zone.id} className={`camera-scene-roi camera-scene-roi-${zone.type}`}>
                  <polygon points={roiPolygonPoints(zone.polygon)} />
                  <text
                    x={zone.polygon[0]?.x ?? 0}
                    y={Math.max((zone.polygon[0]?.y ?? 0) - 12, 22)}
                  >
                    {zone.label}
                  </text>
                </g>
              ))}

              {displayTrackList.map((track) => (
                track.trail.length > 1 && (
                  <polyline
                    key={`${track.id}-trail`}
                    className={`camera-scene-trail camera-scene-trail-${agentClass(track)}`}
                    points={track.trail.map(({ x, y }) => `${x * 1000},${y * 1000}`).join(' ')}
                  />
                )
              ))}
            </svg>

            <div className="camera-scene-agent-layer" aria-live="polite">
              {displayTrackList.map((track) => {
                const scale = Math.min(Math.max(0.7 + track.y * 0.65, 0.7), 1.35)
                const motion = agentMotion(track)
                return (
                  <div
                    key={track.id}
                    className={[
                      'camera-scene-agent',
                      `camera-scene-agent-${agentClass(track)}`,
                      track.state === 'seated' ? 'is-seated' : '',
                      motion.moving ? 'is-moving' : '',
                      track.missing ? 'is-missing' : '',
                    ].filter(Boolean).join(' ')}
                    style={{
                      left: `${track.x * 100}%`,
                      top: `${track.y * 100}%`,
                      zIndex: Math.round(track.y * 1000) + 100,
                      '--agent-scale': scale,
                      '--agent-direction': motion.direction,
                      '--position-transition': `${POSITION_TRANSITION_MS}ms`,
                    }}
                    title={`${agentLabel(track)} · ${track.zone ?? '구역 미지정'} · ID ${track.id}`}
                  >
                    <span className="camera-scene-agent-shadow" />
                    <span className="camera-scene-agent-body">
                      <i className="camera-scene-agent-head" />
                      <i className="camera-scene-agent-torso" />
                      <i className="camera-scene-agent-arms" />
                      <i className="camera-scene-agent-legs" />
                    </span>
                  </div>
                )
              })}
            </div>

            <svg
              className="camera-scene-foreground"
              viewBox="0 0 1000 1000"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              {scene.objects.filter((object) => object.type === 'occluder').map((object) => (
                <g key={object.id} className="camera-scene-object camera-scene-occluder">
                  <polygon points={polygonPoints(object.polygon)} />
                </g>
              ))}
            </svg>
          </>
        )}

        {(status === 'loading' || status === 'empty' || status === 'error') && (
          <div className={`camera-scene-message camera-scene-message-${status}`}>
            {status === 'loading' && '위치 데이터를 불러오는 중입니다.'}
            {status === 'empty' && 'Vision 재생을 시작하면 사람이 표시됩니다.'}
            {status === 'error' && '위치 API에 연결할 수 없습니다.'}
          </div>
        )}
      </div>

      <footer className="camera-scene-footer">
        <div className="camera-scene-legend">
          <span><i className="customer" />고객 {counts.customer}명</span>
          <span><i className="queue" />대기 {counts.queue}명</span>
          <span><i className="staff" />직원 {counts.staff}명</span>
        </div>
        <time dateTime={capturedAt ?? undefined}>{formatCapturedAt(capturedAt)}</time>
      </footer>
    </section>
  )
}
