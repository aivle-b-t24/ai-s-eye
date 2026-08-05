import React, { useEffect, useState } from 'react'
import { ROLES } from '../../constants/auth'
import { API_BASE_URL } from '../../constants/env'
import { PrivacyPolicyBody } from '../legal/PrivacyPolicyModal'
import ReCaptcha from '../legal/ReCaptcha'
import LegalFooter from '../legal/LegalFooter'

// 개인정보 보호 가이드(접근통제 제4조⑧) 비밀번호 작성규칙과 동일한 클라이언트 검증.
function passwordPolicyError(pw) {
  let classes = 0
  if (/[a-z]/.test(pw)) classes += 1
  if (/[A-Z]/.test(pw)) classes += 1
  if (/[0-9]/.test(pw)) classes += 1
  if (/[^A-Za-z0-9]/.test(pw)) classes += 1
  if (classes >= 3 && pw.length >= 8) return ''
  if (classes >= 2 && pw.length >= 10) return ''
  return '비밀번호는 영문·숫자·특수문자 중 2종류 이상 조합 시 10자리 이상, 3종류 이상 조합 시 8자리 이상이어야 합니다.'
}

// 접근통제 제4조⑧-2: 추측하기 쉬운 비밀번호(연속·반복·아이디 유사) 차단.
function easyPasswordError(pw, idPart) {
  if (/(.)\1{3,}/.test(pw)) return '같은 문자를 4자 이상 반복할 수 없습니다.'
  const v = pw.toLowerCase()
  let up = 1
  let down = 1
  for (let i = 1; i < v.length; i += 1) {
    const delta = v.charCodeAt(i) - v.charCodeAt(i - 1)
    up = delta === 1 ? up + 1 : 1
    down = delta === -1 ? down + 1 : 1
    if (up >= 4 || down >= 4) return '연속된 숫자·문자(예: 1234, abcd)는 사용할 수 없습니다.'
  }
  if (idPart && idPart.length >= 3 && v.includes(idPart)) {
    return '아이디(이메일)와 비슷한 비밀번호는 사용할 수 없습니다.'
  }
  return ''
}

function BrandLogo({ className = '' }) {
  return (
    <span className={`signup-wordmark ${className}`}>
      <svg className="signup-logo-mark" width="26" height="26" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3 L21 20 H3 Z" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round" />
        <circle cx="12" cy="14" r="2.4" fill="currentColor" />
      </svg>
      AI&apos;s Eye
    </span>
  )
}

function StoreManagerGuide({ onGoToLogin }) {
  return (
    <>
      <div className="signup-form-head">
        <h2 className="signup-form-title">점주 계정 발급 안내</h2>
        <p className="signup-form-sub">점주 계정은 프랜차이즈 본사 관리자가 발급합니다.</p>
      </div>

      <div className="account-guide-steps">
        <div>
          <strong>1</strong>
          <span>본사 관리자가 로그인 이메일, 담당 매장, 초기 비밀번호를 등록합니다.</span>
        </div>
        <div>
          <strong>2</strong>
          <span>본사에서 발급받은 이메일과 초기 비밀번호를 확인합니다.</span>
        </div>
        <div>
          <strong>3</strong>
          <span>로그인 화면에 발급 정보를 입력해 매장 관제 화면에 접속합니다.</span>
        </div>
      </div>

      <button type="button" className="auth-submit-btn" onClick={onGoToLogin}>
        로그인 화면으로 돌아가기
      </button>
    </>
  )
}

