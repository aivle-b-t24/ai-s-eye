import React from 'react'

export default function KpiSummaryBar({ dashboard, soldOutCount }) {
  const isCameraNormal =
    dashboard?.state?.quality_status === 'normal'

  const totalPeople =
    dashboard?.state?.visible_person_count ?? 0

  const queueCount =
    dashboard?.state?.queue_count_estimate ?? 0

  const waitMinutes =
    dashboard?.eta?.estimated_wait_minutes ?? 0

  const totalMenuCount =
    dashboard?.menus?.length ?? 0

  const cards = [
    {
      id: 'people',
      label: '매장 총 인원',
      value: totalPeople,
      unit: '명',
      meta: '실시간',
      description: '실시간 객체 감지',
    },
    {
      id: 'queue',
      label: '대기 인원',
      value: queueCount,
      unit: '명',
      meta: '웨이팅 존',
      description: '외부 및 대기 구역 기준',
    },
    {
      id: 'wait',
      label: '예상 대기시간',
      value: waitMinutes,
      unit: '분',
      meta: 'AI ETA',
      description: '실시간 AI 예측값',
      accent: true,
    },
    {
      id: 'sold-out',
      label: '품절 메뉴',
      value: soldOutCount,
      unit: '개',
      meta: soldOutCount > 0 ? '품절 발생' : '정상',
      description: `전체 ${totalMenuCount}개 메뉴 중`,
      danger: soldOutCount > 0,
    },
    {
      id: 'camera',
      label: 'AI 카메라 상태',
      value: isCameraNormal ? '정상' : '점검 필요',
      unit: '',
      meta: isCameraNormal ? 'ONLINE' : 'CHECK',
      description: '스트림 및 비전 분석 상태',
      status: true,
      warning: !isCameraNormal,
    },
  ]

  return (
    <section
      className="kpi-summary-bar"
      aria-label="점주용 핵심 지표 요약"
    >
      {cards.map((card) => (
        <article
          key={card.id}
          className={[
            'kpi-card',
            'kpi-card-minimal',
            card.accent ? 'kpi-card-accent' : '',
            card.danger ? 'kpi-card-danger' : '',
          ]
            .filter(Boolean)
            .join(' ')}
        >
          <span className="kpi-label">
            {card.label}
          </span>

          <div className="kpi-value-row">
            <strong
              className={[
                'kpi-value',
                card.status ? 'kpi-status-value' : '',
                card.warning ? 'warning-text' : '',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              {card.status && (
                <span
                  className={`camera-status-dot ${
                    isCameraNormal ? 'normal' : 'warning'
                  }`}
                />
              )}

              {card.value}

              {card.unit && (
                <small>{card.unit}</small>
              )}
            </strong>

            <span
              className={[
                'kpi-meta',
                card.danger ? 'danger' : '',
                card.warning ? 'warning' : '',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              {card.meta}
            </span>
          </div>

          <div className="kpi-divider" />

          <span className="kpi-subtext">
            {card.description}
          </span>
        </article>
      ))}
    </section>
  )
}