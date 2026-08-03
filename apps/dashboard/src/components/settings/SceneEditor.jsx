import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { getCameraScene } from '../store/cameraScenes'
import { DEFAULT_PERSPECTIVE } from '../store/sceneProjection'

const OBJECT_OPTIONS = [
  { value: 'table', label: '테이블' },
  { value: 'counter', label: '카운터' },
  { value: 'entrance', label: '출입구' },
  { value: 'wall', label: '벽·고정 구조물' },
  { value: 'floor', label: '바닥' },
  { value: 'occluder', label: '가림 영역' },
]

const OBJECT_LABELS = Object.fromEntries(
  OBJECT_OPTIONS.map((option) => [option.value, option.label]),
)

function pointFromEvent(event, svg) {
  const rect = svg.getBoundingClientRect()
  return {
    x: Math.max(0, Math.min(1000, Math.round(((event.clientX - rect.left) / rect.width) * 1000))),
    y: Math.max(0, Math.min(1000, Math.round(((event.clientY - rect.top) / rect.height) * 1000))),
  }
}

function polygonPoints(points) {
  return points.map((point) => `${point.x},${point.y}`).join(' ')
}

function movePolygonWithinCanvas(polygon, startPoint, currentPoint) {
  const minX = Math.min(...polygon.map((point) => point.x))
  const maxX = Math.max(...polygon.map((point) => point.x))
  const minY = Math.min(...polygon.map((point) => point.y))
  const maxY = Math.max(...polygon.map((point) => point.y))
  const deltaX = Math.max(
    -minX,
    Math.min(1000 - maxX, currentPoint.x - startPoint.x),
  )
  const deltaY = Math.max(
    -minY,
    Math.min(1000 - maxY, currentPoint.y - startPoint.y),
  )
  return polygon.map((point) => ({
    x: point.x + deltaX,
    y: point.y + deltaY,
  }))
}

function formatDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('ko-KR')
}

function makeObject(type, polygon, index) {
  return {
    id: `${type}-${Date.now()}-${index}`,
    type,
    label: OBJECT_LABELS[type],
    polygon,
  }
}

function supportedObjects(objects = []) {
  return objects
}

function objectCenter(polygon) {
  if (!polygon.length) return { x: 0, y: 0 }
  const total = polygon.reduce(
    (result, point) => ({ x: result.x + point.x, y: result.y + point.y }),
    { x: 0, y: 0 },
  )
  return { x: total.x / polygon.length, y: total.y / polygon.length }
}

function nearestTableId(point, objects) {
  return objects
    .filter((item) => item.type === 'table')
    .map((item) => ({ item, center: objectCenter(item.polygon) }))
    .sort((left, right) => (
      Math.hypot(left.center.x - point.x, left.center.y - point.y)
      - Math.hypot(right.center.x - point.x, right.center.y - point.y)
    ))[0]?.item.id ?? null
}

function deriveSeatAnchors(objects) {
  return objects
    .filter((item) => item.type === 'table' && item.polygon.length >= 3)
    .flatMap((item) => {
      const edge = [...item.polygon]
        .sort((left, right) => right.y - left.y)
        .slice(0, 2)
        .sort((left, right) => left.x - right.x)
      if (edge.length < 2) return []
      const [left, right] = edge
      const y = Math.min(Math.round((left.y + right.y) / 2 + 24), 985)
      const ratios = Math.abs(right.x - left.x) >= 125 ? [0.32, 0.68] : [0.5]
      return ratios.map((ratio, index) => ({
        id: `${item.id}-seat-${index + 1}`,
        x: Math.round(left.x + (right.x - left.x) * ratio),
        y,
        table_id: item.id,
      }))
    })
}

function defaultObjects(storeId) {
  const scene = getCameraScene(storeId)
  return supportedObjects(scene?.objects).map((item) => ({
    ...item,
    label: item.label ?? '',
    polygon: item.polygon.map(([x, y]) => ({ x, y })),
  }))
}

function defaultPerspective(storeId) {
  return { ...DEFAULT_PERSPECTIVE, ...(getCameraScene(storeId)?.perspective ?? {}) }
}

