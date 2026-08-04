/** React Router 경로. 점주 화면은 공용 경로 + 세션 storeId로 구분한다. */
export const ROUTES = Object.freeze({
  HOME: '/',
  STORE_LOGIN: '/storelogin.aicafe',
  HQ_LOGIN: '/hqlogin.aicafe',
  STORE_SIGNUP: '/storesignup.aicafe',
  HQ_SIGNUP: '/hqsignup.aicafe',
  HQ: '/hq',
  DASHBOARD: '/dashboard',
  MENUS: '/menus',
  SETTINGS: '/settings',
})

/** 예전 북마크/링크 호환용 */
export const LEGACY_ROUTES = Object.freeze({
  HQ_AICAFE: '/hq.aicafe',
  KOS: '/kos',
})

export function homeForUser(user) {
  if (!user) return ROUTES.HOME
  if (user.role === 'admin' || user.storeId === 'head-office') return ROUTES.HQ
  return ROUTES.DASHBOARD
}

export function pageFromPathname(pathname) {
  if (
    pathname === ROUTES.HQ
    || pathname === LEGACY_ROUTES.HQ_AICAFE
    || pathname === '/aicafe/hq'
  ) {
    return 'head-office'
  }
  if (pathname === ROUTES.MENUS || pathname === LEGACY_ROUTES.KOS) return 'kos'
  if (pathname === ROUTES.SETTINGS) return 'setting'
  if (pathname === ROUTES.DASHBOARD) return 'dashboard'
  if (pathname.endsWith('.aicafe') && pathname.includes('store-')) {
    return pathname.replace(/^\//, '').replace(/\.aicafe$/, '')
  }
  return 'dashboard'
}
