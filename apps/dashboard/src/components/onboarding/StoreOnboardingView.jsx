import { useEffect, useMemo, useRef, useState } from 'react'

import { authenticatedFetch } from '../../api/authenticatedFetch'
import {
  createAnalysisJob,
  probeUploadApi,
  uploadStoreMedia,
} from '../../api/storeMediaApi'
import {
  REQUIRES_TAILSCALE_UPLOAD,
  UPLOAD_API_BASE_URL,
} from '../../constants/env'
import { imageSourceToPayload } from '../settings/sceneSuggestion'
import './StoreOnboardingView.css'
import { extractVideoPoster } from './extractVideoPoster'
import {
  buildOnboardingPayloads,
  ONBOARDING_ZONE_TYPES,
  onboardingZoneLabel,
  validateOnboardingDraft,
} from './storeOnboarding'

const STEPS = [
  { title: '분석 소스', description: '영상 또는 프레임 ZIP을 등록합니다.' },
  { title: '대표 사진', description: '현재 카메라 구도를 확인합니다.' },
  { title: 'AI 테이블 검수', description: '탐지 결과를 확인하고 잘못된 항목을 제거합니다.' },
  { title: '바닥 영역', description: '사람이 이동할 매장 바닥을 지정합니다.' },
  { title: '운영 구역', description: '필요한 분석 구역만 선택해서 지정합니다.' },
  { title: '저장 및 적용', description: 'Scene/ROI 저장 후 분석을 시작합니다.' },
]

const OVERLAY_COLORS = {
  table: '#38bdf8',
  counter: '#f59e0b',
  floor: '#a3e635',
  staff: '#fb7185',
  waiting: '#facc15',
  entrance: '#2dd4bf',
  seating: '#c084fc',
}

function pointFromEvent(event, svg) {
  const rect = svg.getBoundingClientRect()
  return {
    x: Math.max(0, Math.min(1000, Math.round(((event.clientX - rect.left) / rect.width) * 1000))),
    y: Math.max(0, Math.min(1000, Math.round(((event.clientY - rect.top) / rect.height) * 1000))),
  }
}

function polygonPoints(points = []) {
  return points.map((point) => `${point.x},${point.y}`).join(' ')
}

function errorMessage(detail, fallback) {
  const message = detail?.detail?.message
    ?? detail?.detail?.[0]?.msg
    ?? detail?.detail
    ?? fallback
  return typeof message === 'string' ? message : fallback
}

function entrancePolygon(point) {
  const halfWidth = 45
  const halfHeight = 65
  const left = Math.max(0, point.x - halfWidth)
  const right = Math.min(1000, point.x + halfWidth)
  const top = Math.max(0, point.y - halfHeight)
  const bottom = Math.min(1000, point.y + halfHeight)
  return [
    { x: left, y: top },
    { x: right, y: top },
    { x: right, y: bottom },
    { x: left, y: bottom },
  ]
}

