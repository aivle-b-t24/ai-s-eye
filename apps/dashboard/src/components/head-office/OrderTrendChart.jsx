import { useMemo } from 'react'

import { chartColorFor, storeDisplayName } from '../../api/storeDirectory'

const VIEWBOX = {
  width: 900,
  height: 300,
  left: 54,
  right: 22,
  top: 24,
  bottom: 48,
}

function formatBucketLabel(value, interval) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    ...(interval === '1h'
      ? { hour: '2-digit', hour12: false }
      : { month: 'numeric', day: 'numeric' }),
  }).format(date)
}

function makePath(points, maximum) {
  const chartWidth = VIEWBOX.width - VIEWBOX.left - VIEWBOX.right
  const chartHeight = VIEWBOX.height - VIEWBOX.top - VIEWBOX.bottom
  const denominator = Math.max(points.length - 1, 1)
  return points.map((point, index) => ({
    ...point,
    cx: VIEWBOX.left + (chartWidth * index) / denominator,
    cy: VIEWBOX.top + chartHeight - (chartHeight * point.order_count) / maximum,
  }))
}

function xTickIndexes(length) {
  if (length <= 1) return [0]
  const indexes = new Set([0, length - 1])
  const tickCount = Math.min(6, length)
  for (let index = 1; index < tickCount - 1; index += 1) {
    indexes.add(Math.round((index * (length - 1)) / (tickCount - 1)))
  }
  return [...indexes].sort((left, right) => left - right)
}

export default function OrderTrendChart({
  timelines,
  storeNames = {},
  interval,
  dataLabel,
  loading,
  error,
  onRetry,
}) {
  const series = useMemo(
    () => Object.entries(timelines).map(([storeId, timeline], index) => ({
      storeId,
      label: storeDisplayName(storeId, storeNames),
      color: chartColorFor(index),
      points: timeline?.points ?? [],
    })),
    [storeNames, timelines],
  )
  const referencePoints = series.find((item) => item.points.length)?.points ?? []
  const maximum = Math.max(
    1,
    ...series.flatMap((item) => item.points.map((point) => point.order_count)),
  )
  const renderedSeries = series.map((item) => ({
    ...item,
    renderedPoints: makePath(item.points, maximum),
  }))
  const chartHeight = VIEWBOX.height - VIEWBOX.top - VIEWBOX.bottom
  const chartWidth = VIEWBOX.width - VIEWBOX.left - VIEWBOX.right
  const ticks = [maximum, Math.round(maximum / 2), 0]

  return (
    <section className="supervisor-trend-section" aria-labelledby="order-trend-title">
      <div className="supervisor-section-heading">
        <div>
          <p className="supervisor-section-kicker">ORDER TREND</p>
          <h2 id="order-trend-title">매장별 주문 추이</h2>
        </div>
        <p>{interval === '1h' ? '시간별' : '일별'} {dataLabel} 접수 건수를 비교합니다.</p>
      </div>

      {loading ? (
        <div className="supervisor-trend-state" aria-live="polite">주문 추이를 불러오는 중입니다.</div>
      ) : error ? (
        <div className="supervisor-trend-state is-error" role="alert">
          <div>
            <strong>주문 추이만 불러오지 못했습니다.</strong>
            <p>{error}</p>
          </div>
          <button type="button" className="supervisor-secondary-button" onClick={onRetry}>
            그래프 다시 시도
          </button>
        </div>
      ) : referencePoints.length === 0 ? (
        <div className="supervisor-trend-state">선택 기간에 표시할 주문 추이가 없습니다.</div>
      ) : (
        <>
          <div className="supervisor-trend-legend" aria-label="매장별 주문 합계">
            {renderedSeries.map((item) => (
              <span key={item.storeId}>
                <i style={{ backgroundColor: item.color }} />
                {item.label}
                <strong>{item.points.reduce((sum, point) => sum + point.order_count, 0).toLocaleString('ko-KR')}건</strong>
              </span>
            ))}
          </div>
          <div className="supervisor-trend-chart-wrap">
            <svg
              className="supervisor-trend-chart"
              viewBox={`0 0 ${VIEWBOX.width} ${VIEWBOX.height}`}
              role="img"
              aria-label={`${interval === '1h' ? '시간별' : '일별'} 매장 주문 수 선 그래프`}
            >
              {ticks.map((tick, index) => {
                const y = VIEWBOX.top + (chartHeight * index) / (ticks.length - 1)
                return (
                  <g key={`${tick}-${index}`} className="supervisor-chart-grid">
                    <line x1={VIEWBOX.left} x2={VIEWBOX.left + chartWidth} y1={y} y2={y} />
                    <text x={VIEWBOX.left - 10} y={y + 5}>{tick}</text>
                  </g>
                )
              })}
              {xTickIndexes(referencePoints.length).map((index) => {
                const point = makePath(referencePoints, maximum)[index]
                return (
                  <text
                    className="supervisor-chart-x-label"
                    key={referencePoints[index].start_at}
                    x={point.cx}
                    y={VIEWBOX.height - 14}
                  >
                    {formatBucketLabel(referencePoints[index].start_at, interval)}
                  </text>
                )
              })}
              {renderedSeries.map((item) => (
                <g key={item.storeId}>
                  <polyline
                    className="supervisor-chart-line"
                    points={item.renderedPoints.map((point) => `${point.cx},${point.cy}`).join(' ')}
                    style={{ stroke: item.color }}
                  />
                  {item.renderedPoints.map((point) => (
                    <circle
                      className="supervisor-chart-point"
                      key={`${item.storeId}-${point.start_at}`}
                      cx={point.cx}
                      cy={point.cy}
                      r="4"
                      style={{ fill: item.color }}
                    >
                      <title>{`${item.label} · ${formatBucketLabel(point.start_at, interval)} · ${point.order_count}건`}</title>
                    </circle>
                  ))}
                </g>
              ))}
            </svg>
          </div>
        </>
      )}
    </section>
  )
}
