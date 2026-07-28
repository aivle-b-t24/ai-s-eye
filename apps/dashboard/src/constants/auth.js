// Central Authentication, Roles, and Store Identifiers
export const ROLES = Object.freeze({
  STORE_MANAGER: 'store_manager',
  ADMIN: 'admin',
})

export const STORES = Object.freeze({
  DONGMYEONG: 'store-001',
  SUWAN: 'store-002',
  HEAD_OFFICE: 'head-office',
})

export const ENDPOINTS = Object.freeze({
  STORE_LOGIN: '/storelogin.aicafe',
  HQ_LOGIN: '/hqlogin.aicafe',
  STORE_SIGNUP: '/storesignup.aicafe',
  HQ_SIGNUP: '/hqsignup.aicafe',
  HQ_DASHBOARD: '/hq.aicafe',
  STORE_001_DASHBOARD: '/store-001.aicafe',
  STORE_002_DASHBOARD: '/store-002.aicafe',
})

export const DEFAULT_STORE_DATA = Object.freeze({
  [STORES.DONGMYEONG]: {
    state: null,
    eta: null,
    menus: [],
    policies: [],
  },
  [STORES.SUWAN]: {
    state: null,
    eta: null,
    menus: [],
    policies: [],
  },
})

export const DEMO_CREDENTIALS = Object.freeze({
  [STORES.DONGMYEONG]: {
    id: 'owner01',
    name: '김점주 점주님',
    role: ROLES.STORE_MANAGER,
    storeId: STORES.DONGMYEONG,
  },
  [STORES.SUWAN]: {
    id: 'owner02',
    name: '이점주 점주님',
    role: ROLES.STORE_MANAGER,
    storeId: STORES.SUWAN,
  },
  [STORES.HEAD_OFFICE]: {
    id: 'admin01',
    name: '박팀장 슈퍼바이저님',
    role: ROLES.ADMIN,
    storeId: STORES.HEAD_OFFICE,
  },
})
