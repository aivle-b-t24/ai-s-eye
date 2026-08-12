import { useEffect, useMemo, useState } from 'react'

import { authenticatedFetch } from '../../api/authenticatedFetch'
import CameraSceneTwin from '../store/CameraSceneTwin'
import './OperationsSimulator.css'
import {
  consumeSse,
  frameIndexAtMinute,
  nextOrderAtMinute,
  nextPlaybackMinute,
  recentEventsAtMinute,
} from './operationsAgentStream'
import {
  getRecommendedSimulation,
  MAX_STAFF_COUNT,
  MIN_STAFF_COUNT,
  staffingOptionState,
  updateStaffingCondition,
} from './operationsStaffing'

const DEFAULT_CONDITIONS = {
  store_id: 'store-001',
  duration_minutes: 180,
  event_multiplier: 1.6,
  current_staff_count: 1,
  max_staff_count: 4,
  average_service_minutes: 4,
  patience_minutes: 8,
  seat_count: 16,
  dine_in_rate: 0.65,
  seed: 20260730,
}

const METRICS = [
  { key: 'completed_orders', label: '완료 주문', unit: '건', better: 'higher' },
  { key: 'abandoned_orders', label: '주문 포기', unit: '건', better: 'lower' },
  { key: 'average_wait_minutes', label: '평균 대기', unit: '분', better: 'lower' },
  { key: 'max_queue', label: '최대 대기열', unit: '명', better: 'lower' },
  { key: 'staff_utilization_percent', label: '직원 가동률', unit: '%', better: null },
]

const EVENT_LABELS = {
  customer_entered: '고객 입장',
  order_received: '주문 접수',
  queued: '대기열 진입',
  preparing: '제조 시작',
  ready: '준비 완료',
  completed: '주문 수령',
  abandoned: '주문 포기',
  seated: '좌석 이용',
  customer_exited: '고객 퇴장',
}

function metricValue(value, unit) {
  return `${Number(value ?? 0).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}${unit}`
}

function formatRange(range) {
  if (!range?.startAt || !range?.endAt) return '현재 선택 기간'
  const format = (value) => new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
  return `${format(range.startAt)} ~ ${format(range.endAt)}`
}

function scenarioTone(metric, one, two, side) {
  if (!metric.better || one === two) return 'neutral'
  const twoIsBetter = metric.better === 'higher' ? two > one : two < one
  if (side === 'two') return twoIsBetter ? 'good' : 'bad'
  return twoIsBetter ? 'bad' : 'good'
}

function OrderStatusStrip({ frame }) {
  const counts = frame?.order_status_counts ?? {}
  const received = Object.values(counts).reduce((sum, value) => sum + Number(value ?? 0), 0)
  return (
    <div className="simulation-order-status-grid">
      <span><small>접수</small><strong>{received}</strong></span>
      <span><small>대기</small><strong>{counts.waiting ?? 0}</strong></span>
      <span><small>제조 중</small><strong>{counts.preparing ?? 0}</strong></span>
      <span><small>준비 완료</small><strong>{counts.ready ?? 0}</strong></span>
      <span><small>완료</small><strong>{counts.completed ?? 0}</strong></span>
      <span><small>포기</small><strong>{counts.abandoned ?? 0}</strong></span>
    </div>
  )
}

