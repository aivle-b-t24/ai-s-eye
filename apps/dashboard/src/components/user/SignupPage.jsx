import React from 'react'
import { ROLES } from '../../constants/auth'

export default function SignupPage({ onGoToLogin, initialRole = ROLES.STORE_MANAGER }) {
  const isAdmin = initialRole === ROLES.ADMIN

  return (
    <div className="auth-wrapper">
      <div className="auth-card signup-card account-guide-card">
        <button
          type="button"
          className="auth-back-arrow-btn"
          onClick={onGoToLogin}
          aria-label="로그인 화면으로 돌아가기"
          title="로그인 화면으로 돌아가기"
        >
          ←
        </button>

        <div className="auth-header">
          <span className="auth-badge">AI MONITORING SYSTEM</span>
          <h2 className="auth-title">계정 발급 안내</h2>
          <p className="auth-subtitle">
            {isAdmin
              ? '본사 관리자 계정은 시스템 운영 담당자가 발급합니다.'
              : '점주 계정은 프랜차이즈 본사 관리자가 발급합니다.'}
          </p>
        </div>

        <div className="account-guide-steps">
          <div>
            <strong>1</strong>
            <span>관리자가 이메일과 담당 매장으로 계정을 등록합니다.</span>
          </div>
          <div>
            <strong>2</strong>
            <span>로그인 화면에서 비밀번호 설정 메일을 요청합니다.</span>
          </div>
          <div>
            <strong>3</strong>
            <span>이메일 링크에서 비밀번호를 정한 뒤 로그인합니다.</span>
          </div>
        </div>

        <button type="button" className="auth-submit-btn" onClick={onGoToLogin}>
          로그인 화면으로 돌아가기
        </button>
      </div>
    </div>
  )
}
