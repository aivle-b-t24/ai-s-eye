import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'

import LoginPage from './components/user/LoginPage'
import SignupPage from './components/user/SignupPage'
import StoreDashboardView from './components/store/StoreDashboardView'
import SupervisorHeadOfficeView from './components/head-office/SupervisorHeadOfficeView'
import SettingsView from './components/settings/SettingsView'
import GnbHeader from './components/common/GnbHeader'
import RoleBanner from './components/common/RoleBanner'
import HeroSection from './components/HeroSection'
import Sidebar from './components/Sidebar'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

const QUEUE_STORE1 = [
  {
    visible_person_count: 24,
    queue_count_estimate: 4,
    quality_status: 'normal',
    zone_counts: { seating_1f: 10, aisle_1f: 4, counter_1f: 3, staff_1f: 2, seating_2f: 5, aisle_2f: 2, waiting_out: 4 },
    eta: { estimated_wait_minutes: 12 }
  },
  {
    visible_person_count: 26,
    queue_count_estimate: 5,
    quality_status: 'normal',
    zone_counts: { seating_1f: 11, aisle_1f: 4, counter_1f: 4, staff_1f: 2, seating_2f: 5, aisle_2f: 2, waiting_out: 5 },
    eta: { estimated_wait_minutes: 15 }
  },
  {
    visible_person_count: 22,
    queue_count_estimate: 3,
    quality_status: 'normal',
    zone_counts: { seating_1f: 9, aisle_1f: 3, counter_1f: 3, staff_1f: 2, seating_2f: 5, aisle_2f: 2, waiting_out: 3 },
    eta: { estimated_wait_minutes: 9 }
  },
  {
    visible_person_count: 20,
    queue_count_estimate: 2,
    quality_status: 'normal',
    zone_counts: { seating_1f: 8, aisle_1f: 3, counter_1f: 2, staff_1f: 2, seating_2f: 5, aisle_2f: 2, waiting_out: 2 },
    eta: { estimated_wait_minutes: 6 }
  }
]

const QUEUE_STORE2 = [
  {
    visible_person_count: 10,
    queue_count_estimate: 0,
    quality_status: 'normal',
    zone_counts: { seating_1f: 8, aisle_1f: 0, counter_1f: 2, staff_1f: 1, seating_2f: 0, aisle_2f: 0, waiting_out: 0 },
    eta: { estimated_wait_minutes: 0 }
  },
  {
    visible_person_count: 12,
    queue_count_estimate: 1,
    quality_status: 'normal',
    zone_counts: { seating_1f: 9, aisle_1f: 1, counter_1f: 2, staff_1f: 1, seating_2f: 0, aisle_2f: 0, waiting_out: 1 },
    eta: { estimated_wait_minutes: 3 }
  },
  {
    visible_person_count: 14,
    queue_count_estimate: 2,
    quality_status: 'normal',
    zone_counts: { seating_1f: 10, aisle_1f: 1, counter_1f: 3, staff_1f: 1, seating_2f: 0, aisle_2f: 0, waiting_out: 2 },
    eta: { estimated_wait_minutes: 6 }
  },
  {
    visible_person_count: 9,
    queue_count_estimate: 0,
    quality_status: 'normal',
    zone_counts: { seating_1f: 7, aisle_1f: 0, counter_1f: 2, staff_1f: 1, seating_2f: 0, aisle_2f: 0, waiting_out: 0 },
    eta: { estimated_wait_minutes: 0 }
  }
]

