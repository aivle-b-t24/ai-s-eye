import assert from 'node:assert/strict'
import test from 'node:test'

import { ROLES, STORES } from '../constants/auth.js'
import { authenticateLocalAccount, LOCAL_DEMO_ACCOUNTS } from './localAuth.js'

test('로컬 개발 계정은 역할과 매장 프로필로 로그인한다', () => {
  const store = LOCAL_DEMO_ACCOUNTS[STORES.DONGMYEONG]
  const profile = authenticateLocalAccount(store.email, store.password, ROLES.STORE_MANAGER)

  assert.equal(profile.role, ROLES.STORE_MANAGER)
  assert.equal(profile.storeId, STORES.DONGMYEONG)
})

test('로컬 개발 계정은 잘못된 비밀번호를 거부한다', () => {
  const store = LOCAL_DEMO_ACCOUNTS[STORES.DONGMYEONG]

  assert.throws(
    () => authenticateLocalAccount(store.email, 'wrong-password', ROLES.STORE_MANAGER),
    /올바르지 않습니다/,
  )
})

test('로컬 개발 계정은 요청한 역할과 다른 계정을 거부한다', () => {
  const admin = LOCAL_DEMO_ACCOUNTS[STORES.HEAD_OFFICE]

  assert.throws(
    () => authenticateLocalAccount(admin.email, admin.password, ROLES.STORE_MANAGER),
    /점주 권한이 없는 계정/,
  )
})
