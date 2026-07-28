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

import {
  ROLES,
  STORES,
  ENDPOINTS,
  DEFAULT_STORE_DATA,
} from './constants/auth'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const AICC_BASE_URL = import.meta.env.VITE_AICC_BASE_URL ?? 'http://localhost:8100'

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
  const [authRole, setAuthRole] = useState('store_manager')
  const [currentUser, setCurrentUser] = useState(null)

  const [page, setPage] = useState("store-001")
  const [storesData, setStoresData] = useState(DEFAULT_STORE_DATA)
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)

  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [isUsingMock, setIsUsingMock] = useState(false)
  const isDedicatedHeadOffice = page === STORES.HEAD_OFFICE

  // 🔒 Strict Auth Guard & Role Endpoint Router Sync Effect (.aicafe URL endpoints)
  useEffect(() => {
    const handleUrlRouting = () => {
      const pathname = window.location.pathname

      // 1. Role-based Signup Endpoints (/storesignup.aicafe, /hqsignup.aicafe)
      if (
        pathname === ENDPOINTS.STORE_SIGNUP ||
        pathname === '/storesignup' ||
        pathname === '/aicafe/storesignup'
      ) {
        setAuthMode('signup')
        setAuthRole(ROLES.STORE_MANAGER)
        if (pathname !== ENDPOINTS.STORE_SIGNUP) {
          window.history.replaceState({}, '', ENDPOINTS.STORE_SIGNUP)
        }
        return
      }

      if (
        pathname === ENDPOINTS.HQ_SIGNUP ||
        pathname === '/hqsignup' ||
        pathname === '/aicafe/hqsignup'
      ) {
        setAuthMode('signup')
        setAuthRole(ROLES.ADMIN)
        if (pathname !== ENDPOINTS.HQ_SIGNUP) {
          window.history.replaceState({}, '', ENDPOINTS.HQ_SIGNUP)
        }
        return
      }

      if (pathname === '/signup.aicafe' || pathname === '/signup' || pathname === '/aicafe/signup') {
        setAuthMode('signup')
        setAuthRole(ROLES.STORE_MANAGER)
        window.history.replaceState({}, '', ENDPOINTS.STORE_SIGNUP)
        return
      }

      // 2. Role-based Login Endpoints (/storelogin.aicafe, /hqlogin.aicafe)
      if (
        pathname === ENDPOINTS.STORE_LOGIN ||
        pathname === '/storelogin' ||
        pathname === '/aicafe/storelogin'
      ) {
        setAuthMode('login')
        setAuthRole(ROLES.STORE_MANAGER)
        if (pathname !== ENDPOINTS.STORE_LOGIN) {
          window.history.replaceState({}, '', ENDPOINTS.STORE_LOGIN)
        }
        return
      }

      if (
        pathname === ENDPOINTS.HQ_LOGIN ||
        pathname === '/hqlogin' ||
        pathname === '/aicafe/hqlogin'
      ) {
        setAuthMode('login')
        setAuthRole(ROLES.ADMIN)
        if (pathname !== ENDPOINTS.HQ_LOGIN) {
          window.history.replaceState({}, '', ENDPOINTS.HQ_LOGIN)
        }
        return
      }

      if (
        pathname === '/login.aicafe' ||
        pathname === '/aicafe/login' ||
        pathname === '/' ||
        pathname === ''
      ) {
        setAuthMode('login')
        setAuthRole(ROLES.STORE_MANAGER)
        if (pathname !== ENDPOINTS.STORE_LOGIN) {
          window.history.replaceState({}, '', ENDPOINTS.STORE_LOGIN)
        }
        return
      }

      // 3. Strict Auth Guard: If not logged in during this active React session (currentUser is null)
      if (!currentUser) {
        setAuthMode('login')
        setAuthRole(ROLES.STORE_MANAGER)
        window.history.replaceState({}, '', ENDPOINTS.STORE_LOGIN)
        return
      }

      // 4. Role-Based Authorization Guard & Endpoint Parsing (.aicafe endpoints)
      if (
        pathname === ENDPOINTS.HQ_DASHBOARD ||
        pathname === '/aicafe/hq' ||
        pathname === '/hq'
      ) {
        if (currentUser.role !== ROLES.ADMIN && currentUser.storeId !== STORES.HEAD_OFFICE) {
          // Block non-admin from accessing HQ endpoint, redirect to store endpoint
          const userStore = currentUser.storeId || STORES.DONGMYEONG
          setPage(userStore)
          setAuthMode('dashboard')
          window.history.replaceState({}, '', `/${userStore}.aicafe`)
          return
        }
        setPage(STORES.HEAD_OFFICE)
        setAuthMode('dashboard')
        if (pathname !== ENDPOINTS.HQ_DASHBOARD) {
          window.history.replaceState({}, '', ENDPOINTS.HQ_DASHBOARD)
        }
      } else if (pathname.endsWith('.aicafe')) {
        const storeId = pathname.replace('/', '').replace('.aicafe', '')
        setPage(storeId || STORES.DONGMYEONG)
        setAuthMode('dashboard')
      } else if (pathname.startsWith('/aicafe/store/')) {
        const storeId = pathname.replace('/aicafe/store/', '')
        setPage(storeId || STORES.DONGMYEONG)
        setAuthMode('dashboard')
        window.history.replaceState({}, '', `/${storeId || STORES.DONGMYEONG}.aicafe`)
      } else if (pathname.startsWith('/store/')) {
        const storeId = pathname.replace('/store/', '')
        setPage(storeId || STORES.DONGMYEONG)
        setAuthMode('dashboard')
        window.history.replaceState({}, '', `/${storeId || STORES.DONGMYEONG}.aicafe`)
      } else {
        setAuthMode('login')
        setAuthRole(ROLES.STORE_MANAGER)
        window.history.replaceState({}, '', ENDPOINTS.STORE_LOGIN)
      }
    }

    handleUrlRouting()
    window.addEventListener('popstate', handleUrlRouting)
    return () => window.removeEventListener('popstate', handleUrlRouting)
  }, [currentUser])

  const handleLoginRoleChange = (newRole) => {
    setAuthRole(newRole)
    const newEndpoint = newRole === ROLES.STORE_MANAGER ? ENDPOINTS.STORE_LOGIN : ENDPOINTS.HQ_LOGIN
    window.history.pushState({}, '', newEndpoint)
  }

  const handleSignupRoleChange = (newRole) => {
    setAuthRole(newRole)
    const newEndpoint = newRole === ROLES.STORE_MANAGER ? ENDPOINTS.STORE_SIGNUP : ENDPOINTS.HQ_SIGNUP
    window.history.pushState({}, '', newEndpoint)
  }

  const handleGoToSignup = () => {
    setAuthMode('signup')
    const targetEndpoint = authRole === ROLES.STORE_MANAGER ? ENDPOINTS.STORE_SIGNUP : ENDPOINTS.HQ_SIGNUP
    window.history.pushState({}, '', targetEndpoint)
  }

  const handleGoToLogin = () => {
    setAuthMode('login')
    const targetEndpoint = authRole === ROLES.STORE_MANAGER ? ENDPOINTS.STORE_LOGIN : ENDPOINTS.HQ_LOGIN
    window.history.pushState({}, '', targetEndpoint)
  }


  const handleLoginSuccess = (userData) => {
    const nextPage = userData.storeId ?? STORES.DONGMYEONG
    setCurrentUser(userData)
    setPage(nextPage)
    setAuthMode('dashboard')

    const targetEndpoint = nextPage === STORES.HEAD_OFFICE
      ? ENDPOINTS.HQ_DASHBOARD
      : `/${nextPage}.aicafe`

    window.history.pushState({}, '', targetEndpoint)
  }

  const handleLogout = () => {
    setCurrentUser(null)
    setAuthMode('login')
    window.history.pushState({}, '', ENDPOINTS.STORE_LOGIN)
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

  // ⏱ Smart Polling: Pauses automatically when tab is hidden (document.hidden) to save battery/network
  useEffect(() => {
    let timerId = null

    const startTimer = () => {
      if (timerId) clearInterval(timerId)
      if (!document.hidden && authMode === 'dashboard') {
        if (page === STORES.DONGMYEONG || page === STORES.SUWAN) {
          timerId = setInterval(() => {
            loadStateOnly(page, false)
          }, 2000)
        }
      }
    }

    const handleVisibilityChange = () => {
      if (document.hidden) {
        if (timerId) {
          clearInterval(timerId)
          timerId = null
        }
      } else {
        if (authMode === 'dashboard' && (page === STORES.DONGMYEONG || page === STORES.SUWAN)) {
          loadStateOnly(page, false)
          startTimer()
        }
      }
    }

    if (authMode === 'dashboard') {
      if (page === STORES.DONGMYEONG || page === STORES.SUWAN) {
        loadStaticData(page)
        loadStateOnly(page, true)
        startTimer()
      } else if (page === STORES.HEAD_OFFICE && !isDedicatedHeadOffice) {
        loadStateOnly(STORES.DONGMYEONG, false)
        loadStateOnly(STORES.SUWAN, false)
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      if (timerId) clearInterval(timerId)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
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
        !isDedicatedHeadOffice ? 'has-hero' : '',
        isDedicatedHeadOffice ? 'supervisor-shell no-hero' : '',
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

      {(authMode === 'login' || authMode === 'signup' || !isDedicatedHeadOffice) && (
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
              initialRole={authRole}
              onRoleChange={handleLoginRoleChange}
              onLogin={handleLoginSuccess}
              onGoToSignup={handleGoToSignup}
              onClose={() => setAuthMode('dashboard')}
            />
          )}
          {authMode === 'signup' && (
            <SignupPage
              initialRole={authRole}
              onRoleChange={handleSignupRoleChange}
              onGoToLogin={handleGoToLogin}
              onCompleteSignup={handleGoToLogin}
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
