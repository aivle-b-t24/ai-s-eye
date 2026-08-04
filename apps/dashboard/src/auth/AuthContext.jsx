import { createContext, useContext } from 'react'

import { useAuth as useAuthState } from '../hooks/useAuth'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const auth = useAuthState()
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>
}

export function useAuthContext() {
  const value = useContext(AuthContext)
  if (!value) {
    throw new Error('useAuthContext는 AuthProvider 안에서만 사용할 수 있습니다.')
  }
  return value
}
