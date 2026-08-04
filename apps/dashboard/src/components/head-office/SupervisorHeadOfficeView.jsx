import { useCallback, useEffect, useMemo, useState } from 'react'
import './SupervisorHeadOfficeView.css'
import { authenticatedFetch } from '../../api/authenticatedFetch'
import OperationsSimulator from './OperationsSimulator'
import AccountManagementPanel from './AccountManagementPanel'
import OrderTrendChart from './OrderTrendChart'
import {
  SUPERVISOR_STORE_IDS,
  orderDataLabel,
  orderDataMode,
  timelineIntervalForPeriod,
} from './supervisorPresentation'

const DEFAULT_STORE_NAMES = {
  'store-001': '동명점',
  'store-002': '수완점',
}

const PERIOD_OPTIONS = [
  { key: '24h', label: '최근 24시간', hours: 24 },
  { key: '7d', label: '최근 7일', hours: 24 * 7 },
  { key: '30d', label: '최근 30일', hours: 24 * 30 },
]

const EVIDENCE_LABELS = {
  average_visible_person_count: '평균 인원',
  peak_visible_person_count: '피크 인원',
  peak_visible_person_count_at: '피크 인원 시각',
  average_queue_count_estimate: '평균 대기 인원',
  peak_queue_count_estimate: '최대 대기 인원',
  peak_queue_count_estimate_at: '최대 대기 시각',
  total_order_count: '주문 수',
  quality_issue_count: '영상 이상 건수',
  peak_people: '피크 인원',
  peak_time_people: '피크 인원 시각',
  peak_wait: '최대 대기 인원',
  peak_time_wait: '최대 대기 시각',
  total_orders: '주문 수',
  peak_headcount: '피크 인원',
  peak_headcount_time: '피크 인원 시각',
  peak_wait_time: '최대 대기 시각',
  average_wait: '평균 대기 인원',
}

const INSIGHT_TYPE_LABELS = {
  congestion: '혼잡 특이사항',
  afternoon_demand: '오후 수요 특이사항',
  video_issue: '영상 품질 특이사항',
}

const SEVERITY_LABELS = {
  high: '높음',
  medium: '보통',
  low: '낮음',
  info: '참고',
}

function createPresetRange(hours, interval = '1h') {
  const end = new Date()
  const start = new Date(end.getTime() - hours * 60 * 60 * 1000)
  return {
    startAt: start.toISOString(),
    endAt: end.toISOString(),
    interval,
  }
}

function toKstInputValue(date) {
  const kstDate = new Date(date.getTime() + 9 * 60 * 60 * 1000)
  return kstDate.toISOString().slice(0, 16)
}

function kstInputToIso(value) {
  if (!value) return null
  const parsed = new Date(`${value}:00+09:00`)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString()
}

