function HeroSection({ page, authMode, dashboard, onMenuOpen }) {
  const isHeadOffice = page === 'head-office'
  const isSettings = page === 'setting' || page === 'settings'
  const isAuthPage = authMode === 'login' || authMode === 'signup'
  const hideMetrics = isHeadOffice || isSettings || isAuthPage


  const peopleCount = dashboard?.state?.visible_person_count ?? 0
  // 대기 팀 = 진행 중 주문 건수(backlog). 주문 1건 ≈ 한 팀(그룹). 없으면 비전 추정치.
  const waitingTeams =
    dashboard?.eta?.waiting_order_count ??
    dashboard?.state?.queue_count_estimate ??
    0
  const waitMinutes = dashboard?.eta?.estimated_wait_minutes ?? 0

  // 수용 인원은 설정 페이지에서 저장한 매장별 값. 없으면 기본 30명.
  const maxCapacity = dashboard?.settings?.max_capacity ?? 30
  const congestionRate = Math.min(
    Math.round((peopleCount / maxCapacity) * 100),
    100
  )

  const congestionLabel =
    congestionRate >= 80
      ? '혼잡'
      : congestionRate >= 50
        ? '보통'
        : '여유'

  return (
    <section className={`hero-section ${isAuthPage ? 'is-auth-page' : ''}`}>

      <div className="hero-background" />
      <div className="hero-gradient" />

      {!isAuthPage && (
        <>
          <header className="hero-header">
            <button
              type="button"
              className="hero-menu-button"
              onClick={onMenuOpen}
              aria-label="메뉴 열기"
            >
              <span />
              <span />
            </button>

            <a className="hero-brand" href="#top">
              <span className="hero-brand-mark">◉</span>

              <span>
                <strong>AI’s Eye</strong>
                <small>AI MONITORING SYSTEM</small>
              </span>
            </a>

            <div className="hero-status">
              <span className="hero-status-dot" />
              <span>실시간 연결 중</span>
            </div>
          </header>

          <div className="hero-layout">
            <div className="hero-copy">
              <p className="hero-kicker">INTELLIGENT STORE OPERATIONS</p>

              <h1>
                Know your store.
                <span>Before your customers do.</span>
              </h1>

              <p className="hero-korean-title">
                AI가 매장의 현재를 분석하고
                <br />
                더 나은 운영을 제안합니다.
              </p>

              <p className="hero-description">
                실시간 CCTV 분석과 매장 데이터를 결합하여
                <br />
                혼잡도, 대기시간, 고객 흐름을 한눈에 확인하세요.
              </p>

              <div className={`hero-actions ${isSettings ? 'is-hidden' : ''}`}>
                <a href="#dashboard" className="hero-primary-button">
                  실시간 모니터링
                  <span>↗</span>
                </a>

                <button
                  type="button"
                  className="hero-secondary-button"
                  onClick={onMenuOpen}
                >
                  전체 메뉴
                  <span>＋</span>
                </button>
              </div>

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
                    대기 주문
                  </div>

                  <div className="hero-inline-value">
                    <strong>{waitingTeams}건</strong>
                    <span>예상 대기 {waitMinutes}분</span>
                  </div>
                </div>
              </div>

            </div>
          </div>

          <a href="#dashboard" className="hero-scroll">
            <span className="hero-scroll-line" />
            <small>SCROLL TO EXPLORE</small>
          </a>
        </>
      )}
    </section>
  )
}

export default HeroSection