export default function StoreOnboardingView({
  apiBaseUrl,
  aiccBaseUrl,
  storeId,
  onComplete,
}) {
  const cameraId = `${storeId}-cam1`
  const svgRef = useRef(null)
  const objectUrlRef = useRef(null)
  const [step, setStep] = useState(0)
  const [imageSrc, setImageSrc] = useState('')
  const [imageSize, setImageSize] = useState(null)
  const [imageName, setImageName] = useState('')
  const [sceneObjects, setSceneObjects] = useState([])
  const [analysis, setAnalysis] = useState(null)
  const [isDrawingTable, setIsDrawingTable] = useState(false)
  const [tableDraftPoints, setTableDraftPoints] = useState([])
  const [floorPoints, setFloorPoints] = useState([])
  const [zones, setZones] = useState([])
  const [activeZoneType, setActiveZoneType] = useState('staff')
  const [draftZonePoints, setDraftZonePoints] = useState([])
  const [dragging, setDragging] = useState(null)
  const [status, setStatus] = useState({ kind: 'idle', message: '' })
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isUploadingMedia, setIsUploadingMedia] = useState(false)
  const [savedVersions, setSavedVersions] = useState(null)
  const [uploadedMedia, setUploadedMedia] = useState(null)
  const [analysisJob, setAnalysisJob] = useState(null)
  const [uploadApiReady, setUploadApiReady] = useState(!REQUIRES_TAILSCALE_UPLOAD)
  const [uploadApiChecked, setUploadApiChecked] = useState(!REQUIRES_TAILSCALE_UPLOAD)

  useEffect(() => () => {
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
  }, [])

  useEffect(() => {
    let cancelled = false
    if (!REQUIRES_TAILSCALE_UPLOAD) {
      setUploadApiReady(true)
      setUploadApiChecked(true)
      return undefined
    }
    setUploadApiChecked(false)
    probeUploadApi().then((ok) => {
      if (cancelled) return
      setUploadApiReady(ok)
      setUploadApiChecked(true)
      if (!ok) {
        setStatus({
          kind: 'error',
          message:
            'Tailscale 업로드 API에 연결할 수 없습니다. PC에서 Tailscale 로그인 후 다시 열어 주세요.',
        })
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  const tableObjects = useMemo(
    () => sceneObjects.filter((object) => object.type === 'table'),
    [sceneObjects],
  )
  const validationErrors = useMemo(
    () => validateOnboardingDraft({ imageSize, sceneObjects, floorPoints, zones }),
    [floorPoints, imageSize, sceneObjects, zones],
  )

  const applyImageFile = (file, label) => {
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
    const nextUrl = URL.createObjectURL(file)
    objectUrlRef.current = nextUrl
    setImageSrc(nextUrl)
    setImageName(label || file.name)
    setImageSize(null)
    setSceneObjects([])
    setAnalysis(null)
    setIsDrawingTable(false)
    setTableDraftPoints([])
    setFloorPoints([])
    setZones([])
    setDraftZonePoints([])
    setSavedVersions(null)
    setAnalysisJob(null)
  }

  const selectMediaSource = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (!uploadApiReady) {
      setStatus({
        kind: 'error',
        message: 'Tailscale 업로드 API가 준비되지 않아 파일을 올릴 수 없습니다.',
      })
      event.target.value = ''
      return
    }
    const name = file.name.toLowerCase()
    const isVideo = file.type.startsWith('video/') || /\.(mp4|webm|mov)$/.test(name)
    const isZip = file.type.includes('zip') || name.endsWith('.zip')
    if (!isVideo && !isZip) {
      setStatus({ kind: 'error', message: 'mp4/webm/mov 영상 또는 프레임 ZIP만 업로드할 수 있습니다.' })
      return
    }
    setIsUploadingMedia(true)
    setStatus({ kind: 'loading', message: '분석 소스를 업로드하고 있습니다.' })
    try {
      const media = await uploadStoreMedia(storeId, file)
      setUploadedMedia(media)
      if (isVideo) {
        const poster = await extractVideoPoster(file)
        applyImageFile(poster, `${file.name}-poster.jpg`)
        setStatus({
          kind: 'success',
          message: '영상 업로드 완료. 대표 프레임을 뽑았습니다. 다음 단계에서 구도를 확인하세요.',
        })
      } else {
        setStatus({
          kind: 'success',
          message: 'ZIP 업로드 완료. 다음 단계에서 대표 사진(JPEG/PNG)을 선택해 주세요.',
        })
      }
    } catch (error) {
      setStatus({ kind: 'error', message: error.message })
    } finally {
      setIsUploadingMedia(false)
      event.target.value = ''
    }
  }

  const selectImage = (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (!['image/jpeg', 'image/png'].includes(file.type)) {
      setStatus({ kind: 'error', message: 'JPEG 또는 PNG 사진만 등록할 수 있습니다.' })
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      setStatus({ kind: 'error', message: '사진 크기는 5MB 이하여야 합니다.' })
      return
    }
    applyImageFile(file)
    setStatus({ kind: 'idle', message: '사진을 확인한 뒤 다음 단계로 이동하세요.' })
  }

  const analyzeImage = async () => {
    if (!imageSrc || !imageSize) {
      setStatus({ kind: 'error', message: '분석할 사진을 먼저 등록해 주세요.' })
      return
    }
    setIsAnalyzing(true)
    setStatus({ kind: 'loading', message: 'AI가 사진에서 테이블을 찾고 있습니다.' })
    try {
      const image = await imageSourceToPayload(imageSrc)
      const response = await authenticatedFetch(
        `${aiccBaseUrl.replace(/\/$/, '')}/scene-suggestions`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            store_id: storeId,
            camera_id: cameraId,
            image_base64: image.imageBase64,
            mime_type: image.mimeType,
            image_width: imageSize.width,
            image_height: imageSize.height,
            use_reference_frames: false,
          }),
        },
      )
      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        throw new Error(errorMessage(detail, `AI 분석 실패 (${response.status})`))
      }
      const result = await response.json()
      setAnalysis(result)
      setSceneObjects(result.objects ?? [])
      setIsDrawingTable(false)
      setTableDraftPoints([])
      setStatus({
        kind: 'success',
        message: `테이블 ${(result.objects ?? []).filter((item) => item.type === 'table').length}개를 찾았습니다. 외곽점을 끌어 보정할 수 있습니다.`,
      })
    } catch (error) {
      setStatus({ kind: 'error', message: error.message })
    } finally {
      setIsAnalyzing(false)
    }
  }

  const removeSceneObject = (objectId) => {
    setSceneObjects((current) => current.filter((object) => object.id !== objectId))
  }

  const handleCanvasClick = (event) => {
    if (dragging || !svgRef.current) return
    const point = pointFromEvent(event, svgRef.current)
    if (step === 2 && isDrawingTable) {
      setTableDraftPoints((current) => [...current, point])
      return
    }
    if (step === 3) {
      setFloorPoints((current) => [...current, point])
    }
    if (step === 4) {
      if (activeZoneType === 'entrance') {
        setZones((current) => [
          ...current.filter((zone) => zone.type !== 'entrance'),
          {
            id: `entrance-${Date.now()}`,
            type: 'entrance',
            label: onboardingZoneLabel('entrance'),
            polygon: entrancePolygon(point),
          },
        ])
        setDraftZonePoints([])
        setStatus({ kind: 'success', message: '출입구 위치를 지정했습니다.' })
        return
      }
      setDraftZonePoints((current) => [...current, point])
    }
  }

  const handlePointerMove = (event) => {
    if (!dragging || !svgRef.current) return
    const point = pointFromEvent(event, svgRef.current)
    setSceneObjects((current) => current.map((object) => (
      object.id === dragging.objectId
        ? {
            ...object,
            polygon: object.polygon.map((vertex, index) => (
              index === dragging.vertexIndex ? point : vertex
            )),
          }
        : object
    )))
  }

  const addZone = () => {
    if (draftZonePoints.length < 3) {
      setStatus({ kind: 'error', message: '구역 외곽점을 3개 이상 찍어 주세요.' })
      return
    }
    const nextZone = {
      id: `${activeZoneType}-${Date.now()}`,
      type: activeZoneType,
      label: onboardingZoneLabel(activeZoneType),
      polygon: draftZonePoints,
    }
    setZones((current) => [
      ...current.filter((zone) => zone.type !== activeZoneType),
      nextZone,
    ])
    setDraftZonePoints([])
    setStatus({ kind: 'success', message: `${nextZone.label}을 지정했습니다.` })
  }

  const completeTableDrawing = () => {
    if (tableDraftPoints.length < 3) {
      setStatus({ kind: 'error', message: '테이블 외곽점을 3개 이상 찍어 주세요.' })
      return
    }
    const tableNumber = tableObjects.length + 1
    const table = {
      id: `manual-table-${Date.now()}`,
      type: 'table',
      label: `수동 테이블 ${tableNumber}`,
      polygon: tableDraftPoints,
    }
    setSceneObjects((current) => [...current, table])
    setTableDraftPoints([])
    setIsDrawingTable(false)
    setStatus({ kind: 'success', message: `${table.label}을 추가했습니다.` })
  }

  const saveOnboarding = async () => {
    if (validationErrors.length) {
      setStatus({ kind: 'error', message: validationErrors[0] })
      return
    }
    setIsSaving(true)
    setStatus({ kind: 'loading', message: 'Scene 설정을 저장하고 있습니다.' })
    try {
      const payloads = buildOnboardingPayloads({
        imageSize,
        sceneObjects,
        floorPoints,
        zones,
      })
      const sceneResponse = await authenticatedFetch(
        `${apiBaseUrl}/api/stores/${storeId}/cameras/${cameraId}/scene-config`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payloads.scene),
        },
      )
      if (!sceneResponse.ok) {
        const detail = await sceneResponse.json().catch(() => null)
        throw new Error(errorMessage(detail, `Scene 저장 실패 (${sceneResponse.status})`))
      }
      const savedScene = await sceneResponse.json()

      let savedRoi = null
      if (payloads.roi) {
        setStatus({ kind: 'loading', message: '선택한 운영 ROI 설정을 저장하고 있습니다.' })
        const roiResponse = await authenticatedFetch(
          `${apiBaseUrl}/api/stores/${storeId}/cameras/${cameraId}/roi-config`,
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payloads.roi),
          },
        )
        if (!roiResponse.ok) {
          const detail = await roiResponse.json().catch(() => null)
          throw new Error(errorMessage(
            detail,
            `Scene v${savedScene.version} 저장 후 ROI 저장 실패 (${roiResponse.status})`,
          ))
        }
        savedRoi = await roiResponse.json()
      }
      const completion = {
        completedAt: new Date().toISOString(),
        sceneVersion: savedScene.version,
        roiVersion: savedRoi?.version ?? null,
      }
      window.localStorage.setItem(
        `aiseeye.store-onboarding.${storeId}`,
        JSON.stringify(completion),
      )
      setSavedVersions(completion)
      if (!uploadedMedia?.id) {
        throw new Error('분석 소스가 없습니다. 처음부터 영상/ZIP을 업로드해 주세요.')
      }
      setStatus({ kind: 'loading', message: 'GPU 분석 job을 등록하고 있습니다.' })
      const job = await createAnalysisJob(storeId, uploadedMedia.id)
      setAnalysisJob(job)
      setStatus({
        kind: 'success',
        message: savedRoi
          ? `온보딩 완료 · Scene v${savedScene.version}, ROI v${savedRoi.version} · 분석 job ${job.status}`
          : `온보딩 완료 · Scene v${savedScene.version} · 분석 job ${job.status}`,
      })
    } catch (error) {
      setStatus({ kind: 'error', message: error.message })
    } finally {
      setIsSaving(false)
    }
  }

  const canGoNext = () => {
    if (step === 0) return Boolean(uploadedMedia?.id)
    if (step === 1) return Boolean(imageSrc && imageSize)
    if (step === 2) return tableObjects.length > 0
    if (step === 3) return floorPoints.length >= 3
    if (step === 4) return true
    return false
  }

  return (
    <section className="store-onboarding" aria-labelledby="store-onboarding-title">
      <header className="store-onboarding-heading">
        <div>
          <p className="eyebrow">STORE ONBOARDING MVP</p>
          <h3 id="store-onboarding-title">매장 카메라 온보딩</h3>
          <p>{storeId} · {cameraId} · 업로드 소스 + Scene/ROI로 분석을 시작합니다.</p>
        </div>
        <span className="onboarding-scope-badge">업로드형 온보딩</span>
      </header>

      <ol className="onboarding-steps">
        {STEPS.map((item, index) => (
          <li
            key={item.title}
            className={[
              index === step ? 'is-active' : '',
              index < step ? 'is-complete' : '',
            ].filter(Boolean).join(' ')}
          >
            <span>{index < step ? '✓' : index + 1}</span>
            <div>
              <strong>{item.title}</strong>
              <small>{item.description}</small>
            </div>
          </li>
        ))}
      </ol>

      <div className="onboarding-workspace">
        <div className="onboarding-canvas-card">
          <div className="onboarding-canvas">
            {imageSrc ? (
              <>
                <img
                  src={imageSrc}
                  alt="온보딩용 매장 카메라"
                  onLoad={(event) => setImageSize({
                    width: event.currentTarget.naturalWidth,
                    height: event.currentTarget.naturalHeight,
                  })}
                />
                <svg
                  ref={svgRef}
                  viewBox="0 0 1000 1000"
                  preserveAspectRatio="none"
                  onClick={handleCanvasClick}
                  onPointerMove={handlePointerMove}
                  onPointerUp={() => setDragging(null)}
                  onPointerLeave={() => setDragging(null)}
                >
                  {step >= 2 && sceneObjects.map((object) => (
                    <g key={object.id}>
                      <polygon
                        points={polygonPoints(object.polygon)}
                        fill={`${OVERLAY_COLORS[object.type] ?? '#38bdf8'}33`}
                        stroke={OVERLAY_COLORS[object.type] ?? '#38bdf8'}
                        strokeWidth="5"
                      />
                      {step === 2 && object.polygon.map((point, index) => (
                        <circle
                          key={`${object.id}-${point.x}-${point.y}-${index}`}
                          cx={point.x}
                          cy={point.y}
                          r="12"
                          fill="#ffffff"
                          stroke={OVERLAY_COLORS[object.type] ?? '#38bdf8'}
                          strokeWidth="5"
                          onClick={(event) => event.stopPropagation()}
                          onPointerDown={(event) => {
                            event.stopPropagation()
                            setDragging({ objectId: object.id, vertexIndex: index })
                          }}
                        />
                      ))}
                    </g>
                  ))}
                  {step === 2 && isDrawingTable && tableDraftPoints.length > 0 && (
                    <g>
                      <polyline
                        points={polygonPoints(tableDraftPoints)}
                        fill="none"
                        stroke={OVERLAY_COLORS.table}
                        strokeWidth="6"
                        strokeDasharray="12 10"
                      />
                      {tableDraftPoints.map((point, index) => (
                        <circle
                          key={`table-draft-${point.x}-${point.y}-${index}`}
                          cx={point.x}
                          cy={point.y}
                          r="11"
                          fill={OVERLAY_COLORS.table}
                        />
                      ))}
                    </g>
                  )}
                  {step >= 3 && floorPoints.length > 0 && (
                    <g>
                      <polygon
                        points={polygonPoints(floorPoints)}
                        fill={`${OVERLAY_COLORS.floor}20`}
                        stroke={OVERLAY_COLORS.floor}
                        strokeWidth="5"
                        strokeDasharray="14 10"
                      />
                      {step === 3 && floorPoints.map((point, index) => (
                        <circle
                          key={`floor-${point.x}-${point.y}-${index}`}
                          cx={point.x}
                          cy={point.y}
                          r="11"
                          fill={OVERLAY_COLORS.floor}
                        />
                      ))}
                    </g>
                  )}
                  {step >= 4 && zones.map((zone) => (
                    <polygon
                      key={zone.id}
                      points={polygonPoints(zone.polygon)}
                      fill={`${OVERLAY_COLORS[zone.type]}30`}
                      stroke={OVERLAY_COLORS[zone.type]}
                      strokeWidth="6"
                    />
                  ))}
                  {step === 4 && draftZonePoints.length > 0 && (
                    <g>
                      <polyline
                        points={polygonPoints(draftZonePoints)}
                        fill="none"
                        stroke={OVERLAY_COLORS[activeZoneType]}
                        strokeWidth="6"
                        strokeDasharray="12 10"
                      />
                      {draftZonePoints.map((point, index) => (
                        <circle
                          key={`zone-draft-${point.x}-${point.y}-${index}`}
                          cx={point.x}
                          cy={point.y}
                          r="11"
                          fill={OVERLAY_COLORS[activeZoneType]}
                        />
                      ))}
                    </g>
                  )}
                </svg>
              </>
            ) : (
              <div className="onboarding-empty">
                <strong>매장 대표 사진을 등록하세요</strong>
                <span>테이블과 출입구가 함께 보이는 고정 카메라 구도가 좋습니다.</span>
              </div>
            )}
          </div>
          <footer>
            <span>{imageName || '등록된 사진 없음'}</span>
            <span>{imageSize ? `${imageSize.width} × ${imageSize.height}` : '-'}</span>
          </footer>
        </div>

        <aside className="onboarding-panel">
          <h4>{STEPS[step].title}</h4>
          <p>{STEPS[step].description}</p>

          {step === 0 && (
            <div className="onboarding-control-group">
              {REQUIRES_TAILSCALE_UPLOAD && uploadApiChecked && !uploadApiReady && (
                <p className="onboarding-help">
                  클라우드 대시보드의 대용량 업로드는 Cloudflare를 거치지 않고
                  Tailscale HTTPS({UPLOAD_API_BASE_URL})로만 동작합니다.
                  Tailscale에 로그인한 PC에서 다시 시도하거나,
                  데모용으로 http://100.86.5.67:5173 온보딩을 사용하세요.
                </p>
              )}
              <label className="onboarding-upload">
                영상(mp4/webm/mov) 또는 프레임 ZIP
                <input
                  type="file"
                  accept="video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov,application/zip,.zip"
                  onChange={selectMediaSource}
                  disabled={isUploadingMedia || !uploadApiReady}
                />
              </label>
              {uploadedMedia && (
                <p>
                  등록됨: {uploadedMedia.filename}
                  {' '}
                  ({Math.round(uploadedMedia.size_bytes / 1024)} KB)
                </p>
              )}
              <ul className="onboarding-help">
                <li>최대 약 200MB</li>
                <li>영상은 업로드 후 대표 프레임을 자동으로 뽑습니다</li>
                <li>ZIP은 다음 단계에서 대표 JPEG/PNG를 직접 선택합니다</li>
                <li>실카메라(RTSP) 연결은 이번 범위에 없습니다</li>
                {REQUIRES_TAILSCALE_UPLOAD && (
                  <li>업로드 API: {UPLOAD_API_BASE_URL}</li>
                )}
              </ul>
            </div>
          )}

          {step === 1 && (
            <div className="onboarding-control-group">
              <label className="onboarding-upload">
                JPEG/PNG 대표 사진 선택/변경
                <input type="file" accept="image/jpeg,image/png" onChange={selectImage} />
              </label>
              <ul className="onboarding-help">
                <li>최대 5MB</li>
                <li>실제 운영 카메라와 같은 구도의 사진 권장</li>
                <li>영상 업로드 시 자동으로 뽑힌 프레임을 써도 됩니다</li>
              </ul>
            </div>
          )}

          {step === 2 && (
            <div className="onboarding-control-group">
              {!isDrawingTable ? (
                <div className="onboarding-inline-actions">
                  <button
                    type="button"
                    className="onboarding-primary"
                    disabled={isAnalyzing}
                    onClick={analyzeImage}
                  >
                    {isAnalyzing ? 'AI 분석 중…' : analysis ? '다시 분석' : 'AI 테이블 분석'}
                  </button>
                  <button
                    type="button"
                    className="onboarding-secondary"
                    disabled={isAnalyzing}
                    onClick={() => {
                      setIsDrawingTable(true)
                      setTableDraftPoints([])
                      setStatus({
                        kind: 'idle',
                        message: '사진에서 새 테이블의 외곽점을 순서대로 찍어 주세요.',
                      })
                    }}
                  >
                    테이블 직접 추가
                  </button>
                </div>
              ) : (
                <>
                  <p>사진에서 테이블 외곽을 따라 꼭짓점을 3개 이상 찍으세요.</p>
                  <strong>현재 꼭짓점 {tableDraftPoints.length}개</strong>
                  <div className="onboarding-inline-actions">
                    <button
                      type="button"
                      className="onboarding-secondary"
                      onClick={() => {
                        setIsDrawingTable(false)
                        setTableDraftPoints([])
                      }}
                    >
                      취소
                    </button>
                    <button
                      type="button"
                      className="onboarding-primary"
                      onClick={completeTableDrawing}
                    >
                      새 테이블 확정
                    </button>
                  </div>
                </>
              )}
              {analysis && (
                <div className="onboarding-detection-list">
                  {sceneObjects.map((object) => (
                    <div key={object.id}>
                      <span>{object.label || object.type}</span>
                      <button type="button" onClick={() => removeSceneObject(object.id)}>
                        제거
                      </button>
                    </div>
                  ))}
                  {!sceneObjects.length && <p>확인된 오브젝트가 없습니다.</p>}
                </div>
              )}
            </div>
          )}

          {step === 3 && (
            <div className="onboarding-control-group">
              <p>사진에서 사람이 이동할 수 있는 바닥 외곽을 순서대로 클릭하세요.</p>
              <strong>현재 꼭짓점 {floorPoints.length}개</strong>
              <button
                type="button"
                className="onboarding-secondary"
                onClick={() => setFloorPoints([])}
              >
                바닥 다시 그리기
              </button>
            </div>
          )}

          {step === 4 && (
            <div className="onboarding-control-group">
              <div className="onboarding-zone-tabs">
                {ONBOARDING_ZONE_TYPES.map((zone) => (
                  <button
                    type="button"
                    key={zone.value}
                    className={activeZoneType === zone.value ? 'is-active' : ''}
                    onClick={() => {
                      setActiveZoneType(zone.value)
                      setDraftZonePoints([])
                    }}
                  >
                    {zones.some((item) => item.type === zone.value) ? '✓ ' : ''}
                    {zone.label}
                  </button>
                ))}
              </div>
              {activeZoneType === 'entrance' ? (
                <p>사진에서 출입구 위치를 한 번 클릭하세요. 작은 출입구 영역이 자동 생성됩니다.</p>
              ) : (
                <>
                  <p>필요한 경우에만 구역의 외곽점을 사진 위에 3개 이상 찍으세요.</p>
                  <div className="onboarding-inline-actions">
                    <button
                      type="button"
                      className="onboarding-secondary"
                      onClick={() => setDraftZonePoints([])}
                    >
                      점 초기화
                    </button>
                    <button type="button" className="onboarding-primary" onClick={addZone}>
                      {onboardingZoneLabel(activeZoneType)} 확정
                    </button>
                  </div>
                </>
              )}
              <small>운영 구역은 선택 사항이며 나중에 설정에서 추가할 수 있습니다.</small>
              <div className="onboarding-detection-list">
                {zones.map((zone) => (
                  <div key={zone.id}>
                    <span>{zone.label}</span>
                    <button
                      type="button"
                      onClick={() => setZones((current) => (
                        current.filter((item) => item.id !== zone.id)
                      ))}
                    >
                      제거
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {step === 5 && (
            <div className="onboarding-control-group">
              <dl className="onboarding-summary">
                <div><dt>카메라</dt><dd>{cameraId}</dd></div>
                <div><dt>분석 소스</dt><dd>{uploadedMedia?.filename ?? '-'}</dd></div>
                <div><dt>테이블</dt><dd>{tableObjects.length}개</dd></div>
                <div><dt>바닥 꼭짓점</dt><dd>{floorPoints.length}개</dd></div>
                <div><dt>운영 구역</dt><dd>{zones.length}개</dd></div>
                {analysisJob && (
                  <div><dt>분석 job</dt><dd>{analysisJob.status}</dd></div>
                )}
              </dl>
              {validationErrors.length > 0 && (
                <ul className="onboarding-errors">
                  {validationErrors.map((error) => <li key={error}>{error}</li>)}
                </ul>
              )}
              {!savedVersions ? (
                <button
                  type="button"
                  className="onboarding-primary"
                  disabled={isSaving || validationErrors.length > 0 || !uploadedMedia}
                  onClick={saveOnboarding}
                >
                  {isSaving ? '저장·분석 등록 중…' : 'Scene·ROI 저장 및 분석 시작'}
                </button>
              ) : (
                <button
                  type="button"
                  className="onboarding-primary"
                  onClick={() => onComplete?.()}
                >
                  매장 대시보드로 이동
                </button>
              )}
            </div>
          )}

          {status.message && (
            <p className={`onboarding-status is-${status.kind}`} role="status">
              {status.message}
            </p>
          )}
        </aside>
      </div>

      <footer className="onboarding-navigation">
        <button
          type="button"
          className="onboarding-secondary"
          disabled={step === 0 || isSaving}
          onClick={() => {
            setStatus({ kind: 'idle', message: '' })
            setStep((current) => Math.max(0, current - 1))
          }}
        >
          이전
        </button>
        {step < STEPS.length - 1 && (
          <button
            type="button"
            className="onboarding-primary"
            disabled={!canGoNext()}
            onClick={() => {
              setStatus({ kind: 'idle', message: '' })
              setStep((current) => current + 1)
            }}
          >
            다음 단계
          </button>
        )}
      </footer>
    </section>
  )
}