function SimulationColumn({ label, result, storeId, minute }) {
  const frameIndex = frameIndexAtMinute(result?.frames, minute)
  const frame = result?.frames?.[frameIndex]
  const recentEvents = recentEventsAtMinute(result?.events, minute)
  const nextOrder = nextOrderAtMinute(result?.events, minute)
  const latestOrder = (result?.events ?? [])
    .filter((event) => event.event_type === 'order_received' && event.at_minute <= minute)
    .at(-1)
  const showNewOrder = latestOrder && minute - latestOrder.at_minute <= 1.2

  return (
    <article className="simulation-live-column">
      <header>
        <div>
          <span>{label}</span>
          <strong>{result?.scenario?.name}</strong>
        </div>
        <div className="simulation-live-demand">
          {showNewOrder && <b>신규 주문 +1 · {latestOrder.order_id}</b>}
          <small>
            {nextOrder
              ? `다음 주문까지 ${(nextOrder.at_minute - minute).toFixed(1)}분`
              : '주문 유입 종료'}
          </small>
        </div>
      </header>
      <OrderStatusStrip frame={frame} />
      <CameraSceneTwin
        storeId={storeId}
        simulationResult={result}
        simulationFrameIndex={frameIndex}
      />
      <div className="simulation-event-feed" aria-live="polite">
        <strong>주문·고객 이벤트</strong>
        {recentEvents.map((event) => (
          <div key={`${event.sequence}-${event.event_type}`} className={`is-${event.event_type}`}>
            <time>+{event.at_minute.toFixed(1)}분</time>
            <span>{EVENT_LABELS[event.event_type] ?? event.event_type}</span>
            <small>{event.order_id}</small>
          </div>
        ))}
      </div>
    </article>
  )
}

