import { useEffect, useState } from 'react'
import {
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useOutletContext,
} from 'react-router-dom'
import './App.css'

import LoginPage from './components/user/LoginPage'
import SignupPage from './components/user/SignupPage'
import PasswordExpiryPrompt from './components/legal/PasswordExpiryPrompt'
import StoreDashboardView from './components/store/StoreDashboardView'
import SupervisorHeadOfficeView from './components/head-office/SupervisorHeadOfficeView'
import HeadOfficeHeader from './components/head-office/HeadOfficeHeader'
import SettingsView from './components/settings/SettingsView'
import GnbHeader from './components/common/GnbHeader'
import HeroSection from './components/HeroSection'
import Sidebar from './components/Sidebar'
import ProfileModal from './components/user/ProfileModal'
import KosStoreManagementView from './components/store/KosStoreManagementView'
import StoreOnboardingView from './components/onboarding/StoreOnboardingView'

import { useAuthContext } from './auth/AuthContext'
import { ROLES, STORES } from './constants/auth'
import { API_BASE_URL, CHATBOT_BASE_URL } from './constants/env'
import {
  LEGACY_ROUTES,
  ROUTES,
  homeForUser,
  pageFromPathname,
} from './constants/routes'
import { useStorePolling } from './hooks/useStorePolling'
import { useStoreSetup } from './hooks/useStoreSetup'
import { useChatbotSettings } from './hooks/useChatbotSettings'
import RequireAuth from './routes/RequireAuth'
import RequireStoreSetup from './routes/RequireStoreSetup'
import LegacyStoreRedirect from './routes/LegacyStoreRedirect'

function PublicShell() {
  const navigate = useNavigate()
  const location = useLocation()
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const {
    authRole,
    setAuthRole,
    currentUser,
    authReady,
    authError,
    handleLogin,
    handlePasswordReset,
    handleLoginRoleChange,
    handleSignupRoleChange,
    handleGoToSignup,
    handleGoToLogin,
    handleLoginSuccess,
  } = useAuthContext()

  const pathname = location.pathname
  const isLogin =
    pathname === ROUTES.STORE_LOGIN
    || pathname === ROUTES.HQ_LOGIN
    || pathname === '/login.aicafe'
  const isSignup =
    pathname === ROUTES.STORE_SIGNUP
    || pathname === ROUTES.HQ_SIGNUP
    || pathname === '/signup.aicafe'
  const authMode = isLogin ? 'login' : isSignup ? 'signup' : 'main'
  const page = pageFromPathname(pathname)

  const { activeDashboard } = useStorePolling({ enabled: false })

  useEffect(() => {
    if (pathname === ROUTES.HQ_LOGIN || pathname === ROUTES.HQ_SIGNUP) {
      setAuthRole(ROLES.ADMIN)
    } else if (
      pathname === ROUTES.STORE_LOGIN
      || pathname === ROUTES.STORE_SIGNUP
    ) {
      setAuthRole(ROLES.STORE_MANAGER)
    }
  }, [pathname, setAuthRole])

  if (authReady && currentUser) {
    return <Navigate to={homeForUser(currentUser)} replace />
  }

  // 회원가입·로그인은 모달이 아닌 전용 풀페이지로 렌더한다.
  if (isSignup) {
    return (
      <SignupPage
        initialRole={authRole}
        onRoleChange={handleSignupRoleChange}
        onGoToLogin={handleGoToLogin}
        onLogin={handleLogin}
        onClose={() => navigate(ROUTES.HOME)}
      />
    )
  }

  if (isLogin) {
    return (
      <LoginPage
        initialRole={authRole}
        onRoleChange={handleLoginRoleChange}
        initialError={authError}
        onLogin={handleLogin}
        onPasswordReset={handlePasswordReset}
        onGoToSignup={handleGoToSignup}
        onClose={() => navigate(ROUTES.HOME)}
      />
    )
  }

  return (
    <main className="page-shell is-main-landing has-hero">
      <HeroSection
        page={page}
        authMode={authMode}
        dashboard={activeDashboard}
        onMenuOpen={() => setIsSidebarOpen(true)}
        onLogin={() => {
          setAuthRole(ROLES.STORE_MANAGER)
          navigate(ROUTES.STORE_LOGIN)
        }}
        onSignup={() => {
          setAuthRole(ROLES.STORE_MANAGER)
          navigate(ROUTES.STORE_SIGNUP)
        }}
        onLoginSuccess={handleLoginSuccess}
        onCredentialLogin={handleLogin}
      />

      <Sidebar
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
      />


      <Outlet />
    </main>
  )
}

