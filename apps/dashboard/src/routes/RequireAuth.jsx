import { Navigate, useLocation } from 'react-router-dom'

import { useAuthContext } from '../auth/AuthContext'
import { ROLES } from '../constants/auth'
import { ROUTES } from '../constants/routes'

export default function RequireAuth({
  children,
  roles,
  loginPath = ROUTES.HOME,
}) {
  const { authReady, currentUser } = useAuthContext()
  const location = useLocation()

  if (!authReady) {
    return <div className="route-loading" aria-live="polite">인증 확인 중…</div>
  }

  if (!currentUser) {
    return <Navigate to={loginPath} replace state={{ from: location.pathname }} />
  }

  if (roles?.length && !roles.includes(currentUser.role)) {
    const fallback = currentUser.role === ROLES.ADMIN ? ROUTES.HQ : ROUTES.DASHBOARD
    return <Navigate to={fallback} replace />
  }

  return children
}
