import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { getCameraScene } from '../store/cameraScenes'

const OBJECT_OPTIONS = [
  { value: 'table', label: '테이블' },
  { value: 'counter', label: '카운터' },
  { value: 'entrance', label: '출입구' },
  { value: 'wall', label: '벽·고정 구조물' },
  { value: 'floor', label: '바닥' },
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
  return objects.filter((item) => item.type !== 'occluder')
}

function defaultObjects(storeId) {
  const scene = getCameraScene(storeId)
  return supportedObjects(scene?.objects).map((item) => ({
    ...item,
    label: item.label ?? '',
    polygon: item.polygon.map(([x, y]) => ({ x, y })),
  }))
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
  const [versions, setVersions] = useState([])
  const [selectedObjectId, setSelectedObjectId] = useState(null)
  const [selectedVertex, setSelectedVertex] = useState(null)
  const [drawType, setDrawType] = useState('table')
  const [draftPoints, setDraftPoints] = useState([])
  const [isDrawing, setIsDrawing] = useState(false)
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
    if (!isDrawing || event.target.dataset.vertex === 'true') return
    setDraftPoints((current) => [...current, pointFromEvent(event, svgRef.current)])
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
          }),
        },
      )
      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        throw new Error(detail?.detail?.[0]?.msg ?? detail?.detail ?? `저장 실패 (${response.status})`)
      }
      const saved = await response.json()
      setObjects(supportedObjects(saved.objects))
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
            className={`roi-canvas scene-canvas ${isDrawing ? 'is-drawing' : ''}`}
            viewBox="0 0 1000 1000"
            preserveAspectRatio="none"
            style={{ aspectRatio: `${imageSize.width} / ${imageSize.height}` }}
            onPointerDown={handleCanvasPointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={() => setDragging(null)}
            onPointerCancel={() => setDragging(null)}
          >
            <image href={imageSrc} width="1000" height="1000" preserveAspectRatio="none" />
            {objects.map((item) => (
              <g
                key={item.id}
                className={`scene-editor-object scene-editor-${item.type} ${selectedObjectId === item.id ? 'is-selected' : ''}`}
                onPointerDown={(event) => {
                  if (isDrawing) return
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
