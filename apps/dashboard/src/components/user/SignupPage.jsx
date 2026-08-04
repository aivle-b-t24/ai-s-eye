import React from 'react'
import { ROLES } from '../../constants/auth'

export default function SignupPage({ onClose, onGoToLogin, initialRole = ROLES.STORE_MANAGER }) {
  const isAdmin = initialRole === ROLES.ADMIN

  return (
    <div className="auth-wrapper">
      <div className="auth-card signup-card">
        {onClose && (
          <button
            type="button"
            className="auth-modal-close-btn"
            onClick={onClose}
            aria-label="취소 (메인 페이지로 이동)"
            title="취소 (메인 페이지로 이동)"
          >
            ✕ 취소
          </button>
        )}

        {/* 좌측 상단 뒤로가기 버튼 */}
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
            <span>관리자가 로그인 이메일, 담당 매장, 초기 비밀번호를 등록합니다.</span>
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
      </div>
    </div>
  )
}
