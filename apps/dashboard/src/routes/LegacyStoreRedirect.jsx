import { Navigate, useParams } from 'react-router-dom'

import { useAuthContext } from '../auth/AuthContext'
import { ROLES } from '../constants/auth'
import { ROUTES, homeForUser } from '../constants/routes'

/** `/store-003.aicafe` 같은 예전 매장 URL → 공용 /dashboard */
export default function LegacyStoreRedirect() {
  const { storeFile } = useParams()
  const { currentUser, authReady } = useAuthContext()
  const slug = String(storeFile || '')

  if (!/^store-\d+\.aicafe$/i.test(slug)) {
    return <Navigate to={ROUTES.HOME} replace />
  }

  if (!authReady) {
    return <div className="route-loading" aria-live="polite">인증 확인 중…</div>
  }

  if (!currentUser) {
    return <Navigate to={ROUTES.STORE_LOGIN} replace />
  }

  if (currentUser.role === ROLES.ADMIN) {
    return <Navigate to={ROUTES.HQ} replace />
  }

  const requestedStoreId = slug.replace(/\.aicafe$/i, '')
  if (
    currentUser.storeId
    && requestedStoreId
    && requestedStoreId !== currentUser.storeId
  ) {
    return <Navigate to={homeForUser(currentUser)} replace />
  }

  return <Navigate to={ROUTES.DASHBOARD} replace />
}
