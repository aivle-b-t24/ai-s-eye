import { useCallback, useEffect, useState } from 'react'
import './App.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const STORE_ID = 'store-001'

async function getJson(path) {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) {
    throw new Error(`API 요청 실패 (${response.status})`)
  }
  return response.json()
}

function App() {
  const [dashboard, setDashboard] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const loadDashboard = useCallback(async (isInitial = false) => {
    if (isInitial) {
        setLoading(true)
    }

    try {
      const [state, eta, menuData, policyData] = await Promise.all([
        getJson(`/api/stores/${STORE_ID}/state`),
        getJson(`/api/stores/${STORE_ID}/eta`),
        getJson(`/api/stores/${STORE_ID}/menus`),
        getJson(`/api/stores/${STORE_ID}/policies`),
      ])

      setDashboard({
        state,
        eta,
        menus: menuData.menus,
        policies: policyData.policies,
      })
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadDashboard(true)

    const timer = setInterval(() => {
        loadDashboard(false)
    }, 2000)

    return () => clearInterval(timer)
}, [loadDashboard])
  
  return (
    <main className="page-shell">
      <header className="page-header">
        <h1>AI's Eye</h1>

        <div>
          
          <h1>매장-현황</h1>
          <p className="subtitle">
            현재는 store-001의 샘플 데이터를 표시합니다.
          </p>
        </div>

        <button type="button" onClick={() => loadDashboard(true)} disabled={loading}>
          {loading ? "불러오는 중..." : "새로고침"}
        </button>
      </header>

      {error && (
        <section className="notice error-notice">
          <strong>❌ API 연결 실패</strong>

          <span>
            {error}
            <br />
            API 연결에 실패했습니다.
            기존 데이터를 계속 표시합니다.
          </span>
        </section>
      )}

      {!error && loading && (
        <section className="notice">
          🔄 매장 정보를 불러오는 중입니다...
        </section>
      )}

      {dashboard && (
        <>
          <section className="summary-grid" aria-label="매장 요약">
            <article className="summary-card">
              <span>매장 인원</span>
              <strong>{dashboard.state.visible_person_count}명</strong>
            </article>

            <article className="summary-card">
              <span>대기 인원</span>
              <strong>{dashboard.state.queue_count_estimate}명</strong>
            </article>

            <article className="summary-card accent-card">
              <span>예상 대기시간</span>
              <strong>{dashboard.eta.estimated_wait_minutes}분</strong>
            </article>

            <article className="summary-card">
              <span>영상 상태</span>
              <strong>
                {dashboard.state.quality_status === "normal"
                  ? "정상"
                  : "확인 필요"}
              </strong>
            </article>
          </section>

          <section className="content-grid">
            <article className="panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Menu</p>
                  <h2>메뉴 및 품절 현황</h2>
                </div>

                <span>
                  {dashboard.menus.filter((menu) => !menu.available).length}개
                  품절
                </span>
              </div>

              <div className="menu-list">
                {dashboard.menus.length === 0 ? (
                  <div className="empty-message">
                    등록된 메뉴가 없습니다.
                  </div>
                ) : (
                  dashboard.menus.map((menu) => (
                    <div className="menu-row" key={menu.menu_id}>
                      <div>
                        <strong>{menu.name}</strong>
                        <span>{menu.price.toLocaleString("ko-KR")}원</span>
                      </div>

                      <span
                        className={
                          menu.available
                            ? "status available"
                            : "status sold-out"
                        }
                      >
                        {menu.available ? "판매 중" : "품절"}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </article>

            <article className="panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Policy</p>
                  <h2>매장 안내</h2>
                </div>
              </div>

              <div className="policy-list">
                {dashboard.policies.length === 0 ? (
                  <div className="empty-message">
                    등록된 매장 정책이 없습니다.
                  </div>
                ) : (
                  dashboard.policies.map((policy) => (
                    <div className="policy-item" key={policy.policy_id}>
                      <strong>{policy.title}</strong>
                      <p>{policy.content}</p>
                    </div>
                  ))
                )}
              </div>
            </article>
          </section>
        </>
      )}
    </main>
  )
}

export default App