const MOCK_STORE_DATA = {
  'store-001': {
    state: QUEUE_STORE1[0],
    eta: QUEUE_STORE1[0].eta,
    menus: [
      { menu_id: 'm1', name: '아메리카노', price: 4000, available: true },
      { menu_id: 'm2', name: '카페 라떼', price: 4500, available: true },
      { menu_id: 'm3', name: '바닐라 빈 라떼', price: 5500, available: false },
      { menu_id: 'm4', name: '딸기 생크림 케이크', price: 6800, available: true }
    ],
    policies: [
      { policy_id: 'p1', title: '📢 착석 안내', content: '주문 후 번호표 순서대로 1층 또는 2층 안내에 따라 이동해 주세요.' },
      { policy_id: 'p2', title: '☕ 셀프 바 이용', content: '물과 냅킨은 각 층 중앙 셀프바에서 이용 가능합니다.' }
    ]
  },
  'store-002': {
    state: QUEUE_STORE2[0],
    eta: QUEUE_STORE2[0].eta,
    menus: [
      { menu_id: 'm201', name: '아메리카노', price: 4000, available: true },
      { menu_id: 'm202', name: '카페 라떼', price: 4500, available: true },
      { menu_id: 'm203', name: '카푸치노', price: 4500, available: true },
      { menu_id: 'm204', name: '에스프레소', price: 3500, available: true },
      { menu_id: 'm205', name: '바닐라 빈 라떼', price: 4500, available: false }
    ],
    policies: [
      { policy_id: 'p201', title: '⏰ 영업시간 안내', content: '오전 9시부터 오후 10시까지 영업합니다. (라스트 오더 21:30)' },
      { policy_id: 'p202', title: '🪑 좌석 및 단체석', content: '최대 6인까지 이용 가능한 단체석이 준비되어 있습니다.' },
      { policy_id: 'p203', title: '🛍️ 포장 및 테이크아웃', content: '전 메뉴 테이크아웃 가능합니다.' }
    ]
  }
}

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
  const [authMode, setAuthMode] = useState('login')
  const [currentUser, setCurrentUser] = useState(null)

  const [page, setPage] = useState("store-001")
  const [storesData, setStoresData] = useState(MOCK_STORE_DATA)
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)

  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [isUsingMock, setIsUsingMock] = useState(false)

  const lastStateJsonRef = useRef({})
  const indexStore1Ref = useRef(0)
  const indexStore2Ref = useRef(0)

  const handleLoginSuccess = (userData) => {
    setCurrentUser(userData)
    setPage(userData.storeId ?? 'store-001')
    setAuthMode('dashboard')
  }

  const handleLogout = () => {
    setCurrentUser(null)
    setAuthMode('login')
  }

  const getNextQueueState = (targetStoreId) => {
    if (targetStoreId === 'store-002') {
      indexStore2Ref.current = (indexStore2Ref.current + 1) % QUEUE_STORE2.length
      const nextItem = QUEUE_STORE2[indexStore2Ref.current]
      return {
        state: nextItem,
        eta: nextItem.eta
      }
    } else {
      indexStore1Ref.current = (indexStore1Ref.current + 1) % QUEUE_STORE1.length
      const nextItem = QUEUE_STORE1[indexStore1Ref.current]
      return {
        state: nextItem,
        eta: nextItem.eta
      }
    }
  }

  const loadStateOnly = useCallback(async (targetStoreId, isInitial = false) => {
    if (isInitial) setLoading(true)

    try {
      const stateData = await fetchStoreState(targetStoreId)
      const currentStateJson = JSON.stringify(stateData)

      if (lastStateJsonRef.current[targetStoreId] === currentStateJson) {
        setError('')
        setIsUsingMock(false)
        return
      }

      lastStateJsonRef.current[targetStoreId] = currentStateJson

      setStoresData((prev) => ({
        ...prev,
        [targetStoreId]: {
          ...(prev[targetStoreId] ?? MOCK_STORE_DATA[targetStoreId]),
          state: stateData,
        }
      }))
      setError('')
      setIsUsingMock(false)
    } catch (err) {
      setError(err.message)
      setIsUsingMock(true)

      const nextQueue = getNextQueueState(targetStoreId)
      setStoresData((prev) => ({
        ...prev,
        [targetStoreId]: {
          ...(prev[targetStoreId] ?? MOCK_STORE_DATA[targetStoreId]),
          state: nextQueue.state,
          eta: nextQueue.eta
        }
      }))
    } finally {
      setLoading(false)
    }
  }, [])

  const loadStaticData = useCallback(async (targetStoreId) => {
    try {
      const [menuData, policyData, etaData] = await Promise.all([
        fetchStoreMenus(targetStoreId),
        fetchStorePolicies(targetStoreId),
        fetchStoreEta(targetStoreId),
      ])
      setStoresData((prev) => ({
        ...prev,
        [targetStoreId]: {
          ...(prev[targetStoreId] ?? MOCK_STORE_DATA[targetStoreId]),
          menus: menuData?.menus ?? MOCK_STORE_DATA[targetStoreId]?.menus ?? [],
          policies: policyData?.policies ?? MOCK_STORE_DATA[targetStoreId]?.policies ?? [],
          eta: etaData ?? MOCK_STORE_DATA[targetStoreId]?.eta ?? null,
        }
      }))
    } catch {
      // Mock fallback
    }
  }, [])

  useEffect(() => {
    let timerId = null

    if (authMode === 'dashboard') {
      if (page === 'store-001' || page === 'store-002') {
        lastStateJsonRef.current[page] = ''

        loadStaticData(page)
        loadStateOnly(page, true)

        timerId = setInterval(() => {
          loadStateOnly(page, false)
        }, 2000)
      } else if (page === 'head-office') {
        loadStateOnly('store-001', false)
        loadStateOnly('store-002', false)
        timerId = null
      } else if (page === 'setting') {
        timerId = null
      }
    }

    return () => {
      if (timerId) clearInterval(timerId)
    }
  }, [authMode, page, loadStateOnly, loadStaticData])

  const activeDashboard = storesData[page] ?? MOCK_STORE_DATA[page] ?? MOCK_STORE_DATA['store-001']
  const soldOutCount = activeDashboard?.menus?.filter((menu) => !menu.available).length ?? 0

  if (authMode === 'login') {
    return (
      <LoginPage 
        onLogin={handleLoginSuccess}
        onGoToSignup={() => setAuthMode('signup')}
      />
    )
  }

  if (authMode === 'signup') {
    return (
      <SignupPage
        onGoToLogin={() => setAuthMode('login')}
        onCompleteSignup={() => setAuthMode('login')}
      />
    )
  }

  return (
  <main className="page-shell">
    {(page === 'store-001' || page === 'store-002') && (
      <>
        <HeroSection
          dashboard={activeDashboard}
          onMenuOpen={() => setIsSidebarOpen(true)}
        />

        <Sidebar
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
          page={page}
          setPage={setPage}
        />
      </>
    )}

    <section id="dashboard" className="dashboard-content">
      <GnbHeader
        page={page}
        setPage={setPage}
        loadStateOnly={loadStateOnly}
        loading={loading}
        user={currentUser}
        onLogout={handleLogout}
      />

      <RoleBanner
        page={page}
        apiBaseUrl={API_BASE_URL}
        isUsingMock={isUsingMock}
        error={error}
        loading={loading}
      />

      {(page === 'store-001' || page === 'store-002') && (
        <StoreDashboardView
          page={page}
          dashboard={activeDashboard}
          soldOutCount={soldOutCount}
        />
      )}

      {page === 'head-office' && (
        <SupervisorHeadOfficeView
          storesData={storesData}
        />
      )}

      {page === 'setting' && (
        <SettingsView
          apiBaseUrl={API_BASE_URL}
          setPage={setPage}
        />
      )}
    </section>
  </main>
)
  
}

export default App
