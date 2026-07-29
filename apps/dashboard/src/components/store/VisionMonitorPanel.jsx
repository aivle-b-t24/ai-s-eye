import React, { useCallback, useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const POLLING_INTERVAL_MS = 2000
const TRAIL_RETENTION_MS = 12000
const MAX_TRAIL_POINTS = 12
const ENABLE_CAMERA_TWIN_V2 = (
  String(import.meta.env.VITE_ENABLE_CAMERA_TWIN_V2).toLowerCase() === 'true'
)

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

function agentLabel(agent) {
  if (agent.role === 'staff') return '직원'
  if (agent.state === 'queue') return '대기 고객'
  return '고객'
}

function trailClass(trail) {
  if (trail.role === 'staff') return 'camera-trail-staff'
  if (trail.state === 'queue') return 'camera-trail-queue'
  return 'camera-trail-customer'
}

export default function VisionMonitorPanel({ storeId }) {
  const isStore2 = storeId === 'store-002'
  const cameraName = isStore2 ? 'CAM 02' : 'CAM 01'
  const storeName = isStore2 ? '매장 2' : '매장 1'

  const [viewMode, setViewMode] = useState('camera')
  const [imgTick, setImgTick] = useState(() => Date.now())
  const [hasImage, setHasImage] = useState(true)
  const [occupancy, setOccupancy] = useState(null)
  const [occupancyStatus, setOccupancyStatus] = useState('idle')
  const [roiConfig, setRoiConfig] = useState(null)
  const [trails, setTrails] = useState({})

  const isTwinMode = viewMode === 'twin'
  const agents = occupancy?.agents ?? []
  const counts = agents.reduce(
    (result, agent) => {
      if (agent.role === 'staff') result.staff += 1
      else if (agent.state === 'queue') result.queue += 1
      else result.customer += 1
      return result
    },
    { customer: 0, queue: 0, staff: 0 },
  )

  const updateTrails = useCallback((nextAgents) => {
    const now = Date.now()
    setTrails((current) => {
      const next = Object.fromEntries(
        Object.entries(current).filter(([, trail]) => (
          now - trail.lastSeen <= TRAIL_RETENTION_MS
        )),
      )
      nextAgents.forEach((agent) => {
        if (!agent.id) return
        const previous = next[agent.id]
        const point = { x: agent.x, y: agent.y }
        const lastPoint = previous?.points.at(-1)
        const moved = (
          !lastPoint
          || Math.abs(lastPoint.x - point.x) > 0.001
          || Math.abs(lastPoint.y - point.y) > 0.001
        )
        const points = moved
          ? [...(previous?.points ?? []), point].slice(-MAX_TRAIL_POINTS)
          : previous.points
        next[agent.id] = {
          points,
          role: agent.role,
          state: agent.state,
          lastSeen: now,
        }
      })
      return next
    })
  }, [])

  const loadOccupancy = useCallback(async (signal) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/stores/${storeId}/occupancy/latest`,
        { signal },
      )
      if (response.status === 404) {
        setOccupancy(null)
        setOccupancyStatus('empty')
        return
      }
      if (!response.ok) throw new Error(`위치 API 요청 실패 (${response.status})`)
      const frame = await response.json()
      setOccupancy(frame)
      updateTrails(frame.agents ?? [])
      setOccupancyStatus('ready')
    } catch (error) {
      if (error.name === 'AbortError') return
      setOccupancyStatus('error')
    }
  }, [storeId, updateTrails])

  useEffect(() => {
    setTrails({})
    setOccupancy(null)
    setHasImage(true)
  }, [storeId])

  useEffect(() => {
    const imageTimer = setInterval(() => setImgTick(Date.now()), POLLING_INTERVAL_MS)
    return () => clearInterval(imageTimer)
  }, [])

  useEffect(() => {
    if (!isTwinMode) {
      setOccupancy(null)
      setOccupancyStatus('idle')
      return undefined
    }
    const controller = new AbortController()
    setOccupancyStatus('loading')
    loadOccupancy(controller.signal)
    const occupancyTimer = setInterval(
      () => loadOccupancy(controller.signal),
      POLLING_INTERVAL_MS,
    )
    return () => {
      controller.abort()
      clearInterval(occupancyTimer)
    }
  }, [isTwinMode, loadOccupancy])

  useEffect(() => {
    if (!isTwinMode) return undefined
    const controller = new AbortController()
    fetch(
      `${API_BASE_URL}/api/stores/${storeId}/cameras/${storeId}-cam1/roi-config`,
      { signal: controller.signal },
    )
      .then((response) => (response.ok ? response.json() : null))
      .then(setRoiConfig)
      .catch((error) => {
        if (error.name !== 'AbortError') setRoiConfig(null)
      })
    return () => controller.abort()
  }, [isTwinMode, storeId])

  const imageEndpoint = isTwinMode ? 'vision/raw/latest' : 'vision/latest'
  const imageUrl = `${API_BASE_URL}/api/stores/${storeId}/${imageEndpoint}?t=${imgTick}`

  return (
    <article className="vision-card">
      <header className="vision-card-header">
        <div>
          <p className="eyebrow">
            {isTwinMode ? 'CCTV Digital Twin' : 'AI Camera'}
          </p>
          <h2>
            {isTwinMode ? 'CCTV 디지털 트윈' : '실시간 카메라 모니터링'}
          </h2>
        </div>

        <div className="vision-mode-tabs" aria-label="카메라 보기 방식">
          <button
            type="button"
            className={viewMode === 'camera' ? 'active' : ''}
            aria-pressed={viewMode === 'camera'}
            onClick={() => setViewMode('camera')}
          >
            분석 영상
          </button>
          {!ENABLE_CAMERA_TWIN_V2 && (
            <button
              type="button"
              className={isTwinMode ? 'active' : ''}
              aria-pressed={isTwinMode}
              onClick={() => setViewMode('twin')}
            >
              CCTV 디지털 트윈
            </button>
          )}
        </div>
      </header>

      <div className={`vision-feed ${isTwinMode ? 'twin-mode' : ''}`}>
            <img
              className="vision-feed-image"
              src={imageUrl}
              alt={
                isTwinMode
                  ? `${storeName} 원본 CCTV와 실시간 위치`
                  : `${storeName} 실시간 분석`
              }
              style={{ display: hasImage ? 'block' : 'none' }}
              onError={() => setHasImage(false)}
              onLoad={() => setHasImage(true)}
            />

            <div className="vision-feed-toolbar">
              <span className="vision-camera-name">
                <i />
                {cameraName}
              </span>
              <span className="vision-camera-status">
                {isTwinMode ? `${agents.length}명 위치 수신` : '정상'}
              </span>
            </div>

            {isTwinMode && (
              <svg
                className="camera-position-layer"
                viewBox="0 0 1000 1000"
                preserveAspectRatio="none"
                aria-label={`${storeName} ROI, 고객과 직원 발 좌표`}
              >
                {(roiConfig?.zones ?? []).map((zone) => (
                  <g key={zone.id} className={`camera-roi camera-roi-${zone.type}`}>
                    <polygon
                      points={zone.polygon.map((point) => `${point.x},${point.y}`).join(' ')}
                    />
                    <text x={zone.polygon[0]?.x ?? 0} y={(zone.polygon[0]?.y ?? 0) - 14}>
                      {zone.label}
                    </text>
                  </g>
                ))}

                {Object.entries(trails).map(([trackId, trail]) => (
                  trail.points.length > 1 && (
                    <polyline
                      key={trackId}
                      className={`camera-trail ${trailClass(trail)}`}
                      points={trail.points.map((point) => `${point.x * 1000},${point.y * 1000}`).join(' ')}
                    />
                  )
                ))}

                {agents.map((agent, index) => (
                  <g key={agent.id ?? `${agent.role}-${agent.x}-${agent.y}-${index}`}>
                    <circle
                      className={[
                        'camera-agent',
                        `camera-agent-${agent.role}`,
                        agent.state === 'queue' ? 'camera-agent-queue' : '',
                      ].filter(Boolean).join(' ')}
                      cx={agent.x * 1000}
                      cy={agent.y * 1000}
                      r="12"
                    >
                      <title>
                        {`${agentLabel(agent)} · ${agent.zone ?? '구역 미지정'}`}
                      </title>
                    </circle>
                  </g>
                ))}

                {occupancyStatus === 'loading' && (
                  <text className="camera-position-message" x="500" y="500">
                    위치 데이터를 불러오는 중입니다.
                  </text>
                )}
                {occupancyStatus === 'empty' && (
                  <text className="camera-position-message" x="500" y="500">
                    Vision 재생을 시작하면 발 좌표가 표시됩니다.
                  </text>
                )}
                {occupancyStatus === 'error' && (
                  <text className="camera-position-message camera-position-error" x="500" y="500">
                    위치 API에 연결할 수 없습니다.
                  </text>
                )}
                {occupancyStatus === 'ready' && agents.length === 0 && (
                  <text className="camera-position-message" x="500" y="500">
                    현재 탐지된 사람이 없습니다.
                  </text>
                )}
              </svg>
            )}

            {!hasImage && (
              <div className="twin-empty-state">
                {isTwinMode
                  ? '원본 CCTV 이미지가 없습니다.'
                  : '분석 이미지 대기 중'}
              </div>
            )}

            <div className="vision-feed-footer">
              <span>● LIVE</span>
              <strong>
                {isTwinMode
                  ? `${formatCapturedAt(occupancy?.captured_at)} 기준`
                  : `${storeName} 실시간 분석 중`}
              </strong>
            </div>
      </div>

      {isTwinMode && (
        <div className="twin-status-panel">
          <div className="twin-legend" aria-label="위치 표시 범례">
            <span><i className="customer" />고객 {counts.customer}명</span>
            <span><i className="queue" />대기 {counts.queue}명</span>
            <span><i className="staff" />직원 {counts.staff}명</span>
          </div>
          <p>원본 CCTV 위에 승인 ROI, 발 좌표와 최근 이동 궤적을 2초마다 표시합니다.</p>
        </div>
      )}
    </article>
  )
}
