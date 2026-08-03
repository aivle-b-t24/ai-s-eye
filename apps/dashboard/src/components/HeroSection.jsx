import React, { useState } from 'react'
import { ROLES, STORES, DEMO_CREDENTIALS } from '../constants/auth'

function HeroSection({ page, authMode, dashboard, onMenuOpen, onLogin, onSignup, onLoginSuccess }) {
  const [isStoreSubmenuOpen, setIsStoreSubmenuOpen] = useState(false)
  const isHeadOffice = page === 'head-office'
  const isSettings = page === 'setting' || page === 'settings' || page === 'kos'
  const isAuthPage = authMode === 'login' || authMode === 'signup'
  const isMainLanding = authMode === 'main'

  const peopleCount = dashboard?.state?.visible_person_count ?? 8

  const handleDemoLogin = (selectedRole, targetStoreId = STORES.DONGMYEONG) => {
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
                      매장 1 (동명점)
                    </button>
                    <button
                      type="button"
                      className="store-sub-option"
                      onClick={() => {
                        setIsStoreSubmenuOpen(false)
                        handleDemoLogin(ROLES.STORE_MANAGER, STORES.SUWAN)
                      }}
                    >
                      매장 2 (수완점)
                    </button>
                  </div>
                )}
              </div>

<<<<<<< HEAD
              <button
                type="button"
                className="demo-btn admin-demo"
                onClick={() => handleDemoLogin(ROLES.ADMIN, STORES.HEAD_OFFICE)}
              >
                [본사 관리자] 로그인
              </button>
=======
            </div>

            <div className="hero-visual">
              <div className="camera-window">
                <div className="camera-toolbar">
                  <div className="camera-live">
                    <span />
                    CAM 01 · LIVE
                  </div>

                  <div className="camera-time">
                    실시간 AI 분석
                  </div>
                </div>

                <div className="detection-box detection-box-one">
                  <span>PERSON 01</span>
                </div>

                <div className="detection-box detection-box-two">
                  <span>PERSON 02</span>
                </div>

                <div className="detection-box detection-box-three">
                  <span>WAITING</span>
                </div>

                <div className="camera-bottom-label">
                  <span>{isHeadOffice ? 'SUPERVISOR CONTROL MODE' : 'AI OBJECT DETECTION'}</span>
                  <strong className={hideMetrics ? 'is-hidden' : ''}>고객 {peopleCount}명 감지</strong>
                </div>
              </div>

              <div className={`hero-metrics-row ${hideMetrics ? 'is-hidden' : ''}`}>
                <div className="hero-inline-metric">
                  <div className="hero-inline-title">
                    <span className="metric-icon">●</span>
                    현재 혼잡도
                  </div>

                  <div className="hero-inline-value">
                    <strong>{congestionRate}%</strong>
                    <span>{congestionLabel}</span>
                  </div>
                </div>

                <div className="hero-metric-divider" />

                <div className="hero-inline-metric">
                  <div className="hero-inline-title">
                    <span className="metric-icon">◷</span>
                    대기 현황
                  </div>

                  <div className="hero-inline-value">
                    <strong>{queueCount}팀</strong>
                    <span>예상 대기 {waitMinutes}분</span>
                  </div>
                </div>
              </div>

>>>>>>> ab4234838ba6cc48272fc55366fd0700a8a764a1
            </div>
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

      <footer className="main-landing-footer">
        <span>개인정보 처리방침</span> | <span>이용약관</span> | <span>© 2026 AI's Eye. All rights reserved.</span>
      </footer>
    </section>
  )
}

export default HeroSection
