import React from 'react'

export default function KpiSummaryBar({ dashboard, soldOutCount }) {
  const isCameraNormal =
    dashboard?.state?.quality_status === 'normal'

  const customerCount =
    dashboard?.state?.visible_person_count ?? 0

  const queueCount =
    dashboard?.state?.queue_count_estimate ?? 0

  const waitMinutes =
    dashboard?.eta?.estimated_wait_minutes ?? 0

  const cards = [
    {
      id: 'people',
      label: '현재 고객',
      value: customerCount,
      unit: '명',
    },
    {
      id: 'queue',
      label: '대기 인원',
      value: queueCount,
      unit: '명',
    },
    {
      id: 'wait',
      label: '예상 대기시간',
      value: waitMinutes,
      unit: '분',
    },
    {
      id: 'sold-out',
      label: '품절 메뉴',
      value: soldOutCount,
      unit: '개',
      danger: soldOutCount > 0,
    },
    {
      id: 'camera',
      label: 'AI 카메라 상태',
      value: isCameraNormal ? '정상' : '점검 필요',
      unit: '',
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
                card.danger ? 'kpi-value-danger' : '',
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

            {card.meta && (
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
            )}
          </div>
        </article>
      ))}
    </section>
  )
}
