import { useState, useEffect } from 'react'
import { ROLES, STORES, ENDPOINTS } from '../constants/auth'

export function useRouting(currentUser, authReady, setAuthMode, setAuthRole) {
  const [page, setPage] = useState(STORES.DONGMYEONG)

  useEffect(() => {
    const handleUrlRouting = () => {
      if (!authReady) return
      const pathname = window.location.pathname

      const redirectAuthenticatedUser = () => {
        if (!currentUser) return false
        const targetPage = currentUser.role === ROLES.ADMIN
          ? STORES.HEAD_OFFICE
          : currentUser.storeId || STORES.DONGMYEONG
        const targetEndpoint = targetPage === STORES.HEAD_OFFICE
          ? ENDPOINTS.HQ_DASHBOARD
          : `/${targetPage}.aicafe`
        setPage(targetPage)
        setAuthMode('dashboard')
        window.history.replaceState({}, '', targetEndpoint)
        return true
      }

      // 1. Role-based Signup Endpoints (/storesignup.aicafe, /hqsignup.aicafe)
      if (
        pathname === ENDPOINTS.STORE_SIGNUP ||
        pathname === '/storesignup' ||
        pathname === '/aicafe/storesignup'
      ) {
        if (redirectAuthenticatedUser()) return
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
        if (redirectAuthenticatedUser()) return
        setAuthMode('signup')
        setAuthRole(ROLES.ADMIN)
        if (pathname !== ENDPOINTS.HQ_SIGNUP) {
          window.history.replaceState({}, '', ENDPOINTS.HQ_SIGNUP)
        }
        return
      }

      if (
        pathname === '/signup.aicafe' ||
        pathname === '/signup' ||
        pathname === '/aicafe/signup'
      ) {
        if (redirectAuthenticatedUser()) return
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
        if (redirectAuthenticatedUser()) return
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
        if (redirectAuthenticatedUser()) return
        setAuthMode('login')
        setAuthRole(ROLES.ADMIN)
        if (pathname !== ENDPOINTS.HQ_LOGIN) {
          window.history.replaceState({}, '', ENDPOINTS.HQ_LOGIN)
        }
        return
      }

      if (
        pathname === '/login.aicafe' ||
        pathname === '/aicafe/login'
      ) {
        if (redirectAuthenticatedUser()) return
        setAuthMode('login')
        setAuthRole(ROLES.STORE_MANAGER)
        window.history.replaceState({}, '', ENDPOINTS.STORE_LOGIN)
        return
      }

      if (
        pathname === '/' ||
        pathname === '' ||
        pathname === '/main' ||
        pathname === '/main.aicafe'
      ) {
        setAuthMode('main')
        return
      }

      // 3. Strict Auth Guard: If not logged in during this active React session
      if (!currentUser) {
        setAuthMode('main')
        return
      }

      // 4. Role-Based Authorization Guard & Endpoint Parsing
      if (
        pathname === ENDPOINTS.HQ_DASHBOARD ||
        pathname === '/aicafe/hq' ||
        pathname === '/hq'
      ) {
        if (
          currentUser.role !== ROLES.ADMIN &&
          currentUser.storeId !== STORES.HEAD_OFFICE
        ) {
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
        if (
          currentUser.role === ROLES.STORE_MANAGER
          && storeId !== currentUser.storeId
        ) {
          const userStore = currentUser.storeId || STORES.DONGMYEONG
          setPage(userStore)
          setAuthMode('dashboard')
          window.history.replaceState({}, '', `/${userStore}.aicafe`)
          return
        }
        setPage(storeId || STORES.DONGMYEONG)
        setAuthMode('dashboard')
      } else if (pathname.startsWith('/aicafe/store/')) {
        const storeId = pathname.replace('/aicafe/store/', '')
        if (currentUser.role === ROLES.STORE_MANAGER && storeId !== currentUser.storeId) {
          const userStore = currentUser.storeId || STORES.DONGMYEONG
          setPage(userStore)
          setAuthMode('dashboard')
          window.history.replaceState({}, '', `/${userStore}.aicafe`)
          return
        }
        setPage(storeId || STORES.DONGMYEONG)
        setAuthMode('dashboard')
        window.history.replaceState({}, '', `/${storeId || STORES.DONGMYEONG}.aicafe`)
      } else if (pathname.startsWith('/store/')) {
        const storeId = pathname.replace('/store/', '')
        if (currentUser.role === ROLES.STORE_MANAGER && storeId !== currentUser.storeId) {
          const userStore = currentUser.storeId || STORES.DONGMYEONG
          setPage(userStore)
          setAuthMode('dashboard')
          window.history.replaceState({}, '', `/${userStore}.aicafe`)
          return
        }
        setPage(storeId || STORES.DONGMYEONG)
        setAuthMode('dashboard')
        window.history.replaceState({}, '', `/${storeId || STORES.DONGMYEONG}.aicafe`)
      } else {
        setAuthMode('main')
      }
    }

    handleUrlRouting()
    window.addEventListener('popstate', handleUrlRouting)
    return () => window.removeEventListener('popstate', handleUrlRouting)
  }, [authReady, currentUser, setAuthMode, setAuthRole])

  return {
    page,
    setPage,
  }
}
