import React from 'react'

// 로그인·회원가입 공용 좌측 브랜드 패널.
export function BrandLogo({ className = '' }) {
  return (
    <span className={`signup-wordmark ${className}`.trim()}>
      <svg className="signup-logo-mark" width="26" height="26" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3 L21 20 H3 Z" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round" />
        <circle cx="12" cy="14" r="2.4" fill="currentColor" />
      </svg>
      AI&apos;s Eye
    </span>
  )
}

export default function AuthBrandPanel() {
  return (
    <aside className="signup-brand">
      <div className="signup-brand-top">
        <BrandLogo />
      </div>
      <div className="signup-brand-body">
        <h1 className="signup-brand-title">매장을 한눈에,<br />본사는 가볍게.</h1>
        <p className="signup-brand-sub">
          프랜차이즈 매장을 한 화면에서 관제하고, 고객 응대까지 하나로 이어집니다.
        </p>
        <ul className="signup-brand-features">
          <li>실시간 혼잡도·대기 관제</li>
          <li>매장별 메뉴·정책 온보딩</li>
          <li>카카오 챗봇 고객 응대</li>
        </ul>
      </div>
      <div className="signup-brand-foot">© AI&apos;s Eye · AIVLE 24조</div>
    </aside>
  )
}
