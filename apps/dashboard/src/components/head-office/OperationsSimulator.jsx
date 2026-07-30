import { useEffect, useMemo, useState } from 'react'

import CameraSceneTwin from '../store/CameraSceneTwin'
import './OperationsSimulator.css'

const DEFAULT_CONDITIONS = {
  store_id: 'store-001',
  duration_minutes: 180,
  arrivals_per_hour: 24,
  event_multiplier: 1,
  average_service_minutes: 4,
  patience_minutes: 8,
  seat_count: 16,
  dine_in_rate: 0.65,
  seed: 20260730,
}

const METRICS = [
  { key: 'completed_orders', label: '완료 주문', unit: '건', higherIsBetter: true },
  { key: 'abandoned_orders', label: '주문 포기', unit: '건', higherIsBetter: false },
  { key: 'average_wait_minutes', label: '평균 대기', unit: '분', higherIsBetter: false },
  { key: 'max_queue', label: '최대 대기열', unit: '명', higherIsBetter: false },
  { key: 'staff_utilization_percent', label: '직원 가동률', unit: '%', higherIsBetter: null },
]

function metricValue(value, unit) {
  return `${Number(value ?? 0).toLocaleString('ko-KR', { maximumFractionDigits: 1 })}${unit}`
}

function comparisonTone(metric, baseline, alternative) {
  const difference = alternative - baseline
  if (difference === 0 || metric.higherIsBetter === null) return 'neutral'
  const improved = metric.higherIsBetter ? difference > 0 : difference < 0
  return improved ? 'good' : 'bad'
}

function recommendation(baseline, alternative) {
  if (!baseline || !alternative) return ''
  const base = baseline.metrics
  const alt = alternative.metrics
  if (
    alt.completed_orders > base.completed_orders
    && alt.average_wait_minutes < base.average_wait_minutes
  ) {
    return `대안 조건은 완료 주문이 ${alt.completed_orders - base.completed_orders}건 늘고 평균 대기가 ${(base.average_wait_minutes - alt.average_wait_minutes).toFixed(1)}분 줄었습니다. 피크 시간대에만 대안 인력을 적용하는 방안을 우선 검토하세요.`
  }
  if (alt.staff_utilization_percent < 45 && alt.abandoned_orders === 0) {
    return '대안 조건은 여유 인력이 큰 편입니다. 상시 증원보다는 행사·피크 시간 한정 배치가 적합합니다.'
  }
  return '두 조건의 차이가 크지 않습니다. 방문객 수나 제조시간 조건을 높여 임계점을 추가 확인하세요.'
}

