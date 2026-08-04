import { Navigate, Outlet, useOutletContext } from 'react-router-dom'

import { ROUTES } from '../constants/routes'

/** 미설정 매장은 대시보드/메뉴 대신 온보딩으로 보낸다. */
export default function RequireStoreSetup() {
  const context = useOutletContext()
  const { setupReady, needsOnboarding } = context ?? {}

  if (!setupReady) {
    return (
      <div className="route-loading" aria-live="polite">
        매장 설정 확인 중…
      </div>
    )
  }

  if (needsOnboarding) {
    return <Navigate to={ROUTES.ONBOARDING} replace />
  }

  return <Outlet context={context} />
}
