import { ROLES, STORES } from '../constants/auth.js'

export const LOCAL_SESSION_KEY = 'aicafe.localSession'

export const LOCAL_DEMO_ACCOUNTS = Object.freeze({
  [STORES.DONGMYEONG]: Object.freeze({
    email: 'owner01@local.test',
    password: '1234',
    role: ROLES.STORE_MANAGER,
    profile: Object.freeze({
      uid: 'local-owner-001',
      id: 'owner01',
      email: 'owner01@local.test',
      name: '동명점 점주',
      role: ROLES.STORE_MANAGER,
      storeId: STORES.DONGMYEONG,
      storeName: '동명점',
    }),
  }),
  [STORES.SUWAN]: Object.freeze({
    email: 'owner02@local.test',
    password: '1234',
    role: ROLES.STORE_MANAGER,
    profile: Object.freeze({
      uid: 'local-owner-002',
      id: 'owner02',
      email: 'owner02@local.test',
      name: '수완점 점주',
      role: ROLES.STORE_MANAGER,
      storeId: STORES.SUWAN,
      storeName: '수완점',
    }),
  }),
  [STORES.HEAD_OFFICE]: Object.freeze({
    email: 'admin@local.test',
    password: '1234',
    role: ROLES.ADMIN,
    profile: Object.freeze({
      uid: 'local-admin',
      id: 'admin',
      email: 'admin@local.test',
      name: '로컬 본사 관리자',
      role: ROLES.ADMIN,
      storeId: STORES.HEAD_OFFICE,
      storeName: '본사',
    }),
  }),
})

export function authenticateLocalAccount(email, password, requestedRole) {
  const normalizedEmail = String(email ?? '').trim().toLowerCase()
  const account = Object.values(LOCAL_DEMO_ACCOUNTS).find(
    (candidate) => candidate.email === normalizedEmail,
  )

  if (!account || account.password !== password) {
    throw new Error('이메일 또는 비밀번호가 올바르지 않습니다.')
  }
  if (requestedRole && account.role !== requestedRole) {
    throw new Error(
      requestedRole === ROLES.ADMIN
        ? '본사 관리자 권한이 없는 계정입니다.'
        : '점주 권한이 없는 계정입니다.',
    )
  }

  const profile = { ...account.profile }
  if (!profile.storeName) {
    profile.storeName = profile.storeId === STORES.DONGMYEONG
      ? '동명점'
      : profile.storeId === STORES.SUWAN
        ? '수완점'
        : profile.storeId
  }
  return profile
}