function formatDateTime(value) {
  if (!value) return '데이터 없음'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '데이터 없음'
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function formatFullDateTime(value) {
  if (!value) return '아직 생성되지 않음'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '아직 생성되지 않음'
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

function formatMetric(value, digits = 1) {
  if (value === null || value === undefined) return '데이터 없음'
  return Number(value).toLocaleString('ko-KR', {
    maximumFractionDigits: digits,
  })
}

function getStoreName(storeId, storeNames = DEFAULT_STORE_NAMES) {
  return storeNames[storeId] ?? storeId
}

async function getErrorMessage(response, fallback) {
  try {
    const body = await response.json()
    const detail = body?.detail
    if (typeof detail === 'string') return detail
    if (typeof detail?.message === 'string') return detail.message
  } catch {
    // 응답 본문이 JSON이 아니면 상태 코드 기반 안내를 사용한다.
  }
  return `${fallback} (${response.status})`
}

function getPeakStore(stores, field) {
  return stores
    .filter((store) => store.traffic_summary?.[field] !== null
      && store.traffic_summary?.[field] !== undefined)
    .reduce((highest, store) => {
      if (!highest) return store
      return store.traffic_summary[field] > highest.traffic_summary[field]
        ? store
        : highest
    }, null)
}

function buildKpis(stores, orderMode, storeNames) {
  const peakPeopleStore = getPeakStore(stores, 'peak_visible_person_count')
  const peakQueueStore = getPeakStore(stores, 'peak_queue_count_estimate')
  const totalOrders = stores.reduce(
    (sum, store) => sum + (store.order_summary?.total_order_count ?? 0),
    0,
  )

  return [
    {
      label: '운영 매장',
      value: `${stores.length}개`,
      detail: '기간 내 데이터가 수집된 매장',
    },
    {
      label: '최고 혼잡 매장',
      value: peakPeopleStore
        ? getStoreName(peakPeopleStore.store_id, storeNames)
        : '데이터 없음',
      detail: peakPeopleStore
        ? `피크 ${formatMetric(peakPeopleStore.traffic_summary.peak_visible_person_count, 0)}명`
        : '인원 데이터가 없습니다',
    },
    {
      label: '최대 대기 매장',
      value: peakQueueStore
        ? getStoreName(peakQueueStore.store_id, storeNames)
        : '데이터 없음',
      detail: peakQueueStore
        ? `최대 ${formatMetric(peakQueueStore.traffic_summary.peak_queue_count_estimate, 0)}명`
        : '대기 데이터가 없습니다',
    },
    {
      label: '전체 주문',
      value: `${totalOrders.toLocaleString('ko-KR')}건`,
      detail: `${orderDataLabel(orderMode)} · 선택 기간 내 고유 주문 수`,
    },
  ]
}

function getVideoStatus(videoSummary) {
  if (!videoSummary) {
    return { label: '데이터 없음', tone: 'neutral' }
  }
  if (
    videoSummary.latest_quality_status === 'normal'
    && videoSummary.quality_issue_count === 0
  ) {
    return { label: '정상', tone: 'success' }
  }
  if (videoSummary.quality_issue_count > 0) {
    return {
      label: `기간 중 이상 ${videoSummary.quality_issue_count}건`,
      tone: 'warning',
    }
  }
  return {
    label: `현재 ${videoSummary.latest_quality_status}`,
    tone: 'warning',
  }
}

function formatEvidenceValue(key, value) {
  if (key.endsWith('_at') && typeof value === 'string') {
    return formatDateTime(value)
  }
  if (Array.isArray(value)) return value.join(', ')
  if (value && typeof value === 'object') return JSON.stringify(value)
  if (typeof value === 'number') return value.toLocaleString('ko-KR')
  return String(value)
}

export default function SupervisorHeadOfficeView({ apiBaseUrl, aiccBaseUrl }) {
  const initialCustomEnd = useMemo(() => new Date(), [])
  const initialCustomStart = useMemo(
    () => new Date(initialCustomEnd.getTime() - 24 * 60 * 60 * 1000),
    [initialCustomEnd],
  )

  const [periodKey, setPeriodKey] = useState('24h')
  const [activeRange, setActiveRange] = useState(() => createPresetRange(24, '1h'))
  const [customStart, setCustomStart] = useState(
    () => toKstInputValue(initialCustomStart),
  )
  const [customEnd, setCustomEnd] = useState(
    () => toKstInputValue(initialCustomEnd),
  )
  const [periodError, setPeriodError] = useState('')

  const [summary, setSummary] = useState(null)
  const [summaryLoading, setSummaryLoading] = useState(true)
  const [summaryError, setSummaryError] = useState('')

  const [timelines, setTimelines] = useState({})
  const [timelinesLoading, setTimelinesLoading] = useState(true)
  const [timelinesError, setTimelinesError] = useState('')
  const [timelineReloadToken, setTimelineReloadToken] = useState(0)

  const [insights, setInsights] = useState(null)
  const [insightsLoading, setInsightsLoading] = useState(false)
  const [insightsError, setInsightsError] = useState('')
  const [storeNames, setStoreNames] = useState(DEFAULT_STORE_NAMES)
  const [storeIds, setStoreIds] = useState(SUPERVISOR_STORE_IDS)

  useEffect(() => {
    const controller = new AbortController()
    ;(async () => {
      try {
        const response = await authenticatedFetch(`${apiBaseUrl}/api/admin/stores`, {
          signal: controller.signal,
        })
        if (!response.ok) return
        const stores = await response.json()
        if (!Array.isArray(stores) || stores.length === 0) return
        setStoreIds(stores.map((store) => store.id))
        setStoreNames(
          Object.fromEntries(stores.map((store) => [store.id, store.name])),
        )
      } catch (error) {
        if (error.name !== 'AbortError') {
          // 매장 마스터 조회 실패 시 기본 매장 목록을 유지한다.
        }
      }
    })()
    return () => controller.abort()
  }, [apiBaseUrl])

  const loadSummary = useCallback(async (range, signal) => {
    setSummaryLoading(true)
    setSummaryError('')
    setSummary(null)

    const params = new URLSearchParams({
      start_at: range.startAt,
      end_at: range.endAt,
    })

    try {
      const response = await authenticatedFetch(
        `${apiBaseUrl}/api/stores/summary?${params.toString()}`,
        { signal },
      )
      if (!response.ok) {
        throw new Error(await getErrorMessage(response, '집계 데이터를 불러오지 못했습니다'))
      }
      setSummary(await response.json())
    } catch (error) {
      if (error.name !== 'AbortError') {
        setSummaryError(error.message || '집계 데이터를 불러오지 못했습니다')
      }
    } finally {
      if (!signal?.aborted) setSummaryLoading(false)
    }
  }, [apiBaseUrl])

  useEffect(() => {
    const controller = new AbortController()
    loadSummary(activeRange, controller.signal)
    return () => controller.abort()
  }, [activeRange, loadSummary])

  const loadTimelines = useCallback(async (range, signal) => {
    setTimelinesLoading(true)
    setTimelinesError('')
    setTimelines({})

    const results = await Promise.allSettled(
      storeIds.map(async (storeId) => {
        const params = new URLSearchParams({
          start_at: range.startAt,
          end_at: range.endAt,
          interval: range.interval,
        })
        const response = await authenticatedFetch(
          `${apiBaseUrl}/api/stores/${storeId}/timeline?${params.toString()}`,
          { signal },
        )
        if (!response.ok) {
          throw new Error(
            await getErrorMessage(
              response,
              `${getStoreName(storeId, storeNames)} 추이 조회 실패`,
            ),
          )
        }
        return [storeId, await response.json()]
      }),
    )
    if (signal.aborted) return

    const fulfilled = results
      .filter((result) => result.status === 'fulfilled')
      .map((result) => result.value)
    const rejected = results.filter((result) => result.status === 'rejected')
    setTimelines(Object.fromEntries(fulfilled))
    if (rejected.length > 0) {
      setTimelinesError(
        rejected
          .map((result) => result.reason?.message ?? '주문 추이 조회 실패')
          .join(' · '),
      )
    }
    setTimelinesLoading(false)
  }, [apiBaseUrl, storeIds, storeNames])

  useEffect(() => {
    const controller = new AbortController()
    loadTimelines(activeRange, controller.signal)
    return () => controller.abort()
  }, [activeRange, loadTimelines, timelineReloadToken])

  const stores = useMemo(
    () => [...(summary?.stores ?? [])].sort(
      (left, right) => left.store_id.localeCompare(right.store_id),
    ),
    [summary],
  )
  const orderMode = useMemo(() => orderDataMode(stores), [stores])
  const kpis = useMemo(
    () => buildKpis(stores, orderMode, storeNames),
    [orderMode, storeNames, stores],
  )
  const videoIssueStoreCount = useMemo(
    () => stores.filter(
      (store) => store.video_summary
        && (
          store.video_summary.latest_quality_status !== 'normal'
          || store.video_summary.quality_issue_count > 0
        ),
    ).length,
    [stores],
  )

  const selectPreset = (option) => {
    setPeriodKey(option.key)
    setPeriodError('')
    setInsights(null)
    setInsightsError('')
    setActiveRange(createPresetRange(
      option.hours,
      timelineIntervalForPeriod(option.key),
    ))
  }

  const showCustomPeriod = () => {
    setPeriodKey('custom')
    setPeriodError('')
  }

  const applyCustomPeriod = () => {
    const startAt = kstInputToIso(customStart)
    const endAt = kstInputToIso(customEnd)

    if (!startAt || !endAt) {
      setPeriodError('시작 시각과 종료 시각을 모두 입력해 주세요.')
      return
    }
    if (new Date(startAt) >= new Date(endAt)) {
      setPeriodError('시작 시각은 종료 시각보다 앞서야 합니다.')
      return
    }

    setPeriodError('')
    setInsights(null)
    setInsightsError('')
    setActiveRange({
      startAt,
      endAt,
      interval: timelineIntervalForPeriod('custom'),
    })
  }

  const generateInsights = async () => {
    if (!summary || insightsLoading) return

    setInsightsLoading(true)
    setInsightsError('')
    setInsights(null)

    try {
      const response = await authenticatedFetch(`${aiccBaseUrl}/insights`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_at: activeRange.startAt,
          end_at: activeRange.endAt,
        }),
      })
      if (!response.ok) {
        throw new Error(await getErrorMessage(response, 'AI 분석을 생성하지 못했습니다'))
      }
      setInsights(await response.json())
    } catch (error) {
      setInsightsError(error.message || 'AI 분석을 생성하지 못했습니다')
    } finally {
      setInsightsLoading(false)
    }
  }

  return (
    <section
      id="hq-overview"
      className="supervisor-dashboard"
      aria-labelledby="supervisor-title"
    >
      <header className="supervisor-page-header">
        <div>
          <p className="supervisor-overline">FRANCHISE OPERATIONS</p>
          <h1 id="supervisor-title">가맹점 운영 분석</h1>
          <p className="supervisor-lead">
            기간별 매장 데이터를 비교하고 운영상 특이사항을 확인합니다.
          </p>
        </div>
        <div className="supervisor-generated-at">
          <span>데이터 생성 시각</span>
          <strong>{formatFullDateTime(summary?.generated_at)}</strong>
          <small>한국시간 기준</small>
        </div>
      </header>

      <section className="supervisor-data-source-notice" aria-label="데모 데이터 출처 안내">
        <strong>데모 데이터 환경</strong>
        <span>Vision: CCTV 데모 재생 분석</span>
        <span>주문·메뉴: {orderDataLabel(orderMode)}</span>
        <em>실제 POS 실적이 아닙니다.</em>
      </section>

      <AccountManagementPanel apiBaseUrl={apiBaseUrl} />

      <section className="supervisor-filter-section" aria-labelledby="period-filter-title">
        <div className="supervisor-section-heading">
          <div>
            <p className="supervisor-section-kicker">조회 조건</p>
            <h2 id="period-filter-title">분석 기간</h2>
          </div>
          <p>
            기간을 변경하면 집계 데이터가 갱신됩니다. AI 분석은 필요할 때 별도로 실행합니다.
          </p>
        </div>

        <div className="supervisor-period-controls">
          <div className="supervisor-preset-group" aria-label="기간 선택">
            {PERIOD_OPTIONS.map((option) => (
              <button
                key={option.key}
                type="button"
                className={periodKey === option.key ? 'is-active' : ''}
                aria-pressed={periodKey === option.key}
                onClick={() => selectPreset(option)}
              >
                {option.label}
              </button>
            ))}
            <button
              type="button"
              className={periodKey === 'custom' ? 'is-active' : ''}
              aria-pressed={periodKey === 'custom'}
              onClick={showCustomPeriod}
            >
              직접 설정
            </button>
          </div>

          {periodKey === 'custom' && (
            <div className="supervisor-custom-period">
              <label>
                <span>시작</span>
                <input
                  type="datetime-local"
                  value={customStart}
                  onChange={(event) => setCustomStart(event.target.value)}
                />
              </label>
              <span className="supervisor-period-separator" aria-hidden="true">—</span>
              <label>
                <span>종료</span>
                <input
                  type="datetime-local"
                  value={customEnd}
                  onChange={(event) => setCustomEnd(event.target.value)}
                />
              </label>
              <button
                type="button"
                className="supervisor-primary-button"
                onClick={applyCustomPeriod}
              >
                기간 적용
              </button>
            </div>
          )}
        </div>

        {periodError && (
          <p className="supervisor-inline-error" role="alert">{periodError}</p>
        )}
      </section>

      {summaryError && (
        <section className="supervisor-error-panel" role="alert" aria-live="assertive">
          <div>
            <strong>집계 데이터를 불러오지 못했습니다.</strong>
            <p>{summaryError}</p>
          </div>
          <button
            type="button"
            className="supervisor-secondary-button"
            onClick={() => setActiveRange({ ...activeRange })}
          >
            다시 시도
          </button>
        </section>
      )}

      <section className="supervisor-kpi-section" aria-labelledby="hq-kpi-title">
        <div className="supervisor-section-heading supervisor-section-heading-compact">
          <div>
            <p className="supervisor-section-kicker">운영 요약</p>
            <h2 id="hq-kpi-title">본사 핵심 지표</h2>
          </div>
          <div
            className={`supervisor-video-status ${
              videoIssueStoreCount > 0 ? 'is-warning' : 'is-success'
            }`}
          >
            <span>영상 이상 매장</span>
            <strong>
              {summaryLoading ? '확인 중' : `${videoIssueStoreCount}개`}
            </strong>
          </div>
        </div>

        <div className="supervisor-kpi-grid" aria-busy={summaryLoading}>
          {summaryLoading
            ? Array.from({ length: 4 }, (_, index) => (
              <div className="supervisor-kpi-card is-loading" key={index}>
                <span />
                <strong />
                <small />
              </div>
            ))
            : kpis.map((kpi) => (
              <article className="supervisor-kpi-card" key={kpi.label}>
                <span>{kpi.label}</span>
                <strong>{kpi.value}</strong>
                <small>{kpi.detail}</small>
              </article>
            ))}
        </div>
      </section>

      <OrderTrendChart
        timelines={timelines}
        interval={activeRange.interval}
        dataLabel={orderDataLabel(orderMode)}
        loading={timelinesLoading}
        error={timelinesError}
        onRetry={() => setTimelineReloadToken((current) => current + 1)}
      />

      <section
        id="hq-stores"
        className="supervisor-comparison-section"
        aria-labelledby="store-comparison-title"
      >
        <div className="supervisor-section-heading">
          <div>
            <p className="supervisor-section-kicker">매장 비교</p>
            <h2 id="store-comparison-title">가맹점 운영 현황</h2>
          </div>
          <p>같은 기간의 매장별 인원, 대기, 주문, 영상 상태를 비교합니다.</p>
        </div>

        <div className="supervisor-table-wrap" aria-busy={summaryLoading}>
          {summaryLoading ? (
            <div className="supervisor-table-loading" aria-live="polite">
              매장 집계 데이터를 불러오는 중입니다.
            </div>
          ) : stores.length === 0 ? (
            <div className="supervisor-empty-state">
              <strong>선택 기간에 수집된 매장 데이터가 없습니다.</strong>
              <p>다른 기간을 선택하거나 데이터 수집 상태를 확인해 주세요.</p>
            </div>
          ) : (
            <table>
              <caption>선택 기간의 가맹점별 운영 지표 비교</caption>
              <thead>
                <tr>
                  <th scope="col">매장</th>
                  <th scope="col" className="is-numeric">평균 / 피크 인원</th>
                  <th scope="col" className="is-numeric">평균 / 최대 대기</th>
                  <th scope="col" className="is-numeric">주문</th>
                  <th scope="col">인기 메뉴</th>
                  <th scope="col">영상 상태</th>
                  <th scope="col">최신 데이터</th>
                </tr>
              </thead>
              <tbody>
                {stores.map((store) => {
                  const traffic = store.traffic_summary
                  const order = store.order_summary
                  const videoStatus = getVideoStatus(store.video_summary)
                  const topMenu = order?.top_menu_items?.[0]

                  return (
                    <tr key={store.store_id}>
                      <th scope="row">
                        <strong>{getStoreName(store.store_id, storeNames)}</strong>
                        <span>{store.store_id}</span>
                      </th>
                      <td className="is-numeric">
                        {traffic
                          ? `${formatMetric(traffic.average_visible_person_count)} / ${formatMetric(traffic.peak_visible_person_count, 0)}명`
                          : '데이터 없음'}
                      </td>
                      <td className="is-numeric">
                        {traffic
                          ? `${formatMetric(traffic.average_queue_count_estimate)} / ${formatMetric(traffic.peak_queue_count_estimate, 0)}명`
                          : '데이터 없음'}
                      </td>
                      <td className="is-numeric">
                        {order ? (
                          <span className="supervisor-order-value">
                            <strong>{formatMetric(order.total_order_count, 0)}건</strong>
                            <small>{orderDataLabel(orderDataMode([store]))}</small>
                          </span>
                        ) : '데이터 없음'}
                      </td>
                      <td>
                        {topMenu ? (
                          <span className="supervisor-order-value">
                            <strong>
                              {topMenu.name ?? topMenu.menu_id} {formatMetric(topMenu.quantity, 0)}개
                            </strong>
                            <small>{orderDataLabel(orderDataMode([store]))}</small>
                          </span>
                        ) : '데이터 없음'}
                      </td>
                      <td>
                        <span className={`supervisor-status-tag is-${videoStatus.tone}`}>
                          {videoStatus.label}
                        </span>
                      </td>
                      <td>{formatDateTime(traffic?.latest_captured_at)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <OperationsSimulator apiBaseUrl={apiBaseUrl} />

      <section
        id="hq-ai"
        className="supervisor-ai-section"
        aria-labelledby="ai-insights-title"
      >
        <div className="supervisor-ai-header">
          <div>
            <p className="supervisor-section-kicker">AI 운영 지원</p>
            <h2 id="ai-insights-title">매장 운영 인사이트</h2>
            <p>
              현재 집계 수치를 근거로 매장별 특이사항과 권장 조치를 생성합니다.
            </p>
            <span className="supervisor-ai-source-badge">데모 데이터 기반 분석</span>
          </div>
          <button
            type="button"
            className="supervisor-primary-button"
            onClick={generateInsights}
            disabled={!summary || summaryLoading || insightsLoading}
          >
            {insightsLoading ? 'AI 분석 중' : 'AI 운영 분석 생성'}
          </button>
        </div>

        {insightsError && (
          <div className="supervisor-ai-error" role="alert" aria-live="assertive">
            <strong>AI 분석을 생성하지 못했습니다.</strong>
            <p>{insightsError}</p>
          </div>
        )}

        {insightsLoading && (
          <div className="supervisor-ai-loading" aria-live="polite">
            <span className="supervisor-spinner" aria-hidden="true" />
            <div>
              <strong>기간별 운영 데이터를 분석하고 있습니다.</strong>
              <p>집계 데이터는 그대로 유지되며 AI 결과만 새로 생성됩니다.</p>
            </div>
          </div>
        )}

        {!insights && !insightsLoading && !insightsError && (
          <div className="supervisor-ai-empty">
            <strong>아직 생성된 AI 인사이트가 없습니다.</strong>
            <p>원할 때 분석 버튼을 눌러 현재 기간의 운영 제안을 확인하세요.</p>
          </div>
        )}

        {insights && (
          <div className="supervisor-insights-grid">
            {(insights.insights ?? []).map((insight) => (
              <article
                className="supervisor-insight-card"
                key={`${insight.store_id}-${insight.insight_type}`}
              >
                <header>
                  <div>
                    <span>{getStoreName(insight.store_id, storeNames)}</span>
                    <h3>
                      {INSIGHT_TYPE_LABELS[insight.insight_type] ?? '운영 특이사항'}
                    </h3>
                  </div>
                  {insight.severity && (
                    <span className={`supervisor-severity is-${insight.severity}`}>
                      {SEVERITY_LABELS[insight.severity] ?? insight.severity}
                    </span>
                  )}
                </header>

                <div className="supervisor-insight-block">
                  <h4>판단</h4>
                  <p>{insight.summary ?? '분석 결과가 없습니다.'}</p>
                </div>
                
                <div className="supervisor-insight-block">
                  <h4>추정 원인</h4>
                  <p>{insight.probable_cause}</p>
                </div>

                <div className="supervisor-insight-block">
                  <h4>근거</h4>
                  {Object.keys(insight.evidence ?? {}).length > 0 ? (
                    <dl>
                      {Object.entries(insight.evidence).map(([key, value]) => (
                        <div key={key}>
                          <dt>{EVIDENCE_LABELS[key] ?? key}</dt>
                          <dd>{formatEvidenceValue(key, value)}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : (
                    <p>표시할 근거 수치가 없습니다.</p>
                  )}
                </div>

                <div className="supervisor-insight-block is-recommendation">
                  <h4>권장 조치</h4>
                  <p>{insight.recommendation ?? '권장 조치가 없습니다.'}</p>
                </div>
              </article>
            ))}

            {insights.comparison && (
              <article className="supervisor-insight-card is-comparison">
                <header>
                  <div>
                    <span>매장 비교</span>
                    <h3>가맹점 비교 분석</h3>
                  </div>
                </header>
                <div className="supervisor-insight-block">
                  <h4>비교 결과</h4>
                  <p>{insights.comparison.summary ?? '비교 결과가 없습니다.'}</p>
                </div>
                <div className="supervisor-insight-block is-recommendation">
                  <h4>본사 권장 조치</h4>
                  <p>{insights.comparison.recommendation ?? '권장 조치가 없습니다.'}</p>
                </div>
              </article>
            )}
          </div>
        )}
      </section>
    </section>
  )
}