export default function OperationsSimulator({ apiBaseUrl }) {
  const [conditions, setConditions] = useState(DEFAULT_CONDITIONS)
  const [staffCounts, setStaffCounts] = useState({ baseline: 1, alternative: 2 })
  const [results, setResults] = useState(null)
  const [status, setStatus] = useState({ kind: 'idle', message: '' })
  const [selectedScenario, setSelectedScenario] = useState('baseline')
  const [frameIndex, setFrameIndex] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)

  const activeResult = results?.[selectedScenario] ?? null
  const activeFrame = activeResult?.frames?.[frameIndex] ?? null
  const resultRecommendation = useMemo(
    () => recommendation(results?.baseline, results?.alternative),
    [results],
  )

  useEffect(() => {
    setFrameIndex(0)
    setIsPlaying(false)
  }, [activeResult?.run_id])

  useEffect(() => {
    if (!isPlaying || !activeResult?.frames?.length) return undefined
    const timer = window.setInterval(() => {
      setFrameIndex((current) => {
        if (current >= activeResult.frames.length - 1) {
          setIsPlaying(false)
          return current
        }
        return current + 1
      })
    }, 650)
    return () => window.clearInterval(timer)
  }, [activeResult, isPlaying])

  const updateCondition = (key, value) => {
    setConditions((current) => ({ ...current, [key]: value }))
    setResults(null)
    setIsPlaying(false)
  }

  const runComparison = async (event) => {
    event.preventDefault()
    setStatus({ kind: 'loading', message: '두 운영 조건을 계산하고 있습니다.' })
    setResults(null)
    setIsPlaying(false)
    try {
      const buildScenario = (name, staffCount) => ({
        ...conditions,
        name,
        staff_count: staffCount,
        service_variability: 0.25,
      })
      const requests = [
        buildScenario('기준 조건', staffCounts.baseline),
        buildScenario('대안 조건', staffCounts.alternative),
      ].map(async (payload) => {
        const response = await fetch(`${apiBaseUrl}/api/simulations/operations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
        if (!response.ok) throw new Error(`시뮬레이션 요청 실패 (${response.status})`)
        return response.json()
      })
      const [baseline, alternative] = await Promise.all(requests)
      setResults({ baseline, alternative })
      setSelectedScenario('baseline')
      setFrameIndex(0)
      setStatus({ kind: 'success', message: '같은 방문 조건으로 두 시나리오를 비교했습니다.' })
    } catch (error) {
      setStatus({ kind: 'error', message: error.message || '시뮬레이션을 실행하지 못했습니다.' })
    }
  }

  return (
    <section
      id="hq-simulation"
      className="operations-simulator"
      aria-labelledby="operations-simulator-title"
    >
      <div className="supervisor-section-heading operations-simulator-heading">
        <div>
          <p className="supervisor-section-kicker">WHAT-IF SIMULATION</p>
          <h2 id="operations-simulator-title">운영 조건 비교</h2>
        </div>
        <p>
          동일한 가상 방문 흐름에서 직원 수와 매장 조건을 바꿔 결과를 비교합니다.
          실제 과거 실적에는 반영되지 않습니다.
        </p>
      </div>

      <div className="simulation-source-notice" role="note">
        <strong>합성 시뮬레이션</strong>
        <span>SimPy 이산사건 모델 · DB 저장 없음 · 실제 데이터 아님</span>
      </div>

      <div className="operations-simulator-layout">
        <form className="simulation-controls" onSubmit={runComparison}>
          <fieldset>
            <legend>공통 운영 조건</legend>
            <div className="simulation-field-grid">
              <label>
                대상 매장
                <select
                  value={conditions.store_id}
                  onChange={(event) => updateCondition('store_id', event.target.value)}
                >
                  <option value="store-001">강남점</option>
                  <option value="store-002">홍대점</option>
                </select>
              </label>
              <label>
                운영 시간
                <select
                  value={conditions.duration_minutes}
                  onChange={(event) => updateCondition('duration_minutes', Number(event.target.value))}
                >
                  <option value={60}>1시간</option>
                  <option value={180}>3시간</option>
                  <option value={360}>6시간</option>
                </select>
              </label>
              <label>
                시간당 방문객
                <input
                  type="number"
                  min="1"
                  max="180"
                  value={conditions.arrivals_per_hour}
                  onChange={(event) => updateCondition('arrivals_per_hour', Number(event.target.value))}
                />
              </label>
              <label>
                상황
                <select
                  value={conditions.event_multiplier}
                  onChange={(event) => updateCondition('event_multiplier', Number(event.target.value))}
                >
                  <option value={1}>평상시</option>
                  <option value={1.6}>주변 행사 ×1.6</option>
                  <option value={2}>대형 행사 ×2.0</option>
                </select>
              </label>
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
            </div>
          </fieldset>

          <fieldset>
            <legend>비교할 직원 수</legend>
            <div className="simulation-staff-comparison">
              <label>
                <span>기준 조건 A</span>
                <select
                  value={staffCounts.baseline}
                  onChange={(event) => {
                    setStaffCounts((current) => ({ ...current, baseline: Number(event.target.value) }))
                    setResults(null)
                  }}
                >
                  {[1, 2, 3, 4].map((count) => <option key={count} value={count}>직원 {count}명</option>)}
                </select>
              </label>
              <span aria-hidden="true">VS</span>
              <label>
                <span>대안 조건 B</span>
                <select
                  value={staffCounts.alternative}
                  onChange={(event) => {
                    setStaffCounts((current) => ({ ...current, alternative: Number(event.target.value) }))
                    setResults(null)
                  }}
                >
                  {[1, 2, 3, 4].map((count) => <option key={count} value={count}>직원 {count}명</option>)}
                </select>
              </label>
            </div>
          </fieldset>

          <button className="simulation-run-button" type="submit" disabled={status.kind === 'loading'}>
            {status.kind === 'loading' ? '계산 중…' : '두 조건 비교 실행'}
          </button>
          {status.message && (
            <p className={`simulation-status is-${status.kind}`} role="status">{status.message}</p>
          )}
        </form>

        <div className="simulation-playback-panel">
          <header>
            <div>
              <span>디지털 트윈 재생</span>
              <strong>{activeResult ? activeResult.scenario.name : '실행 대기'}</strong>
            </div>
            {results && (
              <div className="simulation-scenario-tabs">
                <button
                  type="button"
                  className={selectedScenario === 'baseline' ? 'active' : ''}
                  onClick={() => setSelectedScenario('baseline')}
                >
                  조건 A
                </button>
                <button
                  type="button"
                  className={selectedScenario === 'alternative' ? 'active' : ''}
                  onClick={() => setSelectedScenario('alternative')}
                >
                  조건 B
                </button>
              </div>
            )}
          </header>

          {activeResult ? (
            <>
              <CameraSceneTwin
                storeId={conditions.store_id}
                simulationResult={activeResult}
                simulationFrameIndex={frameIndex}
              />
              <div className="simulation-playback-controls">
                <button type="button" onClick={() => setIsPlaying((current) => !current)}>
                  {isPlaying ? '일시정지' : '재생'}
                </button>
                <input
                  type="range"
                  min="0"
                  max={Math.max(activeResult.frames.length - 1, 0)}
                  value={frameIndex}
                  onChange={(event) => {
                    setFrameIndex(Number(event.target.value))
                    setIsPlaying(false)
                  }}
                  aria-label="시뮬레이션 재생 시점"
                />
                <strong>+{activeFrame?.at_minute ?? 0}분</strong>
              </div>
            </>
          ) : (
            <div className="simulation-playback-empty">
              <strong>조건을 설정하고 비교를 실행하세요.</strong>
              <p>방문, 대기, 주문, 착석, 퇴장 흐름이 이 화면에 재생됩니다.</p>
            </div>
          )}
        </div>
      </div>

      {results && (
        <div className="simulation-results" aria-live="polite">
          <div className="simulation-result-grid">
            {METRICS.map((metric) => {
              const base = results.baseline.metrics[metric.key]
              const alt = results.alternative.metrics[metric.key]
              const tone = comparisonTone(metric, base, alt)
              return (
                <article key={metric.key} className={`simulation-result-card is-${tone}`}>
                  <span>{metric.label}</span>
                  <div>
                    <p><small>조건 A</small><strong>{metricValue(base, metric.unit)}</strong></p>
                    <i aria-hidden="true">→</i>
                    <p><small>조건 B</small><strong>{metricValue(alt, metric.unit)}</strong></p>
                  </div>
                </article>
              )
            })}
          </div>
          <div className="simulation-recommendation">
            <span>슈퍼바이저 검토안</span>
            <p>{resultRecommendation}</p>
            <small>결정이 아니라 검토용 제안입니다. 실제 매장 조건과 함께 판단해야 합니다.</small>
          </div>
        </div>
      )}
    </section>
  )
}
