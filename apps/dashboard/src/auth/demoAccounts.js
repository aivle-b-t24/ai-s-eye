import { ROLES, STORES } from '../constants/auth'
import { LOCAL_DEMO_ACCOUNTS } from './localAuth'
import { IS_LOCAL_AUTH_MODE } from './runtimeAuth'

const FIREBASE_DEMO_LOGIN_ENABLED =
  String(import.meta.env.VITE_ENABLE_DEMO_LOGIN ?? 'false').toLowerCase() === 'true'

const FIREBASE_DEMO_ACCOUNTS = Object.freeze({
  [STORES.DONGMYEONG]: Object.freeze({
    email: import.meta.env.VITE_DEMO_STORE_001_EMAIL,
    password: import.meta.env.VITE_DEMO_STORE_001_PASSWORD,
    role: ROLES.STORE_MANAGER,
  }),
  [STORES.SUWAN]: Object.freeze({
    email: import.meta.env.VITE_DEMO_STORE_002_EMAIL,
    password: import.meta.env.VITE_DEMO_STORE_002_PASSWORD,
    role: ROLES.STORE_MANAGER,
  }),
  [STORES.HEAD_OFFICE]: Object.freeze({
    email: import.meta.env.VITE_DEMO_ADMIN_EMAIL,
    password: import.meta.env.VITE_DEMO_ADMIN_PASSWORD,
    role: ROLES.ADMIN,
  }),
})

function hasCredentials(account) {
  return Boolean(account?.email && account?.password)
}

/** 로컬 모드이거나 Firebase 데모 계정이 env에 있을 때 실제 로그인 경로를 쓴다. */
export function usesCredentialDemoLogin() {
  if (IS_LOCAL_AUTH_MODE) return true
  return FIREBASE_DEMO_LOGIN_ENABLED
}

export function getDemoAccount(storeId) {
  if (IS_LOCAL_AUTH_MODE) {
    return LOCAL_DEMO_ACCOUNTS[storeId] ?? null
  }
  if (!FIREBASE_DEMO_LOGIN_ENABLED) {
    return null
  }
  const account = FIREBASE_DEMO_ACCOUNTS[storeId]
  return hasCredentials(account) ? account : null
}