function StoreShell() {
  const location = useLocation()
  const [isProfileOpen, setIsProfileOpen] = useState(false)
  const { currentUser, handleLogout } = useAuthContext()
  const storeId = currentUser?.storeId
  const page = pageFromPathname(location.pathname)

  const {
    activeDashboard,
    soldOutCount,
    error,
    loading,
    loadStateOnly,
  } = useStorePolling({
    enabled: Boolean(storeId),
    storeId,
  })

  const { setupReady, needsOnboarding, refreshSetup } = useStoreSetup(storeId)

  const { chatbotSettingsMap, handleToggleChatbotForStore } =
    useChatbotSettings()

  return (
    <main className="page-shell has-hero">
      <GnbHeader
        page={page}
        loadStateOnly={loadStateOnly}
        loading={loading}
        user={currentUser}
        needsOnboarding={needsOnboarding}
        onLogout={handleLogout}
        onOpenProfile={() => setIsProfileOpen(true)}
      />

      {isProfileOpen && currentUser && (
        <ProfileModal
          user={currentUser}
          onClose={() => setIsProfileOpen(false)}
          onLogout={handleLogout}
        />
      )}

      <section id="dashboard" className="dashboard-content">
        <Outlet
          context={{
            storeId,
            storeName: currentUser?.storeName,
            activeDashboard,
            soldOutCount,
            error,
            loading,
            chatbotSettingsMap,
            handleToggleChatbotForStore,
            setupReady,
            needsOnboarding,
            refreshSetup,
          }}
        />
      </section>
    </main>
  )
}

function HqShell() {
  const [isProfileOpen, setIsProfileOpen] = useState(false)
  const { currentUser, handleLogout } = useAuthContext()

  useStorePolling({
    enabled: true,
    isHeadOffice: true,
  })

  return (
    <main className="page-shell supervisor-shell no-hero">
      <HeadOfficeHeader
        user={currentUser}
        onLogout={handleLogout}
        onOpenProfile={() => setIsProfileOpen(true)}
      />

      {isProfileOpen && currentUser && (
        <ProfileModal
          user={currentUser}
          onClose={() => setIsProfileOpen(false)}
          onLogout={handleLogout}
        />
      )}

      <section id="dashboard" className="dashboard-content">
        <Outlet />
      </section>
    </main>
  )
}

function useStoreShellContext() {
  return useOutletContext()
}

function StoreDashboardRoute() {
  const { currentUser } = useAuthContext()
  const storeId = currentUser?.storeId
  const {
    activeDashboard,
    soldOutCount,
    error,
    loading,
    chatbotSettingsMap,
  } = useStoreShellContext()

  return (
    <StoreDashboardView
      page={storeId}
      storeName={currentUser?.storeName}
      dashboard={activeDashboard}
      soldOutCount={soldOutCount}
      apiBaseUrl={API_BASE_URL}
      error={error}
      loading={loading}
      isChatbotEnabled={chatbotSettingsMap[storeId] !== false}
    />
  )
}

function MenusRoute() {
  const { currentUser } = useAuthContext()
  const storeId = currentUser?.storeId
  const {
    activeDashboard,
    soldOutCount,
    error,
    loading,
    chatbotSettingsMap,
  } = useStoreShellContext()

  return (
    <KosStoreManagementView
      page={storeId}
      storeName={currentUser?.storeName}
      dashboard={activeDashboard}
      soldOutCount={soldOutCount}
      apiBaseUrl={API_BASE_URL}
      error={error}
      loading={loading}
      isChatbotEnabled={chatbotSettingsMap[storeId] !== false}
    />
  )
}

function SettingsRoute() {
  const navigate = useNavigate()
  const { currentUser } = useAuthContext()
  const storeId =
    currentUser?.role === ROLES.STORE_MANAGER
      ? currentUser.storeId
      : STORES.DONGMYEONG
  const {
    chatbotSettingsMap,
    handleToggleChatbotForStore,
    needsOnboarding,
  } = useStoreShellContext()

  return (
    <SettingsView
      apiBaseUrl={API_BASE_URL}
      aiccBaseUrl={CHATBOT_BASE_URL}
      onBack={() => navigate(
        needsOnboarding ? ROUTES.ONBOARDING : ROUTES.DASHBOARD,
      )}
      storeId={storeId}
      storeName={
        currentUser?.role === ROLES.STORE_MANAGER
          ? currentUser.storeName
          : undefined
      }
      isChatbotEnabled={chatbotSettingsMap[storeId] !== false}
      onToggleChatbot={(enabled) =>
        handleToggleChatbotForStore(storeId, enabled)
      }
    />
  )
}

