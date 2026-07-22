import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'

import GnbHeader from './components/GnbHeader'
import RoleBanner from './components/RoleBanner'
import KpiSummaryBar from './components/KpiSummaryBar'
import ZoneBreakdownTable from './components/ZoneBreakdownTable'
import VisionMonitorPanel from './components/VisionMonitorPanel'
import MenuListPanel from './components/MenuListPanel'
import PolicyListPanel from './components/PolicyListPanel'
import EmptyStorePanel from './components/EmptyStorePanel'
import SupervisorHeadOfficeView from './components/SupervisorHeadOfficeView'
import SettingsView from './components/SettingsView'

/* ==========================================================================
   1. [REAL API ENVIRONMENT & CONFIGURATION]
   ========================================================================== */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

/* ==========================================================================
   2. [MOCK DATA FOR DEMO & OFFLINE FALLBACK]
   ========================================================================== */
const MOCK_STORE_DATA = {
  'store-001': {
    state: {
      visible_person_count: 24,
      queue_count_estimate: 4,
      quality_status: 'normal',
      zone_counts: {
        seating_1f: 10,
        aisle_1f: 4,
        counter_1f: 3,
        staff_1f: 2,
        seating_2f: 5,
        aisle_2f: 2,
        waiting_out: 4
      }
    },
    eta: { estimated_wait_minutes: 12 },
    menus: [
      { menu_id: 'm1', name: '아메리카노', price: 4500, available: true },
      { menu_id: 'm2', name: '카페 라떼', price: 5000, available: true },
      { menu_id: 'm3', name: '바닐라 빈 라떼', price: 5500, available: false },
      { menu_id: 'm4', name: '딸기 생크림 케이크', price: 6800, available: true }
    ],
    policies: [
      { policy_id: 'p1', title: '📢 착석 안내', content: '주문 후 번호표 순서대로 1층 또는 2층 안내에 따라 이동해 주세요.' },
      { policy_id: 'p2', title: '☕ 셀프 바 이용', content: '물과 냅킨은 각 층 중앙 셀프바에서 이용 가능합니다.' }
    ]
  },
  'store-002': {
    state: null,
    eta: null,
    menus: [],
    policies: []
  }
}

/* ==========================================================================
   3. [REAL API FETCHERS]
   ========================================================================== */
async function fetchStoreState(storeId) {
  const response = await fetch(`${API_BASE_URL}/api/stores/${storeId}/state`)
  if (!response.ok) {
    throw new Error(`API 요청 실패 (${response.status})`)
  }
  return response.json()
}

async function fetchStoreEta(storeId) {
  const response = await fetch(`${API_BASE_URL}/api/stores/${storeId}/eta`)
  if (!response.ok) return null
  return response.json()
}

async function fetchStoreMenus(storeId) {
  const response = await fetch(`${API_BASE_URL}/api/stores/${storeId}/menus`)
  if (!response.ok) return { menus: [] }
  return response.json()
}

async function fetchStorePolicies(storeId) {
  const response = await fetch(`${API_BASE_URL}/api/stores/${storeId}/policies`)
  if (!response.ok) return { policies: [] }
  return response.json()
}

