import { useState } from 'react'
import { ROLES, STORES, ENDPOINTS } from '../constants/auth'

export function useAuth() {
  const [authMode, setAuthMode] = useState('main')
  const [authRole, setAuthRole] = useState(ROLES.STORE_MANAGER)
  const [currentUser, setCurrentUser] = useState(null)

  const handleLoginRoleChange = (newRole) => {
    setAuthRole(newRole)
    const newEndpoint =
      newRole === ROLES.STORE_MANAGER ? ENDPOINTS.STORE_LOGIN : ENDPOINTS.HQ_LOGIN
    window.history.pushState({}, '', newEndpoint)
  }

  const handleSignupRoleChange = (newRole) => {
    setAuthRole(newRole)
    const newEndpoint =
      newRole === ROLES.STORE_MANAGER ? ENDPOINTS.STORE_SIGNUP : ENDPOINTS.HQ_SIGNUP
    window.history.pushState({}, '', newEndpoint)
  }

  const handleGoToSignup = () => {
    setAuthMode('signup')
    const targetEndpoint =
      authRole === ROLES.STORE_MANAGER ? ENDPOINTS.STORE_SIGNUP : ENDPOINTS.HQ_SIGNUP
    window.history.pushState({}, '', targetEndpoint)
  }

  const handleGoToLogin = () => {
    setAuthMode('login')
    const targetEndpoint =
      authRole === ROLES.STORE_MANAGER ? ENDPOINTS.STORE_LOGIN : ENDPOINTS.HQ_LOGIN
    window.history.pushState({}, '', targetEndpoint)
  }

  const handleLoginSuccess = (userData, setPage) => {
    const nextPage = userData.storeId ?? STORES.DONGMYEONG
    setCurrentUser(userData)
    setPage(nextPage)
    setAuthMode('dashboard')

    const targetEndpoint =
      nextPage === STORES.HEAD_OFFICE ? ENDPOINTS.HQ_DASHBOARD : `/${nextPage}.aicafe`

    window.history.pushState({}, '', targetEndpoint)
  }

  const handleLogout = () => {
    setCurrentUser(null)
    setAuthMode('main')
    window.history.pushState({}, '', '/')
  }

  return {
    authMode,
    setAuthMode,
    authRole,
    setAuthRole,
    currentUser,
    setCurrentUser,
    handleLoginRoleChange,
    handleSignupRoleChange,
    handleGoToSignup,
    handleGoToLogin,
    handleLoginSuccess,
    handleLogout,
  }
}
