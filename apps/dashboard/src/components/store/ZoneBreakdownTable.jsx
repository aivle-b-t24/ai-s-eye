import React from 'react'

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
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {paths[type]}
    </svg>
  )
}

export default function ZoneBreakdownTable({ zoneCounts }) {
  const zones = [
    {
      id: 'seating-1f',
      label: '1층 좌석',
      english: 'Seating · 1F',
      value: zoneCounts?.seating_1f ?? 0,
      type: 'seating',
      status: '좌석 이용 중',
    },
    {
      id: 'aisle-1f',
      label: '1층 통로',
      english: 'Aisle · 1F',
      value: zoneCounts?.aisle_1f ?? 0,
      type: 'aisle',
      status: '이동 감지',
    },
    {
      id: 'counter',
      label: '카운터',
      english: 'Counter',
      value: zoneCounts?.counter_1f ?? 0,
      type: 'counter',
      status: '주문 및 픽업',
    },
    {
      id: 'seating-2f',
      label: '2층 좌석',
      english: 'Seating · 2F',
      value: zoneCounts?.seating_2f ?? 0,
      type: 'seating',
      status: '좌석 이용 중',
    },
    {
      id: 'staff',
      label: '직원',
      english: 'Staff',
      value: zoneCounts?.staff_1f ?? 0,
      type: 'staff',
      status: '근무 인원',
    },
    {
      id: 'waiting',
      label: '외부 대기',
      english: 'Outdoor Waiting',
      value: zoneCounts?.waiting_out ?? 0,
      type: 'waiting',
      status: '웨이팅 존',
      danger: (zoneCounts?.waiting_out ?? 0) >= 5,
    },
  ]

  const totalZoneCount = zones.reduce(
    (sum, zone) => sum + zone.value,
    0
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
            <small>LIVE TRACKING</small>
            <strong>{totalZoneCount}명 감지</strong>
          </div>
        </div>
      </div>

      <div className="zone-overview-body">
        <div className="zone-map-preview" aria-hidden="true">
          <div className="zone-map-grid" />

          <span className="map-zone map-zone-seating-1">
            <i />
            1F 좌석
          </span>

          <span className="map-zone map-zone-counter">
            <i />
            카운터
          </span>

          <span className="map-zone map-zone-aisle">
            <i />
            통로
          </span>

          <span className="map-zone map-zone-seating-2">
            <i />
            2F 좌석
          </span>

          <span className="map-zone map-zone-waiting">
            <i />
            대기
          </span>

          <div className="map-entry">ENTRANCE</div>
        </div>

        <div className="zone-card-grid">
          {zones.map((zone) => (
            <article
              key={zone.id}
              className={`zone-status-card ${
                zone.danger ? 'zone-status-card-danger' : ''
              }`}
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
                <span>{zone.english}</span>
                <strong>{zone.label}</strong>
              </div>

              <div className="zone-status-bottom">
                <strong>
                  {zone.value}
                  <small>명</small>
                </strong>

                <span>{zone.status}</span>
              </div>
            </article>
          ))}
        </div>
      </div>
    </article>
  )
}