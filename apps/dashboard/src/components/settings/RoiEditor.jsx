import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

const ZONE_OPTIONS = [
  { value: 'staff', label: '직원 구역' },
  { value: 'waiting', label: '대기 구역' },
  { value: 'entrance', label: '출입구' },
  { value: 'seating', label: '좌석 구역' },
]

const ZONE_LABELS = Object.fromEntries(
  ZONE_OPTIONS.map((option) => [option.value, option.label]),
)

function pointFromEvent(event, svg) {
  const rect = svg.getBoundingClientRect()
  return {
    x: Math.max(0, Math.min(1000, Math.round(((event.clientX - rect.left) / rect.width) * 1000))),
    y: Math.max(0, Math.min(1000, Math.round(((event.clientY - rect.top) / rect.height) * 1000))),
  }
}

function makeZone(type, polygon, index) {
  return {
    id: `${type}-${Date.now()}-${index}`,
    type,
    label: ZONE_LABELS[type],
    polygon,
  }
}

function polygonPoints(points) {
  return points.map((point) => `${point.x},${point.y}`).join(' ')
}

function formatDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('ko-KR')
}

function pointInPolygon(point, polygon) {
  let inside = false
  for (let current = 0, previous = polygon.length - 1; current < polygon.length; previous = current++) {
    const currentPoint = polygon[current]
    const previousPoint = polygon[previous]
    const crosses = (
      (currentPoint.y > point.y) !== (previousPoint.y > point.y)
      && point.x < (
        ((previousPoint.x - currentPoint.x) * (point.y - currentPoint.y))
        / (previousPoint.y - currentPoint.y)
      ) + currentPoint.x
    )
    if (crosses) inside = !inside
  }
  return inside
}

