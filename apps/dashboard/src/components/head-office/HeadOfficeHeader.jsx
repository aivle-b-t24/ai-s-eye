export default function HeadOfficeHeader({ user, onLogout }) {
  return (
    <header className="head-office-header">
      <div className="head-office-header-inner">
        <a className="head-office-brand" href="#hq-overview">
          <span>AI&apos;s Eye</span>
          <strong>HQ OPERATIONS</strong>
        </a>

        <nav className="head-office-navigation" aria-label="본사 운영 메뉴">
          <a href="#hq-overview">운영 개요</a>
          <a href="#hq-stores">가맹점 분석</a>
          <a href="#hq-ai">AI 인사이트</a>
        </nav>

        <div className="head-office-user">
          <div>
            <span>본사 슈퍼바이저</span>
            <strong>{user?.name ?? '관리자'}</strong>
          </div>
          <button type="button" onClick={onLogout}>로그아웃</button>
        </div>
      </div>
    </header>
  )
}
