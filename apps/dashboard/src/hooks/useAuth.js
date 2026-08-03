import { useEffect, useState } from 'react'
import {
  browserLocalPersistence,
  browserSessionPersistence,
  onAuthStateChanged,
  sendPasswordResetEmail,
  setPersistence,
  signInWithEmailAndPassword,
  signOut,
} from 'firebase/auth'

import { authenticatedFetch } from '../api/authenticatedFetch'
import { IS_LOCAL_AUTH_MODE } from '../auth/runtimeAuth'
import {
  authenticateLocalAccount,
  LOCAL_SESSION_KEY,
} from '../auth/localAuth'
import { API_BASE_URL } from '../constants/env'
import { ROLES, STORES, ENDPOINTS } from '../constants/auth'
import { firebaseAuth } from '../firebase'

function loginErrorMessage(error) {
  const code = error?.code ?? ''
  if (
    code === 'auth/invalid-credential'
    || code === 'auth/invalid-email'
    || code === 'auth/user-not-found'
    || code === 'auth/wrong-password'
  ) {
    return '이메일 또는 비밀번호가 올바르지 않습니다.'
  }
  if (code === 'auth/too-many-requests') {
    return '로그인 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요.'
  }
  if (code === 'auth/network-request-failed') {
    return '인증 서버에 연결할 수 없습니다. 네트워크를 확인해 주세요.'
  }
  return error?.message || '로그인에 실패했습니다.'
}

async function loadProfile() {
  const response = await authenticatedFetch(`${API_BASE_URL}/api/auth/me`)
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? `사용자 권한 확인 실패 (${response.status})`)
  }
  return response.json()
}

function loadLocalSession() {
  const serialized = (
    window.sessionStorage.getItem(LOCAL_SESSION_KEY)
    ?? window.localStorage.getItem(LOCAL_SESSION_KEY)
  )
  if (!serialized) return null
  try {
    return JSON.parse(serialized)
  } catch {
    window.sessionStorage.removeItem(LOCAL_SESSION_KEY)
    window.localStorage.removeItem(LOCAL_SESSION_KEY)
    return null
  }
}

function saveLocalSession(profile, remember) {
  const serialized = JSON.stringify(profile)
  window.sessionStorage.removeItem(LOCAL_SESSION_KEY)
  window.localStorage.removeItem(LOCAL_SESSION_KEY)
  const storage = remember ? window.localStorage : window.sessionStorage
  storage.setItem(LOCAL_SESSION_KEY, serialized)
}

function clearLocalSession() {
  window.sessionStorage.removeItem(LOCAL_SESSION_KEY)
  window.localStorage.removeItem(LOCAL_SESSION_KEY)
}

export function useAuth() {
  const [authMode, setAuthMode] = useState('loading')
  const [authRole, setAuthRole] = useState(ROLES.STORE_MANAGER)
  const [currentUser, setCurrentUser] = useState(null)
  const [authReady, setAuthReady] = useState(false)
  const [authError, setAuthError] = useState('')

  useEffect(() => {
    if (IS_LOCAL_AUTH_MODE) {
      const profile = loadLocalSession()
      if (profile) {
        setCurrentUser(profile)
        setAuthRole(profile.role)
        setAuthMode('dashboard')
      } else {
        setAuthMode('login')
      }
      setAuthReady(true)
      return undefined
    }

    return onAuthStateChanged(firebaseAuth, async (firebaseUser) => {
      if (!firebaseUser) {
        setCurrentUser(null)
        setAuthMode((mode) => (mode === 'signup' ? mode : 'login'))
        setAuthReady(true)
        return
      }

      try {
        const profile = await loadProfile()
        setCurrentUser(profile)
        setAuthRole(profile.role)
        setAuthMode('dashboard')
        setAuthError('')
      } catch (error) {
        setCurrentUser(null)
        setAuthMode('login')
        setAuthError(error.message)
        await signOut(firebaseAuth)
      } finally {
        setAuthReady(true)
      }
    })
  }, [])

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

  const handleLogin = async ({ email, password, remember, role }, setPage) => {
    setAuthError('')
    try {
      const requestedRole = role ?? authRole
      if (IS_LOCAL_AUTH_MODE) {
        const profile = authenticateLocalAccount(email, password, requestedRole)
        saveLocalSession(profile, remember)
        handleLoginSuccess(profile, setPage)
        return profile
      }

      await setPersistence(
        firebaseAuth,
        remember ? browserLocalPersistence : browserSessionPersistence,
      )
      await signInWithEmailAndPassword(firebaseAuth, email, password)
      const profile = await loadProfile()
      if (profile.role !== requestedRole) {
        await signOut(firebaseAuth)
        throw new Error(
          requestedRole === ROLES.ADMIN
            ? '본사 관리자 권한이 없는 계정입니다.'
            : '점주 권한이 없는 계정입니다.',
        )
      }
      handleLoginSuccess(profile, setPage)
      return profile
    } catch (error) {
      const message = loginErrorMessage(error)
      setAuthError(message)
      throw new Error(message)
    }
  }

  const handleLogout = async () => {
    if (IS_LOCAL_AUTH_MODE) {
      clearLocalSession()
    } else {
      await signOut(firebaseAuth)
    }
    setCurrentUser(null)
    setAuthMode('login')
    window.history.pushState({}, '', ENDPOINTS.STORE_LOGIN)
  }

  const handlePasswordReset = async (email) => {
    if (IS_LOCAL_AUTH_MODE) {
      throw new Error('로컬 개발 계정은 빠른 로그인 버튼을 사용해 주세요.')
    }
    const normalizedEmail = email.trim().toLowerCase()
    if (!normalizedEmail) {
      throw new Error('비밀번호를 설정할 이메일을 입력해 주세요.')
    }
    try {
      await sendPasswordResetEmail(firebaseAuth, normalizedEmail)
    } catch (error) {
      if (error?.code === 'auth/invalid-email') {
        throw new Error('유효한 이메일을 입력해 주세요.')
      }
      if (error?.code === 'auth/too-many-requests') {
        throw new Error('요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.')
      }
      throw new Error('비밀번호 설정 메일을 보내지 못했습니다.')
    }
  }

  return {
    authMode,
    setAuthMode,
    authRole,
    setAuthRole,
    currentUser,
    setCurrentUser,
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
  }
}