export default function RoiEditor({
  apiBaseUrl,
  storeId,
}) {
  const cameraId = `${storeId}-cam1`
  const svgRef = useRef(null)
  const objectUrlRef = useRef(null)
  const [imageSrc, setImageSrc] = useState(
    () => `${apiBaseUrl}/api/stores/${storeId}/vision/raw/latest?t=${Date.now()}`,
  )
  const [imageSize, setImageSize] = useState({ width: 1920, height: 1080 })
  const [imageStatus, setImageStatus] = useState({
    kind: 'loading',
    message: '오버레이 없는 원본 CCTV 이미지를 확인하는 중입니다.',
  })
  const [zones, setZones] = useState([])
  const [versions, setVersions] = useState([])
  const [selectedZoneId, setSelectedZoneId] = useState(null)
  const [selectedVertex, setSelectedVertex] = useState(null)
  const [drawType, setDrawType] = useState('waiting')
  const [draftPoints, setDraftPoints] = useState([])
  const [isDrawing, setIsDrawing] = useState(false)
  const [dragging, setDragging] = useState(null)
  const [source, setSource] = useState('manual')
  const [status, setStatus] = useState({ kind: 'idle', message: '' })
  const [occupancy, setOccupancy] = useState(null)
  const [occupancyStatus, setOccupancyStatus] = useState({
    kind: 'idle',
    message: '현재 탐지점을 불러오면 ROI에 포함되는 사람 수를 확인할 수 있습니다.',
  })

  const selectedZone = useMemo(
    () => zones.find((zone) => zone.id === selectedZoneId) ?? null,
    [selectedZoneId, zones],
  )
  const validation = useMemo(() => {
    const agents = occupancy?.agents ?? []
    const zoneCounts = Object.fromEntries(zones.map((zone) => [zone.id, 0]))
    let matched = 0
    agents.forEach((agent) => {
      const point = { x: agent.x * 1000, y: agent.y * 1000 }
      const containingZones = zones.filter((zone) => pointInPolygon(point, zone.polygon))
      if (containingZones.length > 0) matched += 1
      containingZones.forEach((zone) => {
        zoneCounts[zone.id] += 1
      })
    })
    return {
      total: agents.length,
      matched,
      outside: agents.length - matched,
      zoneCounts,
    }
  }, [occupancy, zones])

  const loadVersions = useCallback(async () => {
    const response = await fetch(
      `${apiBaseUrl}/api/stores/${storeId}/cameras/${cameraId}/roi-configs`,
    )
    if (!response.ok) throw new Error(`설정 이력 조회 실패 (${response.status})`)
    setVersions(await response.json())
  }, [apiBaseUrl, cameraId, storeId])

  const loadApproved = useCallback(async () => {
    setStatus({ kind: 'loading', message: 'ROI 설정을 불러오는 중입니다.' })
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/stores/${storeId}/cameras/${cameraId}/roi-config`,
      )
      if (response.status === 404) {
        setZones([])
        setVersions([])
        setStatus({ kind: 'idle', message: '저장된 ROI가 없습니다. 새로 설정해 주세요.' })
        return
      }
      if (!response.ok) throw new Error(`ROI 설정 조회 실패 (${response.status})`)
      const config = await response.json()
      setZones(config.zones)
      setImageSize(config.image_size)
      setSource(config.source)
      setSelectedZoneId(config.zones[0]?.id ?? null)
      await loadVersions()
      setStatus({ kind: 'success', message: `적용 중인 ROI v${config.version}을 불러왔습니다.` })
    } catch (error) {
      setStatus({ kind: 'error', message: error.message })
    }
  }, [apiBaseUrl, cameraId, loadVersions, storeId])

  useEffect(() => {
    setSelectedZoneId(null)
    setDraftPoints([])
    setIsDrawing(false)
    setOccupancy(null)
    loadApproved()
  }, [loadApproved])

  useEffect(() => () => {
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
  }, [])

  useEffect(() => {
    const probe = new Image()
    probe.onload = () => {
      if (probe.naturalWidth && probe.naturalHeight) {
        setImageSize({
          width: probe.naturalWidth,
          height: probe.naturalHeight,
        })
        setImageStatus({
          kind: 'success',
          message: 'ROI 선과 탐지 박스가 없는 원본 이미지를 사용합니다.',
        })
      }
    }
    probe.onerror = () => {
      setImageStatus({
        kind: 'error',
        message: '원본 CCTV 이미지가 없습니다. Vision에서 원본을 전송하거나 설정용 원본 이미지를 업로드해 주세요.',
      })
    }
    probe.src = imageSrc
    return () => {
      probe.onload = null
      probe.onerror = null
    }
  }, [imageSrc])

  const useLatestImage = () => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = null
    }
    const tick = Date.now()
    setImageStatus({
      kind: 'loading',
      message: '최신 원본 CCTV 이미지를 불러오는 중입니다.',
    })
    setImageSrc(`${apiBaseUrl}/api/stores/${storeId}/vision/raw/latest?t=${tick}`)
  }

  const handleFile = (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (!['image/jpeg', 'image/png'].includes(file.type)) {
      setStatus({ kind: 'error', message: 'JPEG 또는 PNG 이미지만 선택할 수 있습니다.' })
      return
    }
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
    objectUrlRef.current = URL.createObjectURL(file)
    setImageSrc(objectUrlRef.current)
    setImageStatus({
      kind: 'success',
      message: `${file.name} 파일을 설정용 원본 이미지로 사용합니다. 기존 ROI가 그려진 이미지는 사용하지 마세요.`,
    })
  }

  const loadOccupancy = async () => {
    setOccupancyStatus({ kind: 'loading', message: '현재 사람 위치를 불러오는 중입니다.' })
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/stores/${storeId}/occupancy/latest`,
      )
      if (!response.ok) throw new Error(`현재 위치 조회 실패 (${response.status})`)
      const result = await response.json()
      if (result.coordinate_space !== 'normalized_image') {
        throw new Error('현재 위치가 평면도 좌표여서 CCTV 이미지 위에서 검증할 수 없습니다.')
      }
      setOccupancy(result)
      setOccupancyStatus({
        kind: 'success',
        message: `${formatDate(result.captured_at)} 기준 탐지점 ${result.agents.length}개를 표시합니다.`,
      })
    } catch (error) {
      setOccupancy(null)
      setOccupancyStatus({ kind: 'error', message: error.message })
    }
  }

  const startDrawing = () => {
    setDraftPoints([])
    setIsDrawing(true)
    setSelectedZoneId(null)
    setSelectedVertex(null)
    setStatus({ kind: 'idle', message: '이미지를 클릭해 꼭짓점을 3개 이상 지정하세요.' })
  }

  const completeDrawing = () => {
    if (draftPoints.length < 3) {
      setStatus({ kind: 'error', message: '꼭짓점을 3개 이상 지정해야 합니다.' })
      return
    }
    const zone = makeZone(drawType, draftPoints, zones.length + 1)
    setZones((current) => [...current, zone])
    setSelectedZoneId(zone.id)
    setDraftPoints([])
    setIsDrawing(false)
    setSource('manual')
    setStatus({ kind: 'idle', message: '새 구역을 추가했습니다. 꼭짓점을 끌어 보정할 수 있습니다.' })
  }

  const handleCanvasPointerDown = (event) => {
    if (!isDrawing || event.target.dataset.vertex === 'true') return
    const point = pointFromEvent(event, svgRef.current)
    setDraftPoints((current) => [...current, point])
  }

  const handlePointerMove = (event) => {
    if (!dragging) return
    const point = pointFromEvent(event, svgRef.current)
    setZones((current) => current.map((zone) => {
      if (zone.id !== dragging.zoneId) return zone
      return {
        ...zone,
        polygon: zone.polygon.map((item, index) => (
          index === dragging.vertexIndex ? point : item
        )),
      }
    }))
    setSource('manual')
  }

  const stopDragging = () => setDragging(null)

  const addVertex = () => {
    if (!selectedZone) return
    let longestIndex = 0
    let longestDistance = -1
    selectedZone.polygon.forEach((point, index) => {
      const next = selectedZone.polygon[(index + 1) % selectedZone.polygon.length]
      const distance = (point.x - next.x) ** 2 + (point.y - next.y) ** 2
      if (distance > longestDistance) {
        longestDistance = distance
        longestIndex = index
      }
    })
    const point = selectedZone.polygon[longestIndex]
    const next = selectedZone.polygon[(longestIndex + 1) % selectedZone.polygon.length]
    const midpoint = {
      x: Math.round((point.x + next.x) / 2),
      y: Math.round((point.y + next.y) / 2),
    }
    setZones((current) => current.map((zone) => (
      zone.id === selectedZone.id
        ? {
            ...zone,
            polygon: [
              ...zone.polygon.slice(0, longestIndex + 1),
              midpoint,
              ...zone.polygon.slice(longestIndex + 1),
            ],
          }
        : zone
    )))
    setSource('manual')
  }

  const deleteVertex = () => {
    if (!selectedZone || selectedVertex === null) return
    if (selectedZone.polygon.length <= 3) {
      setStatus({ kind: 'error', message: '구역에는 꼭짓점이 최소 3개 필요합니다.' })
      return
    }
    setZones((current) => current.map((zone) => (
      zone.id === selectedZone.id
        ? {
            ...zone,
            polygon: zone.polygon.filter((_, index) => index !== selectedVertex),
          }
        : zone
    )))
    setSelectedVertex(null)
    setSource('manual')
  }

  const updateSelectedZone = (changes) => {
    setZones((current) => current.map((zone) => (
      zone.id === selectedZoneId ? { ...zone, ...changes } : zone
    )))
    setSource('manual')
  }

  const deleteSelectedZone = () => {
    setZones((current) => current.filter((zone) => zone.id !== selectedZoneId))
    setSelectedZoneId(null)
    setSelectedVertex(null)
    setSource('manual')
  }

  const saveAndApply = async () => {
    if (!zones.length) {
      setStatus({ kind: 'error', message: '저장할 구역이 없습니다.' })
      return
    }
    setStatus({ kind: 'loading', message: 'ROI 설정을 저장하고 적용하는 중입니다.' })
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/stores/${storeId}/cameras/${cameraId}/roi-config`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            coordinate_space: 'normalized_1000',
            image_size: imageSize,
            source,
            zones: zones.map((zone) => ({
              id: zone.id,
              type: zone.type,
              label: zone.label,
              polygon: zone.polygon,
            })),
          }),
        },
      )
      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        throw new Error(detail?.detail?.[0]?.msg ?? detail?.detail ?? `저장 실패 (${response.status})`)
      }
      const saved = await response.json()
      setZones(saved.zones)
      setSource(saved.source)
      await loadVersions()
      setStatus({
        kind: 'success',
        message: `ROI v${saved.version}을 적용했습니다. 기존 재생 데이터는 Vision 분석을 다시 실행해야 바뀝니다.`,
      })
    } catch (error) {
      setStatus({ kind: 'error', message: error.message })
    }
  }

  const approveVersion = async (version) => {
    setStatus({ kind: 'loading', message: `ROI v${version}을 다시 적용하는 중입니다.` })
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/stores/${storeId}/cameras/${cameraId}/roi-configs/${version}/approve`,
        { method: 'POST' },
      )
      if (!response.ok) throw new Error(`이전 버전 적용 실패 (${response.status})`)
      const approved = await response.json()
      setZones(approved.zones)
      setImageSize(approved.image_size)
      setSource(approved.source)
      setSelectedZoneId(approved.zones[0]?.id ?? null)
      await loadVersions()
      setStatus({ kind: 'success', message: `ROI v${version}을 다시 적용했습니다.` })
    } catch (error) {
      setStatus({ kind: 'error', message: error.message })
    }
  }

  return (
    <section className="roi-settings" aria-labelledby="roi-settings-title">
      <div className="roi-settings-heading">
        <div>
          <p className="roi-eyebrow">VISION SETUP</p>
          <h3 id="roi-settings-title">카메라 구역 설정</h3>
          <p>{storeId} · {cameraId}</p>
        </div>
        <button type="button" className="roi-secondary-btn" onClick={loadApproved}>
          적용 설정 다시 불러오기
        </button>
      </div>

      <div className="roi-toolbar">
        <button type="button" className="roi-secondary-btn" onClick={useLatestImage}>
          최신 원본 CCTV 이미지
        </button>
        <label className="roi-file-btn">
          설정용 이미지 업로드
          <input type="file" accept="image/jpeg,image/png" onChange={handleFile} />
        </label>
        <button type="button" className="roi-secondary-btn" onClick={loadOccupancy}>
          현재 탐지점 불러오기
        </button>
        <select value={drawType} onChange={(event) => setDrawType(event.target.value)}>
          {ZONE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        {!isDrawing ? (
          <button type="button" className="roi-secondary-btn" onClick={startDrawing}>
            수동 구역 그리기
          </button>
        ) : (
          <>
            <button type="button" className="roi-primary-btn" onClick={completeDrawing}>
              구역 완성
            </button>
            <button
              type="button"
              className="roi-text-btn"
              onClick={() => {
                setIsDrawing(false)
                setDraftPoints([])
              }}
            >
              취소
            </button>
          </>
        )}
      </div>

      <p className={`roi-status roi-status-${imageStatus.kind}`} role="status">
        {imageStatus.message}
      </p>

      {status.message && (
        <p className={`roi-status roi-status-${status.kind}`} role="status">
          {status.message}
        </p>
      )}

      <div className="roi-editor-layout">
        <div className="roi-canvas-wrap">
          <svg
            ref={svgRef}
            className={`roi-canvas ${isDrawing ? 'is-drawing' : ''}`}
            viewBox="0 0 1000 1000"
            preserveAspectRatio="none"
            style={{ aspectRatio: `${imageSize.width} / ${imageSize.height}` }}
            onPointerDown={handleCanvasPointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={stopDragging}
            onPointerLeave={stopDragging}
          >
            <image
              href={imageSrc}
              width="1000"
              height="1000"
              preserveAspectRatio="none"
            />
            {zones.map((zone) => (
              <g
                key={zone.id}
                className={`roi-zone roi-zone-${zone.type} ${selectedZoneId === zone.id ? 'is-selected' : ''}`}
                onPointerDown={(event) => {
                  if (isDrawing) return
                  event.stopPropagation()
                  setSelectedZoneId(zone.id)
                  setSelectedVertex(null)
                }}
              >
                <polygon points={polygonPoints(zone.polygon)} />
                <text
                  x={zone.polygon[0]?.x ?? 0}
                  y={(zone.polygon[0]?.y ?? 0) - 12}
                >
                  {zone.label}
                </text>
                {selectedZoneId === zone.id && zone.polygon.map((point, index) => (
                  <circle
                    key={`${point.x}-${point.y}-${index}`}
                    data-vertex="true"
                    className={selectedVertex === index ? 'is-selected' : ''}
                    cx={point.x}
                    cy={point.y}
                    r="11"
                    onPointerDown={(event) => {
                      event.stopPropagation()
                      setSelectedVertex(index)
                      setDragging({ zoneId: zone.id, vertexIndex: index })
                    }}
                  />
                ))}
              </g>
            ))}
            {(occupancy?.agents ?? []).map((agent, index) => (
              <g
                key={agent.id ?? `${agent.x}-${agent.y}-${index}`}
                className={`roi-detection-point roi-detection-${agent.role}`}
              >
                <circle cx={agent.x * 1000} cy={agent.y * 1000} r="12" />
                <text x={(agent.x * 1000) + 16} y={(agent.y * 1000) - 12}>
                  {agent.role === 'staff' ? '직원' : '고객'}
                </text>
              </g>
            ))}
            {draftPoints.length > 0 && (
              <g className="roi-draft">
                <polyline points={polygonPoints(draftPoints)} />
                {draftPoints.map((point, index) => (
                  <circle key={`${point.x}-${point.y}-${index}`} cx={point.x} cy={point.y} r="10" />
                ))}
              </g>
            )}
          </svg>
        </div>

        <aside className="roi-zone-panel">
          <h4>구역 목록</h4>
          {zones.length === 0 && <p className="roi-empty">설정된 구역이 없습니다.</p>}
          <div className="roi-zone-list">
            {zones.map((zone) => (
              <button
                type="button"
                key={zone.id}
                className={selectedZoneId === zone.id ? 'active' : ''}
                onClick={() => {
                  setSelectedZoneId(zone.id)
                  setSelectedVertex(null)
                }}
              >
                <i className={`roi-swatch roi-swatch-${zone.type}`} />
                <span>{zone.label}</span>
                <small>{zone.polygon.length}개 점</small>
                {occupancy && <small>{validation.zoneCounts[zone.id] ?? 0}명 포함</small>}
              </button>
            ))}
          </div>

          {selectedZone && (
            <div className="roi-zone-form">
              <label>
                구역 종류
                <select
                  value={selectedZone.type}
                  onChange={(event) => updateSelectedZone({
                    type: event.target.value,
                    label: ZONE_LABELS[event.target.value],
                  })}
                >
                  {ZONE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              <label>
                표시 이름
                <input
                  value={selectedZone.label}
                  onChange={(event) => updateSelectedZone({ label: event.target.value })}
                />
              </label>
              <div className="roi-vertex-actions">
                <button type="button" onClick={addVertex}>꼭짓점 추가</button>
                <button
                  type="button"
                  onClick={deleteVertex}
                  disabled={selectedVertex === null}
                >
                  선택 점 삭제
                </button>
              </div>
              <button type="button" className="roi-danger-btn" onClick={deleteSelectedZone}>
                구역 삭제
              </button>
            </div>
          )}
        </aside>
      </div>

      <div className={`roi-validation roi-validation-${occupancyStatus.kind}`}>
        <div>
          <strong>현재 탐지점 검증</strong>
          <p>{occupancyStatus.message}</p>
        </div>
        {occupancy && (
          <dl>
            <div><dt>전체 탐지</dt><dd>{validation.total}명</dd></div>
            <div><dt>ROI 포함</dt><dd>{validation.matched}명</dd></div>
            <div><dt>구역 밖</dt><dd>{validation.outside}명</dd></div>
          </dl>
        )}
      </div>

      <div className="roi-apply-bar">
        <p>수동으로 설정한 구역은 이 버튼을 눌러야 Vision 설정으로 저장됩니다.</p>
        <button
          type="button"
          className="roi-primary-btn"
          onClick={saveAndApply}
          disabled={status.kind === 'loading'}
        >
          저장 및 적용
        </button>
      </div>

      <div className="roi-version-panel">
        <h4>설정 이력</h4>
        {versions.length === 0 ? (
          <p className="roi-empty">저장된 버전이 없습니다.</p>
        ) : (
          <div className="roi-version-list">
            {versions.map((version) => (
              <div key={version.version}>
                <span>
                  v{version.version} · {version.source === 'ai_assisted' ? 'AI 보조' : '수동'}
                  {' · '}{formatDate(version.created_at)}
                </span>
                {version.status === 'approved' ? (
                  <strong>적용 중</strong>
                ) : (
                  <button type="button" onClick={() => approveVersion(version.version)}>
                    다시 적용
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
