import React, { useCallback, useState } from 'react'

import CameraSceneTwin from './CameraSceneTwin'

const ENABLE_CAMERA_TWIN_V2 = (
  String(import.meta.env.VITE_ENABLE_CAMERA_TWIN_V2).toLowerCase() === 'true'
)

const ZoneIcon = ({ type }) => {
  const paths = {
    seating: (
      <>
        <path d="M7 11h10a2 2 0 0 1 2 2v5H5v-5a2 2 0 0 1 2-2Z" />
        <path d="M8 11V7a4 4 0 0 1 8 0v4" />
        <path d="M7 18v2M17 18v2" />
      </>
    ),
    aisle: (
      <>
        <path d="M7 4v16M17 4v16" />
        <path d="m10 8 2-2 2 2M10 16l2 2 2-2" />
      </>
    ),
    counter: (
      <>
        <path d="M4 9h16v9H4z" />
        <path d="M7 9V6h10v3" />
        <path d="M8 18v2M16 18v2" />
      </>
    ),
    staff: (
      <>
        <circle cx="12" cy="7" r="3" />
        <path d="M6 20v-2a6 6 0 0 1 12 0v2" />
      </>
    ),
    waiting: (
      <>
        <circle cx="8" cy="8" r="3" />
        <circle cx="16" cy="8" r="3" />
        <path d="M3 20v-2a5 5 0 0 1 10 0v2" />
        <path d="M11 20v-2a5 5 0 0 1 10 0v2" />
      </>
    ),
    unassigned: (
      <>
        <circle cx="12" cy="12" r="8" />
        <path d="M12 8v5M12 16h.01" />
      </>
    ),
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {paths[type]}
    </svg>
  )
}

