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

function App() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false)
  const [isProfileOpen, setIsProfileOpen] = useState(false)

  const {
    authMode,
    setAuthMode,
    authRole,
    setAuthRole,
    currentUser,
    handleLoginRoleChange,
    handleSignupRoleChange,
    handleGoToSignup,
    handleGoToLogin,
    handleLoginSuccess,
    handleLogout,
  } = useAuth()

  const { page, setPage } = useRouting(currentUser, setAuthMode, setAuthRole)

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
        !isDedicatedHeadOffice ? 'has-hero' : '',
        isDedicatedHeadOffice ? 'supervisor-shell no-hero' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {authMode === 'dashboard' && !isDedicatedHeadOffice && (
        <div className="top-global-nav is-overlay">
          <GnbHeader
            page={page}
            setPage={setPage}
            loadStateOnly={loadStateOnly}
            loading={loading}
            user={currentUser}
            onLogout={handleLogout}
            onOpenProfile={() => setIsProfileOpen(true)}
          />
        </div>
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
        !isDedicatedHeadOffice) && (
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
              onLogin={(userData) => handleLoginSuccess(userData, setPage)}
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
          {(page === 'store-001' || page === 'store-002') && (
            <StoreDashboardView
              page={page}
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

          {page === 'setting' && (
            <SettingsView
              apiBaseUrl={API_BASE_URL}
              setPage={setPage}
              storeId={
                currentUser?.role === ROLES.STORE_MANAGER
                  ? currentUser.storeId
                  : STORES.DONGMYEONG
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