function HqSignupForm({ onLogin, onGoToLogin }) {
  const [name, setName] = useState('')
  const [company, setCompany] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [agreePrivacy, setAgreePrivacy] = useState(false)
  const [recaptchaToken, setRecaptchaToken] = useState('')
  const [recaptchaReset, setRecaptchaReset] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setErrorMessage('')
    setSuccessMessage('')

    if (!name.trim()) return setErrorMessage('담당자명을 입력해 주세요.')
    if (!company.trim()) return setErrorMessage('회사(프랜차이즈)명을 입력해 주세요.')
    if (!email.trim()) return setErrorMessage('이메일을 입력해 주세요.')
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      return setErrorMessage('유효한 이메일 주소를 입력해 주세요.')
    }

    const pwError = passwordPolicyError(password)
    if (pwError) return setErrorMessage(pwError)
    const easyError = easyPasswordError(password, (email.split('@')[0] || '').trim().toLowerCase())
    if (easyError) return setErrorMessage(easyError)
    if (password !== passwordConfirm) return setErrorMessage('비밀번호가 일치하지 않습니다.')
    if (!agreePrivacy) return setErrorMessage('개인정보 수집·이용에 동의해 주세요.')
    if (!recaptchaToken) return setErrorMessage('reCAPTCHA 인증을 완료해 주세요.')

    const normalizedEmail = email.trim().toLowerCase()
    setIsSubmitting(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/signup/hq`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: normalizedEmail,
          name: name.trim(),
          company: company.trim(),
          password,
          agree_privacy: agreePrivacy,
          recaptcha_token: recaptchaToken,
        }),
      })

      if (!response.ok) {
        // 실패 시 reCAPTCHA 토큰은 소모되므로 위젯을 리셋해 재시도할 수 있게 한다.
        setRecaptchaToken('')
        setRecaptchaReset((k) => k + 1)
        const detail = await response.json().catch(() => null)
        const rawMessage = Array.isArray(detail?.detail)
          ? detail.detail[0]?.msg
          : detail?.detail
        const message = typeof rawMessage === 'string'
          ? rawMessage.replace(/^Value error,\s*/, '')
          : rawMessage
        throw new Error(message || `회원가입에 실패했습니다 (${response.status})`)
      }

      // 가입 즉시 로그인 (선택: 바로 로그인)
      try {
        await onLogin({ email: normalizedEmail, password, remember: false, role: ROLES.ADMIN })
      } catch (loginError) {
        setSuccessMessage('회원가입이 완료되었습니다. 로그인 화면에서 로그인해 주세요.')
        throw loginError
      }
    } catch (error) {
      if (!successMessage) {
        setErrorMessage(error.message || '회원가입에 실패했습니다.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <>
      <div className="signup-form-head">
        <h2 className="signup-form-title">본사 관리자 회원가입</h2>
        <p className="signup-form-sub">프랜차이즈 본사 관리자 계정을 직접 생성합니다.</p>
      </div>

      <form onSubmit={handleSubmit} className="auth-form" noValidate>
        <div className="signup-field-row">
          <div className="form-group">
            <label htmlFor="signup-name">담당자명</label>
            <input
              id="signup-name"
              type="text"
              autoComplete="name"
              placeholder="예: 박팀장"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isSubmitting}
            />
          </div>
          <div className="form-group">
            <label htmlFor="signup-company">회사(프랜차이즈)명</label>
            <input
              id="signup-company"
              type="text"
              autoComplete="organization"
              placeholder="예: 카페노아"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              disabled={isSubmitting}
            />
          </div>
        </div>

        <div className="form-group">
          <label htmlFor="signup-email">이메일</label>
          <input
            id="signup-email"
            type="email"
            autoComplete="username"
            placeholder="예: admin@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={isSubmitting}
          />
        </div>

        <div className="form-group">
          <label htmlFor="signup-password">비밀번호</label>
          <div className="password-input-wrapper">
            <input
              id="signup-password"
              type={showPassword ? 'text' : 'password'}
              autoComplete="new-password"
              placeholder="비밀번호를 입력하세요"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isSubmitting}
            />
            <button
              type="button"
              className="toggle-pw-btn"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
              title={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
            >
              {showPassword ? '🙈' : '👁'}
            </button>
          </div>
          <p className="pw-hint">
            영문·숫자·특수문자 중 2종류 이상은 10자리 이상, 3종류 이상은 8자리 이상으로 구성해 주세요.
            연속·반복 문자(1234, aaaa)나 아이디와 비슷한 비밀번호는 사용할 수 없습니다.
          </p>
        </div>

        <div className="form-group">
          <label htmlFor="signup-password-confirm">비밀번호 확인</label>
          <input
            id="signup-password-confirm"
            type={showPassword ? 'text' : 'password'}
            autoComplete="new-password"
            placeholder="비밀번호를 다시 입력하세요"
            value={passwordConfirm}
            onChange={(e) => setPasswordConfirm(e.target.value)}
            disabled={isSubmitting}
          />
        </div>

        <div className="signup-consent">
          <label className="checkbox-label consent-agree">
            <input
              type="checkbox"
              checked={agreePrivacy}
              onChange={(e) => setAgreePrivacy(e.target.checked)}
              disabled={isSubmitting}
            />
            <span>
              <strong>[필수]</strong> 개인정보 수집·이용에 동의합니다.
            </span>
          </label>

          <table className="consent-table">
            <tbody>
              <tr>
                <th>수집 목적</th>
                <td>본사 관리자 회원가입 및 관제 서비스 이용</td>
              </tr>
              <tr>
                <th>수집 항목</th>
                <td>이메일, 비밀번호, 담당자명, 회사명</td>
              </tr>
              <tr>
                <th>보유 기간</th>
                <td>회원 탈퇴 시까지 (관계 법령에 따른 보관 예외)</td>
              </tr>
            </tbody>
          </table>
          <p className="consent-note">
            동의를 거부할 권리가 있으며, 필수 항목에 동의하지 않으면 회원가입이 제한됩니다.
          </p>

          <details className="privacy-details">
            <summary>개인정보 처리방침 전문 보기</summary>
            <PrivacyPolicyBody />
          </details>
        </div>

        <div className="form-group">
          <span className="form-static-label">보안 확인</span>
          <ReCaptcha onChange={setRecaptchaToken} resetKey={recaptchaReset} />
          <p className="pw-hint">보안을 위해 비밀번호는 180일(약 6개월)마다 변경하시길 권장합니다.</p>
        </div>

        {errorMessage && (
          <div className="auth-error-alert inline-single-line clean-text-only">
            <span>{errorMessage}</span>
            <button
              type="button"
              className="error-dismiss-btn"
              onClick={() => setErrorMessage('')}
              aria-label="알림 지우기"
              title="알림 지우기"
            >
              ✕
            </button>
          </div>
        )}
        {successMessage && (
          <div className="auth-success-alert inline-single-line clean-text-only">
            <span>{successMessage}</span>
          </div>
        )}

        <button type="submit" className="auth-submit-btn" disabled={isSubmitting}>
          {isSubmitting ? '가입 처리 중...' : '회원가입하고 시작하기'}
        </button>

        <button
          type="button"
          className="auth-link auth-link-button signup-to-login"
          onClick={onGoToLogin}
          disabled={isSubmitting}
        >
          이미 계정이 있으신가요? 로그인
        </button>
      </form>
    </>
  )
}

export default function SignupPage({
  onClose,
  onGoToLogin,
  onLogin,
  onRoleChange,
  initialRole = ROLES.STORE_MANAGER,
}) {
  const [role, setRole] = useState(initialRole)

  useEffect(() => setRole(initialRole), [initialRole])

  const handleTabSwitch = (newRole) => {
    setRole(newRole)
    if (onRoleChange) onRoleChange(newRole)
  }

  const isAdmin = role === ROLES.ADMIN

  return (
    <div className="signup-page">
      <aside className="signup-brand">
        <div className="signup-brand-top">
          <BrandLogo />
        </div>
        <div className="signup-brand-body">
          <h1 className="signup-brand-title">매장을 한눈에,<br />본사는 가볍게.</h1>
          <p className="signup-brand-sub">
            프랜차이즈 관제 시스템 관리자 계정을 만들어 지금 바로 시작하세요.
          </p>
          <ul className="signup-brand-features">
            <li>실시간 혼잡도·대기 관제</li>
            <li>매장별 메뉴·정책 온보딩</li>
            <li>카카오 챗봇 고객 응대</li>
          </ul>
        </div>
        <div className="signup-brand-foot">© AI&apos;s Eye · AIVLE 24조</div>
      </aside>

      <main className="signup-form-panel">
        {onClose && (
          <button
            type="button"
            className="signup-home-link"
            onClick={onClose}
            aria-label="홈으로 이동"
            title="홈으로 이동"
          >
            홈으로 ✕
          </button>
        )}

        <div className="signup-form-scroll">
          <div className="signup-form-inner">
            <BrandLogo className="signup-wordmark-mobile" />

            <div className="role-switch-tabs signup-tabs">
              <button
                type="button"
                className={`role-tab ${role === ROLES.STORE_MANAGER ? 'active' : ''}`}
                onClick={() => handleTabSwitch(ROLES.STORE_MANAGER)}
              >
                점주 계정
              </button>
              <button
                type="button"
                className={`role-tab ${role === ROLES.ADMIN ? 'active' : ''}`}
                onClick={() => handleTabSwitch(ROLES.ADMIN)}
              >
                본사 관리자 가입
              </button>
            </div>

            {isAdmin ? (
              <HqSignupForm onLogin={onLogin} onGoToLogin={onGoToLogin} />
            ) : (
              <StoreManagerGuide onGoToLogin={onGoToLogin} />
            )}
          </div>
        </div>

        <LegalFooter className="signup-footer" />
      </main>
    </div>
  )
}
