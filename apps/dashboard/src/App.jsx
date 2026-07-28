import { useCallback, useEffect, useState } from 'react'
import './App.css'

import LoginPage from './components/user/LoginPage'
import SignupPage from './components/user/SignupPage'
import StoreDashboardView from './components/store/StoreDashboardView'
import SupervisorHeadOfficeView from './components/head-office/SupervisorHeadOfficeView'
import HeadOfficeHeader from './components/head-office/HeadOfficeHeader'

import SettingsView from './components/settings/SettingsView'
import GnbHeader from './components/common/GnbHeader'
import RoleBanner from './components/common/RoleBanner'
import HeroSection from './components/HeroSection'
import Sidebar from './components/Sidebar'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const AICC_BASE_URL = import.meta.env.VITE_AICC_BASE_URL ?? 'http://localhost:8100'

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

  const [page, setPage] = useState("store-001")
  const [storesData, setStoresData] = useState(DEFAULT_STORE_DATA)
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)

  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [isUsingMock, setIsUsingMock] = useState(false)
  const isDedicatedHeadOffice =
    page === 'head-office' && window.location.pathname === '/hq'

  const handleLoginSuccess = (userData) => {
    const nextPage = userData.storeId ?? 'store-001'
    setCurrentUser(userData)
    setPage(nextPage)
    setAuthMode('dashboard')
    window.history.replaceState(
      {},
      '',
      nextPage === 'head-office' ? '/hq' : `/store/${nextPage}`,
    )
  }

  const handleLogout = () => {
    setCurrentUser(null)
    setAuthMode('login')
    window.history.replaceState({}, '', '/')
  }

  const loadStateOnly = useCallback(async (targetStoreId, isInitial = false) => {
    if (isInitial) setLoading(true)

    try {
      const [stateData, etaData] = await Promise.all([
        fetchStoreState(targetStoreId),
        fetchStoreEta(targetStoreId),
      ])

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
        loadStaticData(page)
        loadStateOnly(page, true)

        timerId = setInterval(() => {
          loadStateOnly(page, false)
        }, 2000)
      } else if (page === 'head-office' && !isDedicatedHeadOffice) {
        loadStateOnly('store-001', false)
        loadStateOnly('store-002', false)
        timerId = null
      } else if (page === 'head-office' || page === 'setting') {
        timerId = null
      }
    }

    return () => {
      if (timerId) clearInterval(timerId)
    }
  }, [
    authMode,
    page,
    isDedicatedHeadOffice,
    loadStateOnly,
    loadStaticData,
  ])

  const activeDashboard =
    storesData[page] ??
    DEFAULT_STORE_DATA[page] ??
    DEFAULT_STORE_DATA['store-001']

  const soldOutCount =
    activeDashboard?.menus?.filter((menu) => !menu.available).length ?? 0

  return (
    <main
      className={[
        'page-shell',
        authMode === 'dashboard' && !isDedicatedHeadOffice ? 'has-hero' : '',
        authMode === 'dashboard' && isDedicatedHeadOffice
          ? 'supervisor-shell no-hero'
          : '',
      ].filter(Boolean).join(' ')}
    >
      {authMode === 'dashboard' && !isDedicatedHeadOffice && (
        <div
          className="top-global-nav is-overlay"
        >
          <GnbHeader
            page={page}
            setPage={setPage}
            loadStateOnly={loadStateOnly}
            loading={loading}
            user={currentUser}
            onLogout={handleLogout}
          />
        </div>
      )}

      {authMode === 'dashboard' && isDedicatedHeadOffice && (
        <HeadOfficeHeader
          user={currentUser}
          onLogout={handleLogout}
        />
      )}

      {!isDedicatedHeadOffice && (
        <HeroSection
          page={page}
          authMode={authMode}
          dashboard={activeDashboard}
          onMenuOpen={() => setIsSidebarOpen(true)}
        />
      )}

      {!isDedicatedHeadOffice && (
        <Sidebar
          isOpen={isSidebarOpen}
          onClose={() => setIsSidebarOpen(false)}
          page={page}
          setPage={setPage}
        />
      )}

      {(authMode === 'login' || authMode === 'signup') && (
        <div className="auth-modal-overlay">
          {authMode === 'login' && (
            <LoginPage
              onLogin={handleLoginSuccess}
              onGoToSignup={() => setAuthMode('signup')}
              onClose={() => setAuthMode('dashboard')}
            />
          )}
          {authMode === 'signup' && (
            <SignupPage
              onGoToLogin={() => setAuthMode('login')}
              onCompleteSignup={() => setAuthMode('login')}
              onClose={() => setAuthMode('dashboard')}
            />
          )}
        </div>
      )}


      {authMode === 'dashboard' && (
        <section id="dashboard" className="dashboard-content">
          

          {!isDedicatedHeadOffice && (
            <RoleBanner
              page={page}
              apiBaseUrl={API_BASE_URL}
              isUsingMock={isUsingMock}
              error={error}
              loading={loading}
            />
          )}

          {(page === 'store-001' || page === 'store-002') && (
            <StoreDashboardView
              page={page}
              dashboard={activeDashboard}
              soldOutCount={soldOutCount}
            />
          )}

          {(page === 'head-office' || isDedicatedHeadOffice) && (
            <SupervisorHeadOfficeView
              apiBaseUrl={API_BASE_URL}
              aiccBaseUrl={AICC_BASE_URL}
            />
          )}


          {page === 'setting' && (
            <SettingsView
              apiBaseUrl={API_BASE_URL}
              setPage={setPage}
            />
          )}
        </section>
      )}
    </main>
  )
}

export default App