export default function OperationsSimulator({
  aiccBaseUrl,
  stores = [],
  activeRange,
}) {
  const storeOptions = useMemo(
    () => (stores.length > 0
      ? stores.map((store) => ({ id: store.id, name: store.name || store.id }))
      : [{ id: DEFAULT_CONDITIONS.store_id, name: DEFAULT_CONDITIONS.store_id }]),
    [stores],
  )
  const [conditions, setConditions] = useState(() => ({
    ...DEFAULT_CONDITIONS,
    store_id: storeOptions[0]?.id ?? DEFAULT_CONDITIONS.store_id,
  }))
  const [steps, setSteps] = useState([])
  const [status, setStatus] = useState({ kind: 'idle', message: '' })
  const [runResult, setRunResult] = useState(null)
  const [minute, setMinute] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)

  useEffect(() => {
    if (storeOptions.length === 0) return
    setConditions((current) => (
      storeOptions.some((store) => store.id === current.store_id)
        ? current
        : { ...current, store_id: storeOptions[0].id }
    ))
  }, [storeOptions])

  const comparison = runResult?.comparison ?? null
  const recommendedSimulation = getRecommendedSimulation(comparison)
  const duration = comparison?.event_one?.scenario?.duration_minutes
    ?? conditions.duration_minutes
  const demandSourceLabel = comparison?.demand_source === 'synthetic_order_simulator'
    ? '합성 주문 기반 What-if'
    : runResult?.demand_profile?.source === 'presentation_fallback'
      ? '발표 기본 수요 기반 What-if'
      : '합성 What-if 분석'

  useEffect(() => {
    if (!isPlaying || !comparison) return undefined
    const timer = window.setInterval(() => {
      setMinute((current) => {
        const next = nextPlaybackMinute(current, duration)
        if (next >= duration) {
          setIsPlaying(false)
          return duration
        }
        return next
      })
    }, 100)
    return () => window.clearInterval(timer)
  }, [comparison, duration, isPlaying])

  const updateCondition = (key, value) => {
    setConditions((current) => (
      key === 'current_staff_count' || key === 'max_staff_count'
        ? updateStaffingCondition(current, key, value)
        : { ...current, [key]: value }
    ))
    setRunResult(null)
    setSteps([])
    setMinute(0)
    setIsPlaying(false)
  }

  const updateStep = (item) => {
    if (item.event === 'run_started') {
      setSteps([item])
      return
    }
    if (item.event === 'tool_started') {
      setSteps((current) => [...current, item])
      return
    }
    if (item.event === 'tool_completed') {
      setSteps((current) => {
        const index = current.findLastIndex(
          (step) => step.tool_name === item.tool_name && step.status === 'running',
        )
        if (index < 0) return [...current, item]
        return current.map((step, stepIndex) => (stepIndex === index ? item : step))
      })
      return
    }
    if (item.event === 'fallback_started' || item.event === 'recommendation_ready') {
      setSteps((current) => [...current, item])
    }
  }

  const runAgent = async (event) => {
    event.preventDefault()
    setStatus({ kind: 'loading', message: 'Agent가 매장 데이터를 확인하고 있습니다.' })
    setSteps([])
    setRunResult(null)
    setMinute(0)
    setIsPlaying(false)
    const endAt = activeRange?.endAt ?? new Date().toISOString()
    const startAt = activeRange?.startAt
      ?? new Date(new Date(endAt).getTime() - 24 * 60 * 60 * 1000).toISOString()
    try {
      const response = await authenticatedFetch(`${aiccBaseUrl}/operations-agent/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...conditions,
          start_at: startAt,
          end_at: endAt,
        }),
      })
      const last = await consumeSse(response, (item) => {
        updateStep(item)
        if (item.event === 'run_failed') throw new Error(item.message || item.title)
        if (item.event === 'run_completed') {
          setRunResult(item.result)
          setMinute(0)
          setIsPlaying(true)
        }
      })
      if (last?.event !== 'run_completed') {
        throw new Error('운영 Agent가 완료 결과를 보내지 않았습니다.')
      }
      setStatus({ kind: 'success', message: '실제 도구 호출과 동일 수요 비교가 완료됐습니다.' })
    } catch (error) {
      setStatus({ kind: 'error', message: error.message || '운영 분석을 실행하지 못했습니다.' })
      setIsPlaying(false)
    }
  }

  const current = comparison?.event_one?.metrics
  const recommended = recommendedSimulation?.metrics
  const normal = comparison?.normal_one?.metrics

  return (
    <section id="hq-simulation" className="operations-simulator" aria-labelledby="operations-agent-title">
      <div className="supervisor-section-heading operations-simulator-heading">
        <div>
          <p className="supervisor-section-kicker">BOUNDED AI OPERATIONS AGENT</p>
          <h2 id="operations-agent-title">AI 운영 의사결정 Agent</h2>
        </div>
        <p>매장 데이터를 조회하고 동일 수요의 인력 운영안을 직접 시뮬레이션해 검토안을 제시합니다.</p>
      </div>

      <div className="operations-technology-strip" aria-label="사용 기술">
        <span>Gemini Tool Calling</span>
        <span>FastAPI Streaming</span>
        <span>SimPy Discrete Event Simulation</span>
        <span>동일 수요 비교</span>
      </div>

      <div className="simulation-source-notice" role="note">
        <strong>{demandSourceLabel}</strong>
        <span>선택 기간: {formatRange(activeRange)}</span>
        <em>실제 POS 실적 또는 자동 인력 지시가 아닙니다.</em>
      </div>

      <div className="operations-agent-launch">
        <form className="simulation-controls" onSubmit={runAgent}>
          <div className="operations-agent-primary-fields">
            <label>
              대상 매장
              <select
                value={conditions.store_id}
                onChange={(event) => updateCondition('store_id', event.target.value)}
              >
                {storeOptions.map((store) => (
                  <option key={store.id} value={store.id}>{store.name}</option>
                ))}
              </select>
            </label>
            <label>
              행사 수요 배수
              <input
                type="number"
                min="1"
                max="4"
                step="0.1"
                value={conditions.event_multiplier}
                onChange={(event) => updateCondition('event_multiplier', Number(event.target.value))}
              />
            </label>
            <label>
              현재 근무 인원
              <select
                value={conditions.current_staff_count}
                onChange={(event) => updateCondition('current_staff_count', Number(event.target.value))}
              >
                {Array.from(
                  { length: MAX_STAFF_COUNT - MIN_STAFF_COUNT + 1 },
                  (_, index) => index + MIN_STAFF_COUNT,
                ).map((count) => <option key={count} value={count}>{count}명</option>)}
              </select>
            </label>
            <label>
              투입 가능 최대 인원
              <select
                value={conditions.max_staff_count}
                onChange={(event) => updateCondition('max_staff_count', Number(event.target.value))}
              >
                {Array.from(
                  { length: MAX_STAFF_COUNT - MIN_STAFF_COUNT + 1 },
                  (_, index) => index + MIN_STAFF_COUNT,
                ).map((count) => <option key={count} value={count}>{count}명</option>)}
              </select>
            </label>
          </div>

          <details className="operations-agent-advanced">
            <summary>세부 운영 조건</summary>
            <div className="simulation-field-grid">
              <label>
                평균 제조시간
                <input
                  type="number"
                  min="0.5"
                  max="20"
                  step="0.5"
                  value={conditions.average_service_minutes}
                  onChange={(event) => updateCondition('average_service_minutes', Number(event.target.value))}
                />
                <small>분</small>
              </label>
              <label>
                대기 인내시간
                <input
                  type="number"
                  min="1"
                  max="60"
                  value={conditions.patience_minutes}
                  onChange={(event) => updateCondition('patience_minutes', Number(event.target.value))}
                />
                <small>분</small>
              </label>
              <label>
                좌석 수
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={conditions.seat_count}
                  onChange={(event) => updateCondition('seat_count', Number(event.target.value))}
                />
              </label>
              <label>
                매장 이용 비율
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="5"
                  value={Math.round(conditions.dine_in_rate * 100)}
                  onChange={(event) => updateCondition('dine_in_rate', Number(event.target.value) / 100)}
                />
                <small>%</small>
              </label>
              <label>
                재현 seed
                <input
                  type="number"
                  min="0"
                  value={conditions.seed}
                  onChange={(event) => updateCondition('seed', Number(event.target.value))}
                />
              </label>
            </div>
          </details>

          <button className="simulation-run-button" type="submit" disabled={status.kind === 'loading'}>
            {status.kind === 'loading' ? 'Agent 실행 중…' : 'AI 운영안 분석 실행'}
          </button>
          {status.message && <p className={`simulation-status is-${status.kind}`} role="status">{status.message}</p>}
        </form>

        <div className="operations-agent-trace" aria-live="polite">
          <header>
            <span>LIVE TOOL TRACE</span>
            <strong>Agent 실행 근거</strong>
          </header>
          {steps.length === 0 ? (
            <div className="operations-agent-trace-empty">
              실행하면 데이터 조회와 시뮬레이션 도구 호출이 여기에 표시됩니다.
            </div>
          ) : steps.map((step, index) => (
            <div className={`operations-agent-step is-${step.status}`} key={`${step.sequence}-${index}`}>
              <i>{step.status === 'completed' ? '✓' : step.status === 'warning' ? '!' : index + 1}</i>
              <span>
                <strong>{step.title}</strong>
                {step.tool_name && <small>{step.tool_name}</small>}
              </span>
            </div>
          ))}
          {runResult && (
            <div className={`operations-agent-source is-${runResult.source}`}>
              <strong>
                {runResult.source === 'gemini_tool_agent'
                  ? 'Gemini Tool Agent 완료'
                  : '규칙 기반 대체 분석 완료'}
              </strong>
              <small>{runResult.model ?? 'Gemini 미사용'}</small>
            </div>
          )}
        </div>
      </div>

      {comparison && recommendedSimulation && (
        <div className="operations-agent-result" aria-live="polite">
          <div className="operations-demand-proof">
            <div>
              <span>분석 수요 구간</span>
              <strong>{comparison.demand_window_label ?? runResult.demand_profile?.window_label}</strong>
            </div>
            <div>
              <span>직원 탐색 범위</span>
              <strong>
                현재 {comparison.current_staff_count}명 · 최대 {comparison.max_staff_count}명
              </strong>
            </div>
            <div>
              <span>동일 행사 수요 ID</span>
              <strong>{comparison.event_demand_trace_id}</strong>
            </div>
            <p>
              직원 1~{comparison.max_staff_count}명은 고객 도착 시각과 주문 조건이 같고
              인력 수만 다릅니다.
            </p>
          </div>

          <div className="simulation-synced-playback">
            <SimulationColumn
              label="현재 운영안"
              result={comparison.event_one}
              storeId={conditions.store_id}
              minute={minute}
            />
            <SimulationColumn
              label={comparison.capacity_sufficient ? '최소 적정 운영안' : '최대 투입 운영안'}
              result={recommendedSimulation}
              storeId={conditions.store_id}
              minute={minute}
            />
          </div>

          <div className="simulation-playback-controls simulation-playback-controls-wide">
            <button
              type="button"
              onClick={() => {
                if (minute >= duration) {
                  setMinute(0)
                  setIsPlaying(true)
                } else {
                  setIsPlaying((current) => !current)
                }
              }}
            >
              {isPlaying ? '일시정지' : minute >= duration ? '처음부터 재생' : '재생'}
            </button>
            <input
              type="range"
              min="0"
              max={duration}
              step="0.1"
              value={minute}
              onChange={(event) => {
                setMinute(Number(event.target.value))
                setIsPlaying(false)
              }}
              aria-label="두 시나리오 공통 재생 시점"
            />
            <strong>+{minute.toFixed(1)}분</strong>
          </div>

          <div className="simulation-baseline-card">
            <span>평상시 · 직원 {comparison.current_staff_count}명 기준</span>
            <strong>완료 {normal?.completed_orders ?? 0}건</strong>
            <small>평균 대기 {normal?.average_wait_minutes ?? 0}분 · 포기 {normal?.abandoned_orders ?? 0}건</small>
          </div>

          <div className="simulation-staffing-search-wrap">
            <div className="simulation-staffing-search-heading">
              <div>
                <span>STAFFING RANGE SEARCH</span>
                <strong>동일 수요 인원별 자동 탐색</strong>
              </div>
              <small>
                목표: 평균 대기 {comparison.staffing_targets.max_average_wait_minutes}분 이하 ·
                포기율 {comparison.staffing_targets.max_abandonment_rate_percent}% 이하 ·
                가동률 {comparison.staffing_targets.max_staff_utilization_percent}% 이하
              </small>
            </div>
            <div className="simulation-staffing-options">
              {comparison.staffing_options.map((option) => {
                const state = staffingOptionState(option, comparison)
                const isRecommendation = option.staff_count === comparison.recommended_staff_count
                return (
                  <article className={`is-${state}`} key={option.staff_count}>
                    <header>
                      <strong>{option.staff_count}명</strong>
                      <span>
                        {isRecommendation
                          ? comparison.capacity_sufficient ? '권장' : '최대·목표 미달'
                          : state === 'current' ? '현재' : option.meets_targets ? '충족' : '부족'}
                      </span>
                    </header>
                    <dl>
                      <div><dt>평균 대기</dt><dd>{option.metrics.average_wait_minutes}분</dd></div>
                      <div><dt>포기율</dt><dd>{option.abandonment_rate_percent}%</dd></div>
                      <div><dt>가동률</dt><dd>{option.metrics.staff_utilization_percent}%</dd></div>
                    </dl>
                  </article>
                )
              })}
            </div>
          </div>

          <div className="simulation-comparison-table-wrap">
            <table className="simulation-comparison-table">
              <caption>같은 행사 수요에서 직원 수에 따른 운영 지표 비교</caption>
              <thead>
                <tr>
                  <th>운영 지표</th>
                  <th>현재 {comparison.current_staff_count}명</th>
                  <th>
                    {comparison.capacity_sufficient ? '권장' : '최대'} {comparison.recommended_staff_count}명
                  </th>
                </tr>
              </thead>
              <tbody>
                {METRICS.map((metric) => (
                  <tr key={metric.key}>
                    <th>{metric.label}</th>
                    <td className={`is-${scenarioTone(metric, current[metric.key], recommended[metric.key], 'one')}`}>
                      {metricValue(current[metric.key], metric.unit)}
                    </td>
                    <td className={`is-${scenarioTone(metric, current[metric.key], recommended[metric.key], 'two')}`}>
                      {metricValue(recommended[metric.key], metric.unit)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="simulation-recommendation operations-agent-recommendation">
            <span>AGENT VERIFIED RECOMMENDATION</span>
            <h3>
              {runResult.recommendation.capacity_sufficient
                ? `행사 시간대 직원 ${runResult.recommendation.recommended_staff_count}명 검토`
                : `최대 ${runResult.recommendation.max_staff_count}명으로도 목표 미달`}
            </h3>
            <p>{runResult.recommendation.summary}</p>
            <small>슈퍼바이저 승인 필요 · 합성 What-if 결과 · 실제 운영 자동 변경 없음</small>
          </div>
        </div>
      )}
    </section>
  )
}
