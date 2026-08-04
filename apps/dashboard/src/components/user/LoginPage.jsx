import React, { useEffect, useState } from 'react';
import { ROLES, STORES } from '../../constants/auth';
import { LOCAL_DEMO_ACCOUNTS } from '../../auth/localAuth';
import { IS_LOCAL_AUTH_MODE } from '../../auth/runtimeAuth';

const REMEMBERED_EMAIL_KEY = 'aicafe.rememberedEmail';
const DEMO_LOGIN_ENABLED = (
  IS_LOCAL_AUTH_MODE
  || (
    import.meta.env.DEV
    && String(import.meta.env.VITE_ENABLE_DEMO_LOGIN ?? 'false').toLowerCase() === 'true'
  )
);
const FIREBASE_DEMO_ACCOUNTS = import.meta.env.DEV
  ? {
      [STORES.DONGMYEONG]: {
        email: import.meta.env.VITE_DEMO_STORE_001_EMAIL,
        password: import.meta.env.VITE_DEMO_STORE_001_PASSWORD,
        role: ROLES.STORE_MANAGER,
      },
      [STORES.SUWAN]: {
        email: import.meta.env.VITE_DEMO_STORE_002_EMAIL,
        password: import.meta.env.VITE_DEMO_STORE_002_PASSWORD,
        role: ROLES.STORE_MANAGER,
      },
      [STORES.HEAD_OFFICE]: {
        email: import.meta.env.VITE_DEMO_ADMIN_EMAIL,
        password: import.meta.env.VITE_DEMO_ADMIN_PASSWORD,
        role: ROLES.ADMIN,
      },
    }
  : {};
const DEMO_ACCOUNTS = IS_LOCAL_AUTH_MODE
  ? LOCAL_DEMO_ACCOUNTS
  : FIREBASE_DEMO_ACCOUNTS;

export default function LoginPage({ onClose, onLogin, onPasswordReset, onGoToSignup, initialRole = ROLES.STORE_MANAGER, initialError = '', onRoleChange }) {
  const [role, setRole] = useState(initialRole);
  const [userId, setUserId] = useState(() => localStorage.getItem(REMEMBERED_EMAIL_KEY) ?? '');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberId, setRememberId] = useState(() => Boolean(localStorage.getItem(REMEMBERED_EMAIL_KEY)));
  const [errorMessage, setErrorMessage] = useState(initialError);
  const [successMessage, setSuccessMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isStoreSubmenuOpen, setIsStoreSubmenuOpen] = useState(false);

  useEffect(() => setRole(initialRole), [initialRole]);
  useEffect(() => setErrorMessage(initialError), [initialError]);

  const handleTabSwitch = (newRole) => {
    setRole(newRole);
    setErrorMessage('');
    setSuccessMessage('');
    if (onRoleChange) {
      onRoleChange(newRole);
    }
  };

  const handleResetPassword = async () => {
    setErrorMessage('');
    setSuccessMessage('');
    try {
      await onPasswordReset(userId);
      setSuccessMessage('비밀번호 설정 메일을 보냈습니다. 이메일의 링크를 확인해 주세요.');
    } catch (error) {
      setErrorMessage(error.message || '비밀번호 설정 메일을 보내지 못했습니다.');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!userId.trim()) {
      setErrorMessage('이메일을 입력해 주세요.');
      return;
    }
    if (!password) {
      setErrorMessage('비밀번호를 입력해 주세요.');
      return;
    }

    setIsSubmitting(true);
    try {
      await onLogin({
        email: userId.trim(),
        password,
        remember: rememberId,
      });
      if (rememberId) {
        localStorage.setItem(REMEMBERED_EMAIL_KEY, userId.trim());
      } else {
        localStorage.removeItem(REMEMBERED_EMAIL_KEY);
      }
      setErrorMessage('');
    } catch (error) {
      setErrorMessage(error.message || '로그인에 실패했습니다.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDemoLogin = async (storeId) => {
    const account = DEMO_ACCOUNTS[storeId];
    if (!account?.email || !account?.password) {
      setErrorMessage('빠른 로그인 계정이 설정되지 않았습니다.');
      return;
    }

    setIsStoreSubmenuOpen(false);
    setRole(account.role);
    setErrorMessage('');
    setIsSubmitting(true);
    if (onRoleChange) {
      onRoleChange(account.role);
    }

    try {
      await onLogin({
        email: account.email,
        password: account.password,
        remember: false,
        role: account.role,
      });
    } catch (error) {
      setErrorMessage(error.message || '빠른 로그인에 실패했습니다.');
    } finally {
      setIsSubmitting(false);
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
              {role === ROLES.STORE_MANAGER ? '점주 이메일' : '본사 관리자 이메일'}
            </label>
            <input
              id="userId"
              type="email"
              autoComplete="username"
              placeholder={role === ROLES.STORE_MANAGER ? '예: owner01@aicafe.com' : '예: admin01@aicafe.com'}
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              disabled={isSubmitting}
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
                autoComplete="current-password"
                disabled={isSubmitting}
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
            {successMessage && (
              <div className="auth-success-alert inline-single-line clean-text-only">
                <span>{successMessage}</span>
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
              이메일 저장
            </label>
            {IS_LOCAL_AUTH_MODE ? (
              <span className="auth-link">로컬 개발 모드</span>
            ) : (
              <button
                type="button"
                className="auth-link auth-link-button"
                onClick={handleResetPassword}
                disabled={isSubmitting}
              >
                비밀번호 설정 / 재설정
              </button>
            )}
          </div>

          <button type="submit" className="auth-submit-btn" disabled={isSubmitting}>
            {isSubmitting
              ? '로그인 확인 중...'
              : role === ROLES.STORE_MANAGER
                ? '점주 관제 화면 로그인'
                : '본사 관리자 대시보드 로그인'}
          </button>
        </form>

        

        
      </div>
    </div>
  );
}
