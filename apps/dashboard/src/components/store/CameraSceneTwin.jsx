import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { getCameraScene } from './cameraScenes'
import {
  allocateRenderPositions,
  perspectiveScale,
} from './sceneProjection'

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
  return date.toLocaleString('ko-KR', {
    month: '2-digit',
    day: '2-digit',
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

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum)
}

function deriveSeatAnchors(objects) {
  return objects
    .filter((item) => item.type === 'table' && item.polygon.length >= 3)
    .flatMap((item) => {
      const frontEdge = [...item.polygon]
        .sort((left, right) => right[1] - left[1])
        .slice(0, 2)
        .sort((left, right) => left[0] - right[0])
      if (frontEdge.length < 2) return []
      const [left, right] = frontEdge
      const anchorY = clamp(Math.round((left[1] + right[1]) / 2 + 24), 0, 985)
      const width = Math.abs(right[0] - left[0])
      const ratios = width >= 125 ? [0.32, 0.68] : [0.5]
      return ratios.map((ratio, index) => ({
        id: `${item.id}-derived-seat-${index + 1}`,
        table_id: item.id,
        x: Math.round(left[0] + (right[0] - left[0]) * ratio),
        y: anchorY,
      }))
    })
}

function objectDepth(object) {
  const frontY = Math.max(...object.polygon.map(([, y]) => y))
  return frontY + (object.type === 'occluder' ? 115 : 85)
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

function updateTracks(current, agents, observedAt, { retainMissing = true } = {}) {
  const observedIds = new Set()
  const next = {}

  Object.entries(current).forEach(([id, track]) => {
    if (!retainMissing) return
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

export default function CameraSceneTwin({
  storeId,
  onSummaryChange,
  simulationResult = null,
  simulationFrameIndex = 0,
}) {
  const isSimulation = Boolean(simulationResult)
  const simulationFrame = simulationResult?.frames?.[simulationFrameIndex] ?? null
  const fallbackScene = useMemo(() => getCameraScene(storeId), [storeId])
  const [sceneConfig, setSceneConfig] = useState(null)
  const scene = useMemo(() => {
    if (!fallbackScene || !sceneConfig) return fallbackScene
    const objects = sceneConfig.objects.map((item) => ({
      ...item,
      polygon: item.polygon.map(({ x, y }) => [x, y]),
    }))
    return {
      ...fallbackScene,
      objects,
      perspective: sceneConfig.perspective ?? fallbackScene.perspective,
      seatAnchors: sceneConfig.seat_anchors?.length
        ? sceneConfig.seat_anchors
        : deriveSeatAnchors(objects),
    }
  }, [fallbackScene, sceneConfig])
  const [tracks, setTracks] = useState({})
  const [roiConfig, setRoiConfig] = useState(null)
  const [status, setStatus] = useState('loading')
  const [capturedAt, setCapturedAt] = useState(null)
  const [frameMetadata, setFrameMetadata] = useState(null)
  const [viewMode, setViewMode] = useState('twin')
  const [imageTick, setImageTick] = useState(() => Date.now())
  const latestCapturedAtRef = useRef(null)

  const loadOccupancy = useCallback(async (signal) => {
    if (isSimulation) return
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
      const frameTime = new Date(frame.published_at ?? frame.captured_at).getTime()
      const isStale = !Number.isFinite(frameTime) || Date.now() - frameTime > STALE_AFTER_MS
      const frameKey = `${frame.frame_id ?? frame.captured_at}:${frame.published_at ?? ''}`
      const isNewFrame = frameKey !== latestCapturedAtRef.current

      if (isNewFrame) {
        latestCapturedAtRef.current = frameKey
        setCapturedAt(frame.captured_at)
        setFrameMetadata({
          frameId: frame.frame_id,
          processedAt: frame.processed_at,
          modelVersion: frame.model_version,
          roiVersion: frame.roi_version,
          source: frame.source,
        })
        setTracks((current) => updateTracks(current, frame.agents ?? [], Date.now()))
        setImageTick(Date.now())
      }

      setStatus(isStale ? 'stale' : 'ready')
    } catch (error) {
      if (error.name === 'AbortError') return
      setStatus('error')
    }
  }, [isSimulation, scene, storeId])

  useEffect(() => {
    latestCapturedAtRef.current = null
    setTracks({})
    setRoiConfig(null)
    setSceneConfig(null)
    setCapturedAt(null)
    setFrameMetadata(null)
    setStatus('loading')
    setViewMode('twin')
  }, [simulationResult?.run_id, storeId])

  useEffect(() => {
    if (!scene || isSimulation) return undefined
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
  }, [isSimulation, loadOccupancy, scene])

  useEffect(() => {
    if (!isSimulation || !simulationFrame) return
    setStatus('ready')
    setCapturedAt(null)
    setFrameMetadata({
      frameId: `${simulationResult.run_id}:${simulationFrameIndex}`,
      processedAt: simulationResult.generated_at,
      modelVersion: 'simpy-operations-v1',
      roiVersion: null,
      source: 'simulation',
      simulationMinute: simulationFrame.at_minute,
    })
    setTracks((current) => updateTracks(
      current,
      simulationFrame.agents ?? [],
      Date.now(),
      { retainMissing: false },
    ))
  }, [isSimulation, simulationFrame, simulationFrameIndex, simulationResult])

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
    if (isSimulation || !roiConfig) return trackList
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
  }, [isSimulation, roiConfig, roiZoneTypeSet, trackList])
  const seatAnchors = useMemo(
    () => scene?.seatAnchors?.length
      ? scene.seatAnchors
      : deriveSeatAnchors(scene?.objects ?? []),
    [scene],
  )
  const renderTrackList = useMemo(
    () => allocateRenderPositions(displayTrackList, seatAnchors),
    [displayTrackList, seatAnchors],
  )
  const backgroundObjects = useMemo(
    () => (scene?.objects ?? []).filter(
      (item) => !['table', 'counter', 'occluder'].includes(item.type),
    ),
    [scene],
  )
  const depthObjects = useMemo(
    () => (scene?.objects ?? []).filter(
      (item) => ['table', 'counter', 'occluder'].includes(item.type),
    ),
    [scene],
  )
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

  const imageEndpoint = 'vision/raw/latest'
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
            {status === 'ready' && (isSimulation ? 'SIMULATION' : 'LIVE')}
            {status === 'stale' && '지연됨'}
            {status === 'loading' && '연결 중'}
            {status === 'empty' && '재생 대기'}
            {status === 'error' && '연결 오류'}
          </small>
        </div>
        {!isSimulation && (
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
        )}
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
              {backgroundObjects.map((object) => {
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

              {renderTrackList.map((track) => (
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
              {renderTrackList.map((track) => {
                const scale = perspectiveScale(track.renderY, scene.perspective)
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
                      left: `${track.renderX * 100}%`,
                      top: `${track.renderY * 100}%`,
                      zIndex: Math.round(track.renderY * 1000) + 100,
                      '--agent-scale': scale,
                      '--agent-direction': motion.direction,
                      '--position-transition': isSimulation
                        ? '480ms'
                        : `${POSITION_TRANSITION_MS}ms`,
                    }}
                    title={`${agentLabel(track)} · ${track.zone ?? '구역 미지정'} · ID ${track.id}${track.seatAnchorId ? ' · 좌석 보정' : ''}`}
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

            {depthObjects.map((object) => {
              const center = objectCenter(object.polygon)
              return (
                <svg
                  key={`${object.id}-depth`}
                  className={`camera-scene-depth-object camera-scene-object camera-scene-${object.type}`}
                  viewBox="0 0 1000 1000"
                  preserveAspectRatio="none"
                  style={{ zIndex: objectDepth(object) }}
                  aria-hidden="true"
                >
                  <polygon points={polygonPoints(object.polygon)} />
                  {object.label && object.type !== 'occluder' && (
                    <text x={center.x} y={center.y}>{object.label}</text>
                  )}
                </svg>
              )
            })}

          </>
        )}

        {viewMode === 'analysis' && (
          <svg
            className="camera-scene-map camera-scene-analysis-overlay"
            viewBox="0 0 1000 1000"
            preserveAspectRatio="none"
            aria-label="현재 승인 ROI 판정 결과"
          >
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
              <g
                key={track.id}
                className={`camera-scene-analysis-agent camera-scene-analysis-agent-${agentClass(track)}`}
              >
                <circle cx={track.x * 1000} cy={track.y * 1000} r="13" />
                <text x={track.x * 1000 + 18} y={track.y * 1000 - 15}>
                  {track.id}
                </text>
              </g>
            ))}
          </svg>
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
        <div>
          <div className="camera-scene-legend">
            <span><i className="customer" />고객 {counts.customer}명</span>
            <span><i className="queue" />대기 {counts.queue}명</span>
            <span><i className="staff" />직원 {counts.staff}명</span>
          </div>
          <div className="camera-scene-identity">
            <span>프레임 {frameMetadata?.frameId ?? '확인 불가'}</span>
            <span>모델 {frameMetadata?.modelVersion ?? '확인 불가'}</span>
            {!isSimulation && <span>ROI v{frameMetadata?.roiVersion ?? '미지정'}</span>}
            <span>
              {frameMetadata?.source === 'simulation'
                ? '합성 시뮬레이션'
                : frameMetadata?.source === 'demo-replay'
                  ? '데모 재생'
                  : 'Vision 분석'}
            </span>
          </div>
        </div>
        <div className="camera-scene-times">
          {isSimulation ? (
            <>
              <span>가상 운영 +{frameMetadata?.simulationMinute ?? 0}분</span>
              <span>실제 데이터 아님</span>
            </>
          ) : (
            <>
              <span>촬영 {formatCapturedAt(capturedAt)}</span>
              <span>분석 {formatCapturedAt(frameMetadata?.processedAt)}</span>
            </>
          )}
        </div>
      </footer>
    </section>
  )
}