export default function ZoneBreakdownTable({ zoneCounts, storeId }) {
  const [twinSummary, setTwinSummary] = useState(null)
  const handleTwinSummaryChange = useCallback((summary) => {
    setTwinSummary(summary)
  }, [])
  const allZones = [
    {
      id: 'staff',
      keyMatch: ['staff', 'staff_1f'],
      label: '근무 직원',
      english: 'Staff Zone',
      type: 'staff',
      status: '근무 인원 감지',
      getValue: (zc) => zc?.staff ?? zc?.staff_1f,
    },
    {
      id: 'waiting',
      keyMatch: ['waiting', 'waiting_out'],
      label: '대기열 구역',
      english: 'Waiting Zone',
      type: 'waiting',
      status: '웨이팅 존',
      getValue: (zc) => zc?.waiting ?? zc?.waiting_out,
      getDanger: (val) => val >= 5,
    },
    {
      id: 'counter',
      keyMatch: ['counter', 'counter_1f'],
      label: '카운터 구역',
      english: 'Counter Zone',
      type: 'counter',
      status: '주문 및 픽업',
      getValue: (zc) => zc?.counter ?? zc?.counter_1f,
    },
    {
      id: 'seating',
      keyMatch: ['seating', 'seating_1f', 'seating_2f'],
      label: '매장 좌석',
      english: 'Seating Zone',
      type: 'seating',
      status: '좌석 이용 중',
      getValue: (zc) => zc?.seating ?? (zc?.seating_1f != null || zc?.seating_2f != null ? (zc?.seating_1f ?? 0) + (zc?.seating_2f ?? 0) : undefined),
    },
    {
      id: 'aisle',
      keyMatch: ['aisle', 'aisle_1f'],
      label: '이동 통로',
      english: 'Aisle Zone',
      type: 'aisle',
      status: '이동 감지',
      getValue: (zc) => zc?.aisle ?? zc?.aisle_1f,
    },
    {
      id: 'unassigned',
      keyMatch: ['unassigned'],
      label: '구역 외 고객',
      english: 'Outside Zone',
      type: 'unassigned',
      status: '승인 ROI 밖에서 감지',
      getValue: (zc) => zc?.unassigned,
    },
  ]

  const hasLiveTwinData = (
    ENABLE_CAMERA_TWIN_V2
    && (twinSummary?.status === 'ready' || twinSummary?.status === 'stale')
  )
  const effectiveZoneCounts = hasLiveTwinData
    ? twinSummary.zoneCounts
    : zoneCounts
  const hasApprovedZoneDefinition = (
    ENABLE_CAMERA_TWIN_V2
    && Array.isArray(twinSummary?.roiZoneTypes)
  )
  const approvedZoneTypes = hasApprovedZoneDefinition
    ? new Set(twinSummary.roiZoneTypes)
    : null
  const activeZoneKeys = effectiveZoneCounts
    ? Object.keys(effectiveZoneCounts)
    : []

  const filteredZones = allZones
    .map((z) => {
      const val = z.getValue(effectiveZoneCounts)
      const isPresent = approvedZoneTypes
        ? (
          approvedZoneTypes.has(z.id)
          || (z.id === 'unassigned' && (val ?? 0) > 0)
        )
        : val !== undefined || z.keyMatch.some((k) => activeZoneKeys.includes(k))
      return {
        id: z.id,
        label: z.label,
        english: z.english,
        type: z.type,
        status: z.status,
        value: val ?? 0,
        isPresent,
        danger: z.getDanger ? z.getDanger(val ?? 0) : false,
      }
    })
    .filter((z) => z.isPresent)

  const displayZones = filteredZones.length > 0
    ? filteredZones
    : (hasApprovedZoneDefinition ? [] : [
    {
      id: 'staff',
      label: '근무 직원',
      english: 'Staff Zone',
      type: 'staff',
      status: '근무 인원 감지',
      value: zoneCounts?.staff ?? 0,
      danger: false,
    },
    {
      id: 'waiting',
      label: '대기열 구역',
      english: 'Waiting Zone',
      type: 'waiting',
      status: '웨이팅 존',
      value: zoneCounts?.waiting ?? 0,
      danger: (zoneCounts?.waiting ?? 0) >= 5,
    },
  ])

  const fallbackTotalCount = displayZones.reduce(
    (sum, zone) => sum + zone.value,
    0
  )
  const totalZoneCount = (
    hasLiveTwinData
      ? twinSummary.count
      : fallbackTotalCount
  )
  const liveLabel = (
    ENABLE_CAMERA_TWIN_V2 && twinSummary?.status === 'stale'
      ? 'TRACKING DELAYED'
      : 'LIVE TRACKING'
  )

  return (
    <article className="panel zone-overview-panel">
      <div className="panel-heading zone-overview-heading">
        <div>
          <p className="eyebrow">Zone Overview</p>
          <h2>구역별 실시간 인원 현황</h2>
          <p className="zone-overview-description">
            AI 카메라가 구역별 인원과 이동 흐름을 실시간으로 분석합니다.
          </p>
        </div>

        <div className="zone-live-summary">
          <span className="zone-live-dot" />
          <div>
            <small>{liveLabel}</small>
            <strong>{totalZoneCount}명 감지</strong>
          </div>
        </div>
      </div>

      <div className="zone-overview-body">
        {ENABLE_CAMERA_TWIN_V2 ? (
          <CameraSceneTwin
            storeId={storeId}
            onSummaryChange={handleTwinSummaryChange}
          />
        ) : (
          <div className="zone-map-preview" aria-hidden="true">
            <div className="zone-map-grid" />

            {displayZones.some((z) => z.id === 'staff') && (
              <span className="map-zone map-zone-counter">
                <i />
                직원 구역
              </span>
            )}

            {displayZones.some((z) => z.id === 'waiting') && (
              <span className="map-zone map-zone-waiting">
                <i />
                대기 구역
              </span>
            )}

            {displayZones.some((z) => z.id === 'counter') && (
              <span className="map-zone map-zone-counter">
                <i />
                카운터
              </span>
            )}

            {displayZones.some((z) => z.id === 'seating') && (
              <span className="map-zone map-zone-seating-1">
                <i />
                좌석
              </span>
            )}

            {displayZones.some((z) => z.id === 'aisle') && (
              <span className="map-zone map-zone-aisle">
                <i />
                통로
              </span>
            )}

            <div className="map-entry">ENTRANCE</div>
          </div>
        )}

        <div className="zone-card-grid" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {displayZones.map((zone) => (
            <article
              key={zone.id}
              className={`zone-status-card ${
                zone.danger ? 'zone-status-card-danger' : ''
              }`}
              style={{ width: '100%', padding: '20px 24px' }}
            >
              <div className="zone-status-top">
                <span className="zone-status-icon">
                  <ZoneIcon type={zone.type} />
                </span>

                <span
                  className={`zone-status-indicator ${
                    zone.danger ? 'danger' : 'normal'
                  }`}
                >
                  {zone.danger ? '혼잡' : '정상'}
                </span>
              </div>

              <div className="zone-status-copy">
                <span style={{ fontSize: '0.9rem', fontWeight: '700', color: '#0f172a', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {zone.english}
                </span>

                <h4 style={{ margin: '6px 0 0 0', fontSize: '1.3rem', fontWeight: '700', color: '#091512', display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '1.3rem', fontWeight: '700', color: '#091512' }}>
                    {zone.label}
                  </span>
                  <span style={{ fontSize: '1.85rem', fontWeight: '800', color: '#0284c7', lineHeight: 1 }}>
                    {zone.value}
                    <small style={{ fontSize: '1rem', marginLeft: '4px', color: '#0284c7', fontWeight: '700' }}>명</small>
                  </span>
                </h4>
              </div>

              <div className="zone-status-bottom" style={{ marginTop: '10px' }}>
                <p style={{ margin: 0, fontSize: '0.95rem', fontWeight: '600', color: '#1e293b' }}>
                  {zone.status}
                </p>
              </div>

            </article>
          ))}
        </div>
      </div>
    </article>
  )
}