function defaultSeatAnchors(storeId, objects) {
  const anchors = getCameraScene(storeId)?.seatAnchors
  return anchors?.length ? anchors.map((anchor) => ({ ...anchor })) : deriveSeatAnchors(objects)
}

export default function SceneEditor({ apiBaseUrl, storeId }) {
  const cameraId = `${storeId}-cam1`
  const svgRef = useRef(null)
  const objectUrlRef = useRef(null)
  const [imageSrc, setImageSrc] = useState(
    () => `${apiBaseUrl}/api/stores/${storeId}/vision/raw/latest?t=${Date.now()}`,
  )
  const [imageSize, setImageSize] = useState({ width: 1920, height: 1080 })
  const [imageStatus, setImageStatus] = useState({
    kind: 'loading',
    message: '장면 보정에 사용할 원본 CCTV 이미지를 확인하는 중입니다.',
  })
  const [objects, setObjects] = useState([])
  const [perspective, setPerspective] = useState(DEFAULT_PERSPECTIVE)
  const [seatAnchors, setSeatAnchors] = useState([])
  const [versions, setVersions] = useState([])
  const [selectedObjectId, setSelectedObjectId] = useState(null)
  const [selectedVertex, setSelectedVertex] = useState(null)
  const [drawType, setDrawType] = useState('table')
  const [draftPoints, setDraftPoints] = useState([])
  const [isDrawing, setIsDrawing] = useState(false)
  const [isPlacingSeat, setIsPlacingSeat] = useState(false)
  const [dragging, setDragging] = useState(null)
  const [source, setSource] = useState('default_import')
  const [status, setStatus] = useState({ kind: 'idle', message: '' })

  const selectedObject = useMemo(
    () => objects.find((item) => item.id === selectedObjectId) ?? null,
    [objects, selectedObjectId],
  )

  const loadVersions = useCallback(async () => {
    const response = await fetch(
      `${apiBaseUrl}/api/stores/${storeId}/cameras/${cameraId}/scene-configs`,
    )
    if (!response.ok) throw new Error(`장면 이력 조회 실패 (${response.status})`)
    setVersions(await response.json())
  }, [apiBaseUrl, cameraId, storeId])

  const applyDefaults = useCallback((message = '현재 매장의 기본 장면을 불러왔습니다.') => {
    const initialObjects = defaultObjects(storeId)
    setObjects(initialObjects)
    setPerspective(defaultPerspective(storeId))
    setSeatAnchors(defaultSeatAnchors(storeId, initialObjects))
    setSelectedObjectId(initialObjects[0]?.id ?? null)
    setSelectedVertex(null)
    setSource('default_import')
    setStatus({ kind: 'idle', message })
  }, [storeId])

  const loadApproved = useCallback(async () => {
    setStatus({ kind: 'loading', message: '적용 중인 장면 설정을 불러오는 중입니다.' })
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/stores/${storeId}/cameras/${cameraId}/scene-config`,
      )
      if (response.status === 404) {
        setVersions([])
        applyDefaults('저장된 장면이 없어 현재 기본 장면을 불러왔습니다. 보정 후 저장해 주세요.')
        return
      }
      if (!response.ok) throw new Error(`장면 설정 조회 실패 (${response.status})`)
      const config = await response.json()
      const loadedObjects = supportedObjects(config.objects)
      setObjects(loadedObjects)
      setPerspective(config.perspective ?? defaultPerspective(storeId))
      setSeatAnchors(config.seat_anchors?.length
        ? config.seat_anchors
        : deriveSeatAnchors(loadedObjects))
      setImageSize(config.image_size)
      setSource(config.source)
      setSelectedObjectId(loadedObjects[0]?.id ?? null)
      try {
        await loadVersions()
      } catch (historyError) {
        setVersions([])
        setStatus({
          kind: 'error',
          message: `장면 설정은 불러왔지만 이력은 조회하지 못했습니다. ${historyError.message}`,
        })
        return
      }
      setStatus({ kind: 'success', message: `적용 중인 장면 v${config.version}을 불러왔습니다.` })
    } catch (error) {
      applyDefaults()
      setStatus({
        kind: 'error',
        message: `${error.message} 기본 장면으로 계속 편집할 수 있습니다.`,
      })
    }
  }, [apiBaseUrl, applyDefaults, cameraId, loadVersions, storeId])

  useEffect(() => {
    setDraftPoints([])
    setIsDrawing(false)
    setIsPlacingSeat(false)
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
          message: '원본 CCTV를 기준으로 장면 오브젝트를 보정합니다.',
        })
      }
    }
    probe.onerror = () => {
      setImageStatus({
        kind: 'error',
        message: '원본 CCTV 이미지가 없습니다. 설정용 이미지를 업로드해 주세요.',
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
    setImageStatus({ kind: 'loading', message: '최신 원본 CCTV 이미지를 불러오는 중입니다.' })
    setImageSrc(`${apiBaseUrl}/api/stores/${storeId}/vision/raw/latest?t=${Date.now()}`)
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
    setImageStatus({ kind: 'success', message: `${file.name} 이미지를 장면 보정 기준으로 사용합니다.` })
  }

  const startDrawing = () => {
    setDraftPoints([])
    setIsDrawing(true)
    setIsPlacingSeat(false)
    setSelectedObjectId(null)
    setSelectedVertex(null)
    setStatus({
      kind: 'idle',
      message: '오브젝트 외곽을 따라 꼭짓점을 3개 이상 지정하세요.',
    })
  }

  const completeDrawing = () => {
    if (draftPoints.length < 3) {
      setStatus({ kind: 'error', message: '꼭짓점을 3개 이상 지정해야 합니다.' })
      return
    }
    const item = makeObject(drawType, draftPoints, objects.length + 1)
    setObjects((current) => [...current, item])
    setSelectedObjectId(item.id)
    setDraftPoints([])
    setIsDrawing(false)
    setSource('manual')
    setStatus({ kind: 'idle', message: '장면 오브젝트를 추가했습니다. 꼭짓점을 끌어 보정할 수 있습니다.' })
  }

  const handleCanvasPointerDown = (event) => {
    const point = pointFromEvent(event, svgRef.current)
    if (isPlacingSeat) {
      const tableId = nearestTableId(point, objects)
      setSeatAnchors((current) => [...current, {
        id: `seat-${Date.now()}-${current.length + 1}`,
        x: point.x,
        y: point.y,
        ...(tableId ? { table_id: tableId } : {}),
      }])
      setSource('manual')
      setStatus({ kind: 'idle', message: '좌석 위치를 추가했습니다. 계속 찍거나 좌석 배치를 종료하세요.' })
      return
    }
    if (event.target.dataset.vertex === 'true' || event.target.dataset.seat === 'true') return
    if (!isDrawing) return
    setDraftPoints((current) => [...current, point])
  }

  const handlePointerMove = (event) => {
    if (!dragging) return
    const point = pointFromEvent(event, svgRef.current)
    setObjects((current) => current.map((item) => (
      item.id === dragging.objectId
        ? {
            ...item,
            polygon: dragging.kind === 'object'
              ? movePolygonWithinCanvas(
                  dragging.originalPolygon,
                  dragging.startPoint,
                  point,
                )
              : item.polygon.map((vertex, index) => (
                  index === dragging.vertexIndex ? point : vertex
                )),
          }
        : item
    )))
    setSource('manual')
  }

  const addVertex = () => {
    if (!selectedObject) return
    let longestIndex = 0
    let longestDistance = -1
    selectedObject.polygon.forEach((point, index) => {
      const next = selectedObject.polygon[(index + 1) % selectedObject.polygon.length]
      const distance = (point.x - next.x) ** 2 + (point.y - next.y) ** 2
      if (distance > longestDistance) {
        longestDistance = distance
        longestIndex = index
      }
    })
    const point = selectedObject.polygon[longestIndex]
    const next = selectedObject.polygon[(longestIndex + 1) % selectedObject.polygon.length]
    const midpoint = {
      x: Math.round((point.x + next.x) / 2),
      y: Math.round((point.y + next.y) / 2),
    }
    setObjects((current) => current.map((item) => (
      item.id === selectedObject.id
        ? {
            ...item,
            polygon: [
              ...item.polygon.slice(0, longestIndex + 1),
              midpoint,
              ...item.polygon.slice(longestIndex + 1),
            ],
          }
        : item
    )))
    setSource('manual')
  }

  const deleteVertex = () => {
    if (!selectedObject || selectedVertex === null) return
    if (selectedObject.polygon.length <= 3) {
      setStatus({ kind: 'error', message: '오브젝트에는 꼭짓점이 최소 3개 필요합니다.' })
      return
    }
    setObjects((current) => current.map((item) => (
      item.id === selectedObject.id
        ? {
            ...item,
            polygon: item.polygon.filter((_, index) => index !== selectedVertex),
          }
        : item
    )))
    setSelectedVertex(null)
    setSource('manual')
  }

  const updateSelectedObject = (changes) => {
    setObjects((current) => current.map((item) => (
      item.id === selectedObjectId ? { ...item, ...changes } : item
    )))
    setSource('manual')
  }

  const deleteSelectedObject = () => {
    setObjects((current) => current.filter((item) => item.id !== selectedObjectId))
    setSeatAnchors((current) => current.filter(
      (anchor) => anchor.table_id !== selectedObjectId,
    ))
    setSelectedObjectId(null)
    setSelectedVertex(null)
    setSource('manual')
  }

  const saveAndApply = async () => {
    if (!objects.length) {
      setStatus({ kind: 'error', message: '저장할 장면 오브젝트가 없습니다.' })
      return
    }
    setStatus({ kind: 'loading', message: '장면 설정을 저장하고 적용하는 중입니다.' })
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/stores/${storeId}/cameras/${cameraId}/scene-config`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            coordinate_space: 'normalized_1000',
            image_size: imageSize,
            source,
            objects,
            perspective,
            seat_anchors: seatAnchors,
          }),
        },
      )
      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        throw new Error(detail?.detail?.[0]?.msg ?? detail?.detail ?? `저장 실패 (${response.status})`)
      }
      const saved = await response.json()
      setObjects(supportedObjects(saved.objects))
      setPerspective(saved.perspective ?? DEFAULT_PERSPECTIVE)
      setSeatAnchors(saved.seat_anchors ?? [])
      setSource(saved.source)
      await loadVersions()
      setStatus({
        kind: 'success',
        message: `장면 v${saved.version}을 적용했습니다. 매장 화면을 다시 열면 바로 반영됩니다.`,
      })
    } catch (error) {
      setStatus({ kind: 'error', message: error.message })
    }
  }

  const approveVersion = async (version) => {
    setStatus({ kind: 'loading', message: `장면 v${version}을 다시 적용하는 중입니다.` })
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/stores/${storeId}/cameras/${cameraId}/scene-configs/${version}/approve`,
        { method: 'POST' },
      )
      if (!response.ok) throw new Error(`이전 버전 적용 실패 (${response.status})`)
      const approved = await response.json()
      const loadedObjects = supportedObjects(approved.objects)
      setObjects(loadedObjects)
      setPerspective(approved.perspective ?? defaultPerspective(storeId))
      setSeatAnchors(approved.seat_anchors?.length
        ? approved.seat_anchors
        : deriveSeatAnchors(loadedObjects))
      setImageSize(approved.image_size)
      setSource(approved.source)
      setSelectedObjectId(loadedObjects[0]?.id ?? null)
      await loadVersions()
      setStatus({ kind: 'success', message: `장면 v${version}을 다시 적용했습니다.` })
    } catch (error) {
      setStatus({ kind: 'error', message: error.message })
    }
  }

  return (
    <section className="roi-settings scene-settings" aria-labelledby="scene-settings-title">
      <div className="roi-settings-heading">
        <div>
          <p className="roi-eyebrow">DIGITAL TWIN SETUP</p>
          <h3 id="scene-settings-title">카메라 장면 보정</h3>
          <p>{storeId} · {cameraId}</p>
        </div>
        <div className="scene-heading-actions">
          <button type="button" className="roi-secondary-btn" onClick={() => applyDefaults()}>
            기본 장면 불러오기
          </button>
          <button type="button" className="roi-secondary-btn" onClick={loadApproved}>
            적용 설정 다시 불러오기
          </button>
        </div>
      </div>

      <div className="roi-toolbar">
        <button type="button" className="roi-secondary-btn" onClick={useLatestImage}>
          최신 원본 CCTV 이미지
        </button>
        <label className="roi-file-btn">
          설정용 이미지 업로드
          <input type="file" accept="image/jpeg,image/png" onChange={handleFile} />
        </label>
        <select value={drawType} onChange={(event) => setDrawType(event.target.value)}>
          {OBJECT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        {!isDrawing ? (
          <button type="button" className="roi-secondary-btn" onClick={startDrawing}>
            오브젝트 그리기
          </button>
        ) : (
          <>
            <button type="button" className="roi-primary-btn" onClick={completeDrawing}>
              오브젝트 완성
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
        <button
          type="button"
          className={isPlacingSeat ? 'roi-primary-btn' : 'roi-secondary-btn'}
          disabled={isDrawing}
          onClick={() => {
            setIsPlacingSeat((current) => !current)
            setStatus({
              kind: 'idle',
              message: isPlacingSeat
                ? '좌석 배치를 종료했습니다.'
                : 'CCTV 화면에서 실제 의자 중심을 클릭하세요.',
            })
          }}
        >
          {isPlacingSeat ? '좌석 배치 종료' : '좌석 위치 찍기'}
        </button>
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
            className={`roi-canvas scene-canvas ${isDrawing ? 'is-drawing' : ''} ${isPlacingSeat ? 'is-placing-seat' : ''}`}
            viewBox="0 0 1000 1000"
            preserveAspectRatio="none"
            style={{ aspectRatio: `${imageSize.width} / ${imageSize.height}` }}
            onPointerDown={handleCanvasPointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={() => setDragging(null)}
            onPointerCancel={() => setDragging(null)}
          >
            <image href={imageSrc} width="1000" height="1000" preserveAspectRatio="none" />
            <g className="scene-perspective-guides" aria-hidden="true">
              <line x1="0" x2="1000" y1={perspective.far_y} y2={perspective.far_y} />
              <text x="18" y={Math.max(perspective.far_y - 12, 24)}>원거리 기준</text>
              <line x1="0" x2="1000" y1={perspective.near_y} y2={perspective.near_y} />
              <text x="18" y={Math.max(perspective.near_y - 12, 24)}>근거리 기준</text>
            </g>
            {objects.map((item) => (
              <g
                key={item.id}
                className={`scene-editor-object scene-editor-${item.type} ${selectedObjectId === item.id ? 'is-selected' : ''}`}
                onPointerDown={(event) => {
                  if (isDrawing || isPlacingSeat) return
                  event.stopPropagation()
                  event.preventDefault()
                  event.currentTarget.setPointerCapture?.(event.pointerId)
                  setSelectedObjectId(item.id)
                  setSelectedVertex(null)
                  setDragging({
                    kind: 'object',
                    objectId: item.id,
                    startPoint: pointFromEvent(event, svgRef.current),
                    originalPolygon: item.polygon.map((point) => ({ ...point })),
                  })
                }}
              >
                <polygon points={polygonPoints(item.polygon)} />
                {item.label && (
                  <text
                    x={item.polygon[0]?.x ?? 0}
                    y={Math.max((item.polygon[0]?.y ?? 0) - 12, 24)}
                  >
                    {item.label}
                  </text>
                )}
                {selectedObjectId === item.id && item.polygon.map((point, index) => (
                  <circle
                    key={`${point.x}-${point.y}-${index}`}
                    data-vertex="true"
                    className={selectedVertex === index ? 'is-selected' : ''}
                    cx={point.x}
                    cy={point.y}
                    r="11"
                    onPointerDown={(event) => {
                      if (isPlacingSeat) return
                      event.stopPropagation()
                      event.preventDefault()
                      event.currentTarget.setPointerCapture?.(event.pointerId)
                      setSelectedVertex(index)
                      setDragging({
                        kind: 'vertex',
                        objectId: item.id,
                        vertexIndex: index,
                      })
                    }}
                  />
                ))}
              </g>
            ))}
            {seatAnchors.map((anchor, index) => (
              <g className="scene-seat-anchor" key={anchor.id}>
                <circle data-seat="true" cx={anchor.x} cy={anchor.y} r="15" />
                <text x={anchor.x + 22} y={anchor.y - 16}>{index + 1}</text>
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
          <div className="scene-perspective-form">
            <h4>원근 보정</h4>
            <label>
              원거리 기준선
              <input
                type="range"
                min="0"
                max={perspective.near_y - 1}
                value={perspective.far_y}
                onChange={(event) => {
                  setPerspective((current) => ({ ...current, far_y: Number(event.target.value) }))
                  setSource('manual')
                }}
              />
              <span>{perspective.far_y}</span>
            </label>
            <label>
              근거리 기준선
              <input
                type="range"
                min={perspective.far_y + 1}
                max="1000"
                value={perspective.near_y}
                onChange={(event) => {
                  setPerspective((current) => ({ ...current, near_y: Number(event.target.value) }))
                  setSource('manual')
                }}
              />
              <span>{perspective.near_y}</span>
            </label>
            <div className="scene-scale-inputs">
              <label>
                원거리 크기
                <input
                  type="number"
                  min="0.35"
                  max="1"
                  step="0.01"
                  value={perspective.far_scale}
                  onChange={(event) => {
                    setPerspective((current) => ({ ...current, far_scale: Number(event.target.value) }))
                    setSource('manual')
                  }}
                />
              </label>
              <label>
                근거리 크기
                <input
                  type="number"
                  min="0.8"
                  max="2"
                  step="0.01"
                  value={perspective.near_scale}
                  onChange={(event) => {
                    setPerspective((current) => ({ ...current, near_scale: Number(event.target.value) }))
                    setSource('manual')
                  }}
                />
              </label>
            </div>
          </div>

          <h4>장면 오브젝트</h4>
          {objects.length === 0 && <p className="roi-empty">설정된 오브젝트가 없습니다.</p>}
          <div className="roi-zone-list">
            {objects.map((item) => (
              <button
                type="button"
                key={item.id}
                className={selectedObjectId === item.id ? 'active' : ''}
                onClick={() => {
                  setSelectedObjectId(item.id)
                  setSelectedVertex(null)
                }}
              >
                <i className={`roi-swatch scene-swatch-${item.type}`} />
                <span>{item.label || OBJECT_LABELS[item.type]}</span>
                <small>{item.polygon.length}개 점</small>
              </button>
            ))}
          </div>

          {selectedObject && (
            <div className="roi-zone-form">
              <label>
                오브젝트 종류
                <select
                  value={selectedObject.type}
                  onChange={(event) => updateSelectedObject({
                    type: event.target.value,
                    label: OBJECT_LABELS[event.target.value],
                  })}
                >
                  {OBJECT_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              <label>
                표시 이름
                <input
                  value={selectedObject.label}
                  onChange={(event) => updateSelectedObject({ label: event.target.value })}
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
              <button type="button" className="roi-danger-btn" onClick={deleteSelectedObject}>
                오브젝트 삭제
              </button>
            </div>
          )}

          <div className="scene-seat-list">
            <div>
              <h4>좌석 앵커</h4>
              <button
                type="button"
                onClick={() => {
                  setSeatAnchors(deriveSeatAnchors(objects))
                  setSource('manual')
                }}
              >
                테이블 기준 자동 배치
              </button>
            </div>
            {seatAnchors.length === 0 ? (
              <p className="roi-empty">등록된 좌석이 없습니다.</p>
            ) : seatAnchors.map((anchor, index) => (
              <div key={anchor.id}>
                <span>좌석 {index + 1} · ({anchor.x}, {anchor.y})</span>
                <button
                  type="button"
                  onClick={() => {
                    setSeatAnchors((current) => current.filter((item) => item.id !== anchor.id))
                    setSource('manual')
                  }}
                >
                  삭제
                </button>
              </div>
            ))}
          </div>
        </aside>
      </div>

      <div className="roi-apply-bar">
        <p>저장하면 점주 대시보드의 카메라 디지털 트윈 장면에 적용됩니다.</p>
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
        <h4>장면 설정 이력</h4>
        {versions.length === 0 ? (
          <p className="roi-empty">저장된 버전이 없습니다.</p>
        ) : (
          <div className="roi-version-list">
            {versions.map((version) => (
              <div key={version.version}>
                <span>
                  v{version.version} · {version.source === 'manual' ? '수동 보정' : '기본 장면'}
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
