import { useState } from 'react'
import './App.css'

import LoginPage from './components/user/LoginPage'
import SignupPage from './components/user/SignupPage'
import StoreDashboardView from './components/store/StoreDashboardView'
import SupervisorHeadOfficeView from './components/head-office/SupervisorHeadOfficeView'
import HeadOfficeHeader from './components/head-office/HeadOfficeHeader'

import SettingsView from './components/settings/SettingsView'
import GnbHeader from './components/common/GnbHeader'
import HeroSection from './components/HeroSection'
import Sidebar from './components/Sidebar'
import ProfileModal from './components/user/ProfileModal'

import { ROLES, STORES } from './constants/auth'
import { API_BASE_URL, CHATBOT_BASE_URL } from './constants/env'
import { useAuth } from './hooks/useAuth'
import { useRouting } from './hooks/useRouting'
import { useStorePolling } from './hooks/useStorePolling'
import { useChatbotSettings } from './hooks/useChatbotSettings'

import KosStoreManagementView from './components/store/KosStoreManagementView'

function App() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [isProfileOpen, setIsProfileOpen] = useState(false)

  const {
    authMode,
    setAuthMode,
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
    handleLogout,
  } = useAuth()

  const { page, setPage } = useRouting(
    currentUser,
    authReady,
    setAuthMode,
    setAuthRole,
  )

  const isDedicatedHeadOffice = page === STORES.HEAD_OFFICE

  const {
    activeDashboard,
    soldOutCount,
    error,
    loading,
    loadStateOnly,
  } = useStorePolling(authMode, page, isDedicatedHeadOffice)

  const { chatbotSettingsMap, handleToggleChatbotForStore } =
    useChatbotSettings()

  return (
    <main
      className={[
        'page-shell',
        authMode === 'main' ? 'is-main-landing' : '',
        !isDedicatedHeadOffice ? 'has-hero' : '',
        isDedicatedHeadOffice ? 'supervisor-shell no-hero' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {authMode === 'dashboard' && !isDedicatedHeadOffice && (
        
          <GnbHeader
            page={page}
            setPage={setPage}
            loadStateOnly={loadStateOnly}
            loading={loading}
            user={currentUser}
            onLogout={handleLogout}
            onOpenProfile={() => setIsProfileOpen(true)}
          />
        
      )}

      {authMode === 'dashboard' && isDedicatedHeadOffice && (
        <HeadOfficeHeader
          user={currentUser}
          onLogout={handleLogout}
          onOpenProfile={() => setIsProfileOpen(true)}
        />
      )}

      {isProfileOpen && currentUser && (
        <ProfileModal
          user={currentUser}
          onClose={() => setIsProfileOpen(false)}
          onLogout={handleLogout}
        />
      )}

      {(authMode === 'login' ||
        authMode === 'signup' ||
        authMode === 'main') && (
        <HeroSection
          page={page}
          authMode={authMode}
          dashboard={activeDashboard}
          onMenuOpen={() => setIsSidebarOpen(true)}
          onLogin={() => {
            setAuthRole(ROLES.STORE_MANAGER)
            setAuthMode('login')
          }}
          onSignup={() => {
            setAuthRole(ROLES.STORE_MANAGER)
            setAuthMode('signup')
          }}
          onLoginSuccess={(userData) => handleLoginSuccess(userData, setPage)}
          onCredentialLogin={(credentials) => handleLogin(credentials, setPage)}
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
              initialError={authError}
              onLogin={(credentials) => handleLogin(credentials, setPage)}
              onPasswordReset={handlePasswordReset}
              onGoToSignup={handleGoToSignup}
              onClose={() => setAuthMode('main')}
            />
          )}
          {authMode === 'signup' && (
            <SignupPage
              initialRole={authRole}
              onRoleChange={handleSignupRoleChange}
              onGoToLogin={handleGoToLogin}
              onCompleteSignup={handleGoToLogin}
              onClose={() => setAuthMode('main')}
            />
          )}
        </div>
      )}

      {authMode === 'dashboard' && (
        <section id="dashboard" className="dashboard-content">
          {String(page).startsWith('store') && (
            <StoreDashboardView
              page={page}
              storeName={currentUser?.storeName}
              dashboard={activeDashboard}
              soldOutCount={soldOutCount}
              apiBaseUrl={API_BASE_URL}
              error={error}
              loading={loading}
              isChatbotEnabled={chatbotSettingsMap[page] !== false}
            />
          )}

          {(page === 'head-office' || isDedicatedHeadOffice) && (
            <SupervisorHeadOfficeView
              apiBaseUrl={API_BASE_URL}
              aiccBaseUrl={CHATBOT_BASE_URL}
            />
          )}

          {page === 'kos' && (
            <KosStoreManagementView
              page={currentUser?.storeId || page}
              storeName={currentUser?.storeName}
              dashboard={activeDashboard}
              soldOutCount={soldOutCount}
              apiBaseUrl={API_BASE_URL}
              error={error}
              loading={loading}
              isChatbotEnabled={
                chatbotSettingsMap[currentUser?.storeId || page] !== false
              }
            />
          )}

          {page === 'setting' && (
            <SettingsView
              apiBaseUrl={API_BASE_URL}
              aiccBaseUrl={CHATBOT_BASE_URL}
              setPage={setPage}
              storeId={
                currentUser?.role === ROLES.STORE_MANAGER
                  ? currentUser.storeId
                  : STORES.DONGMYEONG
              }
              storeName={
                currentUser?.role === ROLES.STORE_MANAGER
                  ? currentUser.storeName
                  : undefined
              }
              isChatbotEnabled={
                chatbotSettingsMap[
                  currentUser?.role === ROLES.STORE_MANAGER
                    ? currentUser.storeId
                    : STORES.DONGMYEONG
                ] !== false
              }
              onToggleChatbot={(enabled) =>
                handleToggleChatbotForStore(
                  currentUser?.role === ROLES.STORE_MANAGER
                    ? currentUser.storeId
                    : STORES.DONGMYEONG,
                  enabled
                )
              }
            />
          )}
        </section>
      )}
    </main>
  )
}

export default App