function App() {
  const [page, setPage] = useState("store-001")
  const [dashboard, setDashboard] = useState(MOCK_STORE_DATA['store-001'])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [isUsingMock, setIsUsingMock] = useState(false)

  const lastStateJsonRef = useRef('')
  const lastErrorRef = useRef('')
  const isApiOfflineRef = useRef(false)

  const loadStateOnly = useCallback(async (storeId, isInitial = false) => {
    if (isApiOfflineRef.current && !isInitial) {
      return
    }

    if (isInitial) setLoading(true)
    try {
      const stateData = await fetchStoreState(storeId)
      const currentStateJson = JSON.stringify(stateData)
      
      isApiOfflineRef.current = false

      if (lastStateJsonRef.current === currentStateJson) {
        if (lastErrorRef.current !== '') {
          setError('')
          lastErrorRef.current = ''
        }
        setIsUsingMock(false)
        return
      }

      lastStateJsonRef.current = currentStateJson
      lastErrorRef.current = ''

      setDashboard((prev) => ({
        ...prev,
        state: stateData,
      }))
      setError('')
      setIsUsingMock(false)
    } catch (err) {
      isApiOfflineRef.current = true

      if (lastErrorRef.current !== err.message) {
        lastErrorRef.current = err.message
        setError(err.message)
      }
      
      setIsUsingMock(true)
      if (MOCK_STORE_DATA[storeId]) {
        setDashboard((prev) => ({
          ...prev,
          state: MOCK_STORE_DATA[storeId].state ?? prev?.state,
          eta: MOCK_STORE_DATA[storeId].eta ?? prev?.eta,
          menus: MOCK_STORE_DATA[storeId].menus ?? prev?.menus,
          policies: MOCK_STORE_DATA[storeId].policies ?? prev?.policies,
        }))
      }
    } finally {
      setLoading(false)
    }
  }, [])

  const loadStaticData = useCallback(async (storeId) => {
    try {
      const [menuData, policyData, etaData] = await Promise.all([
        fetchStoreMenus(storeId),
        fetchStorePolicies(storeId),
        fetchStoreEta(storeId),
      ])
      setDashboard((prev) => ({
        ...prev,
        menus: menuData?.menus ?? MOCK_STORE_DATA[storeId]?.menus ?? [],
        policies: policyData?.policies ?? MOCK_STORE_DATA[storeId]?.policies ?? [],
        eta: etaData ?? MOCK_STORE_DATA[storeId]?.eta ?? null,
      }))
    } catch {
      // Ignore static fail in mock mode
    }
  }, [])

  useEffect(() => {
    let timerId = null

    if (page === 'store-001' || page === 'store-002') {
      const targetStore = page
      
      loadStaticData(targetStore)
      loadStateOnly(targetStore, true)

      timerId = setInterval(() => {
        loadStateOnly(targetStore, false)
      }, 2000)
    } else {
      timerId = null
    }

    return () => {
      if (timerId) clearInterval(timerId)
    }
  }, [page, loadStateOnly, loadStaticData])

  const soldOutCount = dashboard?.menus?.filter((menu) => !menu.available).length ?? 0;

  return (
    <main className="page-shell">
      {/* 1. GNB Component */}
      <GnbHeader 
        page={page} 
        setPage={setPage} 
        loadStateOnly={loadStateOnly} 
        loading={loading} 
      />

      {/* 2. Role Banner Component */}
      <RoleBanner 
        page={page} 
        apiBaseUrl={API_BASE_URL} 
        isUsingMock={isUsingMock} 
        error={error} 
        loading={loading} 
      />

      {/* 3. [Store Manager View - Store 1] */}
      {page === "store-001" && (
        <>
          {dashboard?.state?.quality_status !== "normal" && (
            <section className="alert-banner warning-alert">
              ⚠️ <strong>점주 알림:</strong> AI 카메라 스트림 화질 점검이 필요합니다.
            </section>
          )}

          {(dashboard?.state?.queue_count_estimate ?? 0) >= 20 && (
            <section className="alert-banner queue-alert">
              🚨 <strong>대기 폭주 알림:</strong> 현재 외부 대기 인원이 {dashboard?.state?.queue_count_estimate}명으로 증가했습니다. 카운터 대응을 권장합니다.
            </section>
          )}

          <KpiSummaryBar dashboard={dashboard} soldOutCount={soldOutCount} />

          <section className="dashboard-main-grid">
            <div className="main-left-content">
              <ZoneBreakdownTable zoneCounts={dashboard?.state?.zone_counts} />
              <VisionMonitorPanel />
            </div>

            <div className="main-right-content">
              <MenuListPanel menus={dashboard?.menus} soldOutCount={soldOutCount} />
              <PolicyListPanel policies={dashboard?.policies} />
            </div>
          </section>
        </>
      )}

      {/* 4. [Store Manager View - Store 2] */}
      {page === "store-002" && <EmptyStorePanel storeId="store-002" />}

      {/* 5. [Supervisor View - Head Office] */}
      {page === "head-office" && (
        <SupervisorHeadOfficeView dashboard={dashboard} mockData={MOCK_STORE_DATA} />
      )}

      {/* 6. [Settings View] */}
      {page === "setting" && (
        <SettingsView apiBaseUrl={API_BASE_URL} setPage={setPage} />
      )}
    </main>
  )
}

export default App
