// 개인정보 표시 제한(개인정보의 기술적·관리적 보호조치 기준 제10조) — 조회·출력 시 마스킹.

/**
 * 이메일을 abc****@domain.com 형태로 마스킹한다.
 * 로컬파트 앞 2글자만 남기고 나머지는 *로 가린다(도메인은 그대로).
 */
export function maskEmail(email) {
  if (typeof email !== 'string' || !email.includes('@')) return email ?? ''
  const [local, domain] = email.split('@')
  const head = local.slice(0, 2)
  const stars = '*'.repeat(Math.max(2, local.length - head.length))
  return `${head}${stars}@${domain}`
}
