import React from "react";

const maskName = (name) => {
  if (!name) return ''
  const parts = name.split(' ')
  if (parts.length > 0 && parts[0].length >= 2) {
    const mainName = parts[0]
    let masked = ''
    if (mainName.length === 2) {
      masked = mainName[0] + '*'
    } else {
      const mid = Math.floor(mainName.length / 2)
      masked = mainName.slice(0, mid) + '*' + mainName.slice(mid + 1)
    }
    parts[0] = masked
    return parts.join(' ')
  }
  return name
}

export default function GnbHeader({
  page,
  setPage,
  _loadStateOnly,
  _loading,
  user,
  onLogout,
  onOpenProfile,
}) {
  return (
    <header className="gnb-header">
      <button
        type="button"
        className="header-back-btn"
        onClick={onLogout}
        aria-label="뒤로가기 (로그인 화면으로 이동)"
        title="로그인 화면으로 돌아가기"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="19" y1="12" x2="5" y2="12" />
          <polyline points="12 19 5 12 12 5" />
        </svg>
      </button>

      <div className="brand-zone">
        <span className="brand-badge">AI MONITORING SYSTEM</span>
        <h1 className="brand-title">AI&apos;s Eye</h1>
      </div>




        <button
          type="button"
          className="tab-btn green-pill-btn"
          onClick={() => {
            setPage("store-001");
            window.history.pushState({}, '', '/store-001.aicafe');
          }}
        >
          실시간 모니터링 ↗
        </button>

        <button
          type="button"
          className="tab-btn dark-pill-btn"
          onClick={() => {
            setPage("kos");
            window.history.pushState({}, '', '/kos');
          }}
        >
          전체 메뉴 +
        </button>

      <nav className="store-tabs" aria-label="가맹점 정보">       
        {(user?.storeId === 'store-002' || page === 'store-002') ? (
          <button
            type="button"
            className="tab-btn active"
            onClick={() => {
              setPage("store-002");
              window.history.pushState({}, '', '/store-002.aicafe');
            }}
          >
            [점주] 매장 2 (수완점)
          </button>
        ) : (
          <button
            type="button"
            className="tab-btn active"
            onClick={() => {
              setPage("store-001");
              window.history.pushState({}, '', '/store-001.aicafe');
            }}
          >
            [점주] 매장 1 (동명점)
          </button>
        )}
      </nav>



      <div className="header-actions">
        <button
          type="button"
          className={`action-btn settings-btn ${
            page === "setting" ? "active" : ""
          }`}
          onClick={() => setPage("setting")}
        >
          설정
        </button>


        {user && (
          <div className="user-profile-badge">
            <span
              className="user-name clickable"
              onClick={onOpenProfile}
              title="프로필 상세정보 보기"
            >
              {maskName(user.name)}
            </span>
            <button
              type="button"
              className="logout-btn"
              onClick={onLogout}
            >
              로그아웃
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

