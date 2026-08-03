import React, { useState } from 'react';
import { ROLES, STORES, DEMO_CREDENTIALS } from '../../constants/auth';

export default function LoginPage({ onLogin, onGoToSignup, onClose, initialRole = ROLES.STORE_MANAGER, onRoleChange }) {
  const [role, setRole] = useState(initialRole);
  const [userId, setUserId] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberId, setRememberId] = useState(false);
  const [failedCount, setFailedCount] = useState(0);
  const [errorMessage, setErrorMessage] = useState('');
  const [isStoreSubmenuOpen, setIsStoreSubmenuOpen] = useState(false);

  const handleTabSwitch = (newRole) => {
    setRole(newRole);
    setErrorMessage('');
    if (onRoleChange) {
      onRoleChange(newRole);
    }
  };

  const handleDemoLogin = (selectedRole, targetStoreId = STORES.DONGMYEONG) => {
    const credKey = selectedRole === ROLES.STORE_MANAGER ? targetStoreId : STORES.HEAD_OFFICE;
    const creds = DEMO_CREDENTIALS[credKey] || DEMO_CREDENTIALS[STORES.DONGMYEONG];

    onLogin({
      id: creds.id,
      name: creds.name,
      role: creds.role,
      storeId: creds.storeId,
    });
  };

  const handleSelectDongmyeong = () => {
    setIsStoreSubmenuOpen(false);
    handleDemoLogin(ROLES.STORE_MANAGER, STORES.DONGMYEONG);
  };

  const handleSelectSuwan = () => {
    setIsStoreSubmenuOpen(false);
    handleDemoLogin(ROLES.STORE_MANAGER, STORES.SUWAN);
  };

  const handleAdminDemoLogin = () => {
    handleDemoLogin(ROLES.ADMIN, STORES.HEAD_OFFICE);
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    if (failedCount >= 5) {
      setErrorMessage('비밀번호 5회 이상 오류로 계정이 일시 잠금되었습니다. 고객센터에 문의하거나 비밀번호를 재설정해 주세요.');
      return;
    }

    if (!userId.trim()) {
      setErrorMessage('아이디를 입력해 주세요.');
      return;
    }
    if (!password) {
      setErrorMessage('비밀번호를 입력해 주세요.');
      return;
    }

    if ((role === ROLES.STORE_MANAGER && userId === 'owner' && password === '1234') ||
        (role === ROLES.ADMIN && userId === 'admin' && password === '1234')) {
      setFailedCount(0);
      setErrorMessage('');
      onLogin({
        id: userId,
        name: role === ROLES.STORE_MANAGER ? '강남점 점주' : '본사 관리자',
        role: role,
        storeId: role === ROLES.STORE_MANAGER ? STORES.DONGMYEONG : STORES.HEAD_OFFICE
      });
    } else {
      const newCount = failedCount + 1;
      setFailedCount(newCount);
      if (newCount >= 5) {
        setErrorMessage('비밀번호 5회 이상 오류로 계정이 일시 잠금되었습니다.');
      } else {
        setErrorMessage(`아이디 또는 비밀번호가 올바르지 않습니다. (실패 횟수: ${newCount}/5회)`);
      }
    }
  };

  return (
    <div className="auth-wrapper">
      <div className="auth-card">
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

        <div className="auth-header">
          <span className="auth-badge">AI MONITORING SYSTEM</span>
          <h2 className="auth-title">AI's Eye 로그인</h2>
          <p className="auth-subtitle">관제 시스템에 접속하기 위한 계정 정보를 입력하세요.</p>
        </div>

        <div className="role-switch-tabs">
          <button
            type="button"
            className={`role-tab ${role === ROLES.STORE_MANAGER ? 'active' : ''}`}
            onClick={() => handleTabSwitch(ROLES.STORE_MANAGER)}
          >
            점주 전용 로그인
          </button>
          <button
            type="button"
            className={`role-tab ${role === ROLES.ADMIN ? 'active' : ''}`}
            onClick={() => handleTabSwitch(ROLES.ADMIN)}
          >
            본사 관리자 로그인
          </button>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label htmlFor="userId">
              {role === ROLES.STORE_MANAGER ? '점주 아이디' : '본사 관리자 사번/아이디'}
            </label>
            <input
              id="userId"
              type="text"
              placeholder={role === ROLES.STORE_MANAGER ? '예: owner01' : '예: admin01'}
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              disabled={failedCount >= 5}
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">비밀번호</label>
            <div className="password-input-wrapper">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                placeholder="비밀번호를 입력하세요"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={failedCount >= 5}
              />
              <button
                type="button"
                className="toggle-pw-btn"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
                title={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
              >
                {showPassword ? (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                ) : (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>

            {/* 비밀번호 아래 텍스트만 표시되는 오류 메시지 & X 닫기 버튼 */}
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
          </div>

          <div className="form-options">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={rememberId}
                onChange={(e) => setRememberId(e.target.checked)}
              />
              아이디 저장
            </label>
            <span className="auth-link">아이디 / 비밀번호 찾기</span>
          </div>

          <button type="submit" className="auth-submit-btn" disabled={failedCount >= 5}>
            {role === ROLES.STORE_MANAGER ? '점주 관제 화면 로그인' : '본사 관리자 대시보드 로그인'}
          </button>
        </form>

        <div className="demo-login-box">
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
                    onClick={handleSelectDongmyeong}
                  >
                    매장 1 (동명점)
                  </button>
                  <button
                    type="button"
                    className="store-sub-option"
                    onClick={handleSelectSuwan}
                  >
                    매장 2 (수완점)
                  </button>
                </div>
              )}
            </div>

            <button
              type="button"
              className="demo-btn admin-demo"
              onClick={handleAdminDemoLogin}
            >
              [본사 관리자] 로그인
            </button>
          </div>
        </div>




        <div className="auth-footer-links">
          <span>아직 계정이 없으신가요?</span>
          <button type="button" className="signup-link-btn" onClick={onGoToSignup}>
            회원가입 신청하기
          </button>
        </div>

        <footer className="auth-compliance-footer">
          <span>개인정보 처리방침</span> | <span>이용약관</span> | <span>© 2026 AI's Eye. All rights reserved.</span>
        </footer>
      </div>
    </div>
  );
}