function OnboardingRoute() {
  const navigate = useNavigate()
  const { currentUser } = useAuthContext()
  const storeId = currentUser?.storeId
  const { refreshSetup } = useStoreShellContext()

  return (
    <StoreOnboardingView
      apiBaseUrl={API_BASE_URL}
      aiccBaseUrl={CHATBOT_BASE_URL}
      storeId={storeId}
      onComplete={async () => {
        await refreshSetup?.()
        navigate(ROUTES.DASHBOARD, { replace: true })
      }}
    />
  )
}

function HqRoute() {
  return (
    <SupervisorHeadOfficeView
      apiBaseUrl={API_BASE_URL}
      aiccBaseUrl={CHATBOT_BASE_URL}
    />
  )
}

function AuthBootstrap({ children }) {
  const { authReady } = useAuthContext()
  if (!authReady) {
    return <div className="route-loading" aria-live="polite">인증 확인 중…</div>
  }
  return children
}

function App() {
  return (
    <AuthBootstrap>
      <PasswordExpiryPrompt />
      <Routes>
        <Route element={<PublicShell />}>
          <Route path={ROUTES.HOME} element={null} />
          <Route path="/main" element={<Navigate to={ROUTES.HOME} replace />} />
          <Route path="/main.aicafe" element={<Navigate to={ROUTES.HOME} replace />} />
          <Route path={ROUTES.STORE_LOGIN} element={null} />
          <Route path={ROUTES.HQ_LOGIN} element={null} />
          <Route path="/login.aicafe" element={<Navigate to={ROUTES.STORE_LOGIN} replace />} />
          <Route path="/storelogin" element={<Navigate to={ROUTES.STORE_LOGIN} replace />} />
          <Route path="/hqlogin" element={<Navigate to={ROUTES.HQ_LOGIN} replace />} />
          <Route path="/aicafe/storelogin" element={<Navigate to={ROUTES.STORE_LOGIN} replace />} />
          <Route path="/aicafe/hqlogin" element={<Navigate to={ROUTES.HQ_LOGIN} replace />} />
          <Route path="/aicafe/login" element={<Navigate to={ROUTES.STORE_LOGIN} replace />} />
          <Route path={ROUTES.STORE_SIGNUP} element={null} />
          <Route path={ROUTES.HQ_SIGNUP} element={null} />
          <Route path="/signup.aicafe" element={<Navigate to={ROUTES.STORE_SIGNUP} replace />} />
          <Route path="/signup" element={<Navigate to={ROUTES.STORE_SIGNUP} replace />} />
          <Route path="/storesignup" element={<Navigate to={ROUTES.STORE_SIGNUP} replace />} />
          <Route path="/hqsignup" element={<Navigate to={ROUTES.HQ_SIGNUP} replace />} />
          <Route path="/aicafe/storesignup" element={<Navigate to={ROUTES.STORE_SIGNUP} replace />} />
          <Route path="/aicafe/hqsignup" element={<Navigate to={ROUTES.HQ_SIGNUP} replace />} />
          <Route path="/aicafe/signup" element={<Navigate to={ROUTES.STORE_SIGNUP} replace />} />
        </Route>

        <Route
          element={(
            <RequireAuth roles={[ROLES.STORE_MANAGER]} loginPath={ROUTES.HOME}>
              <StoreShell />
            </RequireAuth>
          )}
        >
          <Route element={<RequireStoreSetup />}>
            <Route path={ROUTES.DASHBOARD} element={<StoreDashboardRoute />} />
            <Route path={ROUTES.MENUS} element={<MenusRoute />} />
            <Route path={LEGACY_ROUTES.KOS} element={<Navigate to={ROUTES.MENUS} replace />} />
          </Route>
          <Route path={ROUTES.ONBOARDING} element={<OnboardingRoute />} />
          <Route path={ROUTES.SETTINGS} element={<SettingsRoute />} />
        </Route>

        <Route
          element={(
            <RequireAuth roles={[ROLES.ADMIN]} loginPath={ROUTES.HOME}>
              <HqShell />
            </RequireAuth>
          )}
        >
          <Route path={ROUTES.HQ} element={<HqRoute />} />
          <Route path={LEGACY_ROUTES.HQ_AICAFE} element={<Navigate to={ROUTES.HQ} replace />} />
          <Route path="/aicafe/hq" element={<Navigate to={ROUTES.HQ} replace />} />
        </Route>

        <Route path="/store/:storeId" element={<Navigate to={ROUTES.DASHBOARD} replace />} />
        <Route path="/aicafe/store/:storeId" element={<Navigate to={ROUTES.DASHBOARD} replace />} />
        <Route path="/:storeFile" element={<LegacyStoreRedirect />} />
        <Route path="*" element={<Navigate to={ROUTES.HOME} replace />} />
      </Routes>
    </AuthBootstrap>
  )
}

export default App
