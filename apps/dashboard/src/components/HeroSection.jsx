import React, { useState } from 'react'
import { getDemoAccount, usesCredentialDemoLogin } from '../auth/demoAccounts'
import { ROLES, STORES, DEMO_CREDENTIALS } from '../constants/auth'
import LegalFooter from './legal/LegalFooter'

function HeroSection({
  page,
  authMode,
  dashboard,
  _onMenuOpen,
  onLogin,
  onSignup,
  onLoginSuccess,
  onCredentialLogin,
}) {
  const [isStoreSubmenuOpen, setIsStoreSubmenuOpen] = useState(false)
  const [demoError, setDemoError] = useState('')
  const [demoSubmitting, setDemoSubmitting] = useState(false)
  const _isHeadOffice = page === 'head-office'
  const _isSettings = page === 'setting' || page === 'settings' || page === 'kos'
  const isAuthPage = authMode === 'login' || authMode === 'signup'
  const isMainLanding = authMode === 'main'
  /* =========================================================================
     [첫 번째 충돌 구역: 둘 다 병합]
     도훈님 코드 (단 1글자도 변경 없이 100% 원문 보존) + 점주님 로그인 함수
     ========================================================================= */
  const peopleCount = dashboard?.state?.visible_person_count ?? 0
  // 대기 팀 = 진행 중 주문 건수(backlog). 주문 1건 ≈ 한 팀(그룹). 없으면 비전 추정치.
  const _waitingTeams =
    dashboard?.eta?.waiting_order_count ??
    dashboard?.state?.queue_count_estimate ??
    0
  const _waitMinutes = dashboard?.eta?.estimated_wait_minutes ?? 0
  // 수용 인원은 설정 페이지에서 저장한 매장별 값. 없으면 기본 30명.
  const maxCapacity = dashboard?.settings?.max_capacity ?? 30
  const _congestionRate = Math.min(
    Math.round((peopleCount / maxCapacity) * 100),
    100
  )

  const enterWithDemoProfile = (selectedRole, targetStoreId) => {
    const credKey = selectedRole === ROLES.STORE_MANAGER ? targetStoreId : STORES.HEAD_OFFICE
    const creds = DEMO_CREDENTIALS[credKey] || DEMO_CREDENTIALS[STORES.DONGMYEONG]
    if (onLoginSuccess) {
      onLoginSuccess({
        id: creds.id,
        name: creds.name,
        role: creds.role,
        storeId: creds.storeId,
      })
    }
  }

  const handleDemoLogin = async (selectedRole, targetStoreId = STORES.DONGMYEONG) => {
    const credKey = selectedRole === ROLES.STORE_MANAGER ? targetStoreId : STORES.HEAD_OFFICE
    setDemoError('')

    // Firebase/로컬 데모 계정이 설정돼 있으면 실제 로그인, 아니면 기존 원클릭(비연결) 유지
    if (usesCredentialDemoLogin() && onCredentialLogin) {
      const account = getDemoAccount(credKey)
      if (account?.email && account?.password) {
        setDemoSubmitting(true)
        try {
          await onCredentialLogin({
            email: account.email,
            password: account.password,
            remember: false,
            role: account.role,
          })
        } catch (error) {
          setDemoError(error.message || '빠른 로그인에 실패했습니다.')
        } finally {
          setDemoSubmitting(false)
        }
        return
      }
    }

    enterWithDemoProfile(selectedRole, targetStoreId)
  }
  return (
    <section className={`hero-section ${isAuthPage ? 'is-auth-page' : ''} ${isMainLanding ? 'main-landing-hero' : ''}`}>
      <div className="hero-background" />
      <div className="hero-gradient" />

      <header className="hero-header main-landing-header">
        <a className="hero-brand" href="#top">
          <span>
            <small>AI MONITORING SYSTEM</small>
            <strong>Al's Eye</strong>
          </span>
        </a>
        <div className="landing-auth-buttons">
          <button
            type="button"
            className="landing-login-btn"
            onClick={onLogin}
          >
            로그인
          </button>
          <button
            type="button"
            className="landing-signup-btn"
            onClick={onSignup}
          >
            회원가입
          </button>
        </div>
      </header>

      <div className="hero-layout main-landing-layout">
        <div className="hero-copy main-landing-copy">
          <p className="hero-kicker">INTELLIGENT STORE OPERATIONS</p>
          <h1 className="landing-main-title">
            Al's eye
          </h1>
          <p className="hero-korean-subtitle">
            AI기반 프랜차이즈 매장 운영 지원 플랫폼
          </p>
          <div className="landing-demo-login-box">
            <p className="demo-hint">[빠른 체험용 원클릭 로그인]</p>
            <div className="demo-btn-group">
              <div className="store-sub-wrapper">
                <button
                  type="button"
                  className="demo-btn store-demo with-arrow-btn"
                  onClick={() => setIsStoreSubmenuOpen(!isStoreSubmenuOpen)}
                  aria-expanded={isStoreSubmenuOpen}
                  disabled={demoSubmitting}
                >
                  <span>[점주] 로그인</span>
                  <span className={`dropdown-arrow-icon ${isStoreSubmenuOpen ? 'open' : ''}`} aria-hidden="true">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </span>
                </button>
                {isStoreSubmenuOpen && (
                  <div className="store-sub-dropdown-menu">
                    <button
                      type="button"
                      className="store-sub-option"
                      onClick={() => {
                        setIsStoreSubmenuOpen(false)
                        handleDemoLogin(ROLES.STORE_MANAGER, STORES.DONGMYEONG)
                      }}
                    >
                      데모 점주 ({STORES.DONGMYEONG})
                    </button>
                    <button
                      type="button"
                      className="store-sub-option"
                      onClick={() => {
                        setIsStoreSubmenuOpen(false)
                        handleDemoLogin(ROLES.STORE_MANAGER, STORES.SUWAN)
                      }}
                    >
                      데모 점주 ({STORES.SUWAN})
                    </button>
                  </div>
                )}
              </div>
              <button
                type="button"
                className="demo-btn admin-demo"
                onClick={() => handleDemoLogin(ROLES.ADMIN, STORES.HEAD_OFFICE)}
                disabled={demoSubmitting}
              >
                {demoSubmitting ? '로그인 중…' : '[본사 관리자] 로그인'}
              </button>
            </div>
            {demoError && (
              <p className="demo-login-error" role="alert">{demoError}</p>
            )}
          </div>
        </div>
        <div className="hero-visual main-landing-visual">
          <div className="camera-window landing-camera-card">
            <div className="camera-toolbar">
              <div className="camera-live">
                <span className="live-dot" />
                CAM 01 · LIVE
              </div>
            </div>
            {/* =========================================================
               [두 번째 충돌 구역: 현재 변경 사항 수락 (Accept Current Change)]
               ========================================================= */}
            <div className="detection-box detection-box-waiting">
              <span className="box-tag tag-waiting">WAITING</span>
            </div>
            <div className="detection-box detection-box-person1">
              <span className="box-tag tag-person">PERSON 02</span>
            </div>
            <div className="detection-box detection-box-person2">
              <span className="box-tag tag-person">PERSON 01</span>
            </div>
          </div>
        </div>
      </div>
      <LegalFooter className="main-landing-footer" />
    </section>
  )
}
export default HeroSection