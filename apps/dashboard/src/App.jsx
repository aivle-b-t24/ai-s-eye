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

const DEFAULT_STORE_DATA = {
  'store-001': {
    state: null,
    eta: null,
    menus: [],
    policies: []
  },
  'store-002': {
    state: null,
    eta: null,
    menus: [],
    policies: []
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

  const [page, setPage] = useState('store-001')
  const [storesData, setStoresData] = useState(DEFAULT_STORE_DATA)
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)

  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [isUsingMock, setIsUsingMock] = useState(false)

  const lastStateJsonRef = useRef({})

  const handleLoginSuccess = (userData) => {
    setCurrentUser(userData)
    setPage(userData.storeId ?? 'store-001')
    setAuthMode('dashboard')
  }

  const handleLogout = () => {
    setCurrentUser(null)
    setAuthMode('login')
  }

  const loadStateOnly = useCallback(async (targetStoreId, isInitial = false) => {
    if (isInitial) setLoading(true)

    try {
      const [stateData, etaData] = await Promise.all([
        fetchStoreState(targetStoreId),
        fetchStoreEta(targetStoreId),
      ])
      const currentStateJson = JSON.stringify({ stateData, etaData })

      if (lastStateJsonRef.current[targetStoreId] === currentStateJson) {
        setError('')
        setIsUsingMock(false)
        return
      }

      lastStateJsonRef.current[targetStoreId] = currentStateJson

      setStoresData((prev) => ({
        ...prev,
        [targetStoreId]: {
          ...(prev[targetStoreId] ?? DEFAULT_STORE_DATA[targetStoreId]),
          state: stateData,
          eta: etaData ?? prev[targetStoreId]?.eta ?? null,
        }
      }))
      setError('')
      setIsUsingMock(false)
    } catch (err) {
      setError(err.message)
      setIsUsingMock(true)
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
          ...(prev[targetStoreId] ?? DEFAULT_STORE_DATA[targetStoreId]),
          menus: menuData?.menus ?? [],
          policies: policyData?.policies ?? [],
          eta: etaData ?? null,
        }
      }))
    } catch {
      // API Error handler
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
      }
    }

    return () => {
      if (timerId) clearInterval(timerId)
    }
  }, [authMode, page, loadStateOnly, loadStaticData])

  const activeDashboard =
    storesData[page] ??
    DEFAULT_STORE_DATA[page] ??
    DEFAULT_STORE_DATA['store-001']

  const soldOutCount =
    activeDashboard?.menus?.filter((menu) => !menu.available).length ?? 0

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

  const hasHero =
    page === 'store-001' ||
    page === 'store-002' ||
    page === 'head-office'

  return (
    <main className={`page-shell ${hasHero ? 'has-hero' : 'no-hero'}`}>
      <div className={`top-global-nav ${hasHero ? 'is-overlay' : 'is-solid'}`}>
        <GnbHeader
          page={page}
          setPage={setPage}
          loadStateOnly={loadStateOnly}
          loading={loading}
          user={currentUser}
          onLogout={handleLogout}
        />
      </div>

      {hasHero && (
        <>
          <HeroSection
            page={page}
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
          <SupervisorHeadOfficeView storesData={storesData} />
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
