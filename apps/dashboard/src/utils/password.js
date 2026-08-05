// 비밀번호 유효기간(접근통제 제4조⑧ — 반기별 1회 변경 권고) 관련 유틸.

export const PASSWORD_VALIDITY_DAYS = 180
const DAY_MS = 24 * 60 * 60 * 1000

/**
 * password_changed_at(ISO 문자열) 기준으로 유효기간이 지났는지 판단한다.
 * 값이 없으면(과거 계정 등) 판단 불가로 보고 false를 반환한다.
 */
export function isPasswordExpired(changedAtIso, now = Date.now()) {
  if (!changedAtIso) return false
  const changed = Date.parse(changedAtIso)
  if (Number.isNaN(changed)) return false
  return now - changed > PASSWORD_VALIDITY_DAYS * DAY_MS
}

/** 유효기간 만료까지 남은 일수(음수면 만료). 값 없으면 null. */
export function daysUntilPasswordExpiry(changedAtIso, now = Date.now()) {
  if (!changedAtIso) return null
  const changed = Date.parse(changedAtIso)
  if (Number.isNaN(changed)) return null
  const elapsedDays = (now - changed) / DAY_MS
  return Math.ceil(PASSWORD_VALIDITY_DAYS - elapsedDays)
}
