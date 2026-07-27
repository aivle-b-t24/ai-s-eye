import React from "react";

export default function GnbHeader({
  page,
  setPage,
  loadStateOnly,
  loading,
  user,
  onLogout,
}) {
  return (
    <header className="gnb-header">
      <div className="brand-zone">
        <span className="brand-badge">AI MONITORING SYSTEM</span>
        <h1 className="brand-title">AI&apos;s Eye</h1>
      </div>

      <nav className="store-tabs" aria-label="역할별 화면 전환">
        <button
          type="button"
          className={`tab-btn ${page === "store-001" ? "active" : ""}`}
          onClick={() => setPage("store-001")}
        >
          [점주] 매장 1
        </button>

        <button
          type="button"
          className={`tab-btn ${page === "store-002" ? "active" : ""}`}
          onClick={() => setPage("store-002")}
        >
          [점주] 매장 2
        </button>

        <button
          type="button"
          className={`tab-btn supervisor-tab ${
            page === "head-office" ? "active" : ""
          }`}
          onClick={() => setPage("head-office")}
        >
          [슈퍼바이저] 본사
        </button>
      </nav>

      <div className="header-actions">
        <button
          type="button"
          className="action-btn refresh-btn"
          onClick={() =>
            loadStateOnly(page.startsWith("store") ? page : "store-001", true)
          }
          disabled={loading}
        >
          {loading ? "갱신 중..." : "새로고침"}
        </button>

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
            <span className="user-name">{user.name}</span>
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
