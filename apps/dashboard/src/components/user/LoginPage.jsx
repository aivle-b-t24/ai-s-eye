import React, { useState } from 'react';

export default function LoginPage({ onLogin, onGoToSignup }) {
  const [role, setRole] = useState('store_manager');
  const [userId, setUserId] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberId, setRememberId] = useState(false);
  const [failedCount, setFailedCount] = useState(0);
  const [errorMessage, setErrorMessage] = useState('');

  const handleDemoLogin = (selectedRole) => {
    const demoId = selectedRole === 'store_manager' ? 'owner01' : 'admin01';
    const userName = selectedRole === 'store_manager' ? '김점주 점주님' : '박팀장 슈퍼바이저님';
    const storeId = selectedRole === 'store_manager' ? 'store-001' : 'head-office';
    
    onLogin({
      id: demoId,
      name: userName,
      role: selectedRole,
      storeId: storeId
    });
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    if (failedCount >= 5) {
      setErrorMessage('🚨 비밀번호 5회 이상 오류로 계정이 일시 잠금되었습니다. 고객센터에 문의하거나 비밀번호를 재설정해 주세요.');
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

    if ((role === 'store_manager' && userId === 'owner' && password === '1234') ||
        (role === 'admin' && userId === 'admin' && password === '1234')) {
      setFailedCount(0);
      setErrorMessage('');
      onLogin({
        id: userId,
        name: role === 'store_manager' ? '강남점 점주' : '본사 관리자',
        role: role,
        storeId: role === 'store_manager' ? 'store-001' : 'head-office'
      });
    } else {
      const newCount = failedCount + 1;
      setFailedCount(newCount);
      if (newCount >= 5) {
        setErrorMessage('🚨 비밀번호 5회 이상 오류로 계정이 일시 잠금되었습니다.');
      } else {
        setErrorMessage(`아이디 또는 비밀번호가 올바르지 않습니다. (실패 횟수: ${newCount}/5회)`);
      }
    }
  };

  return (
    <div className="auth-wrapper">
      <div className="auth-card">
        <div className="auth-header">
          <span className="auth-badge">AI MONITORING SYSTEM</span>
          <h2 className="auth-title">AI's Eye 로그인</h2>
          <p className="auth-subtitle">관제 시스템에 접속하기 위한 계정 정보를 입력하세요.</p>
        </div>

        <div className="role-switch-tabs">
          <button
            type="button"
            className={`role-tab ${role === 'store_manager' ? 'active' : ''}`}
            onClick={() => { setRole('store_manager'); setErrorMessage(''); }}
          >
            👤 점주 전용 로그인
          </button>
          <button
            type="button"
            className={`role-tab ${role === 'admin' ? 'active' : ''}`}
            onClick={() => { setRole('admin'); setErrorMessage(''); }}
          >
            👔 본사 관리자 로그인
          </button>
        </div>

        {errorMessage && (
          <div className="auth-error-alert">
            {errorMessage}
          </div>
        )}

        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label htmlFor="userId">
              {role === 'store_manager' ? '점주 아이디' : '본사 관리자 사번/아이디'}
            </label>
            <input
              id="userId"
              type="text"
              placeholder={role === 'store_manager' ? '예: owner01' : '예: admin01'}
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
              >
                {showPassword ? '🙈' : '👁️'}
              </button>
            </div>
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
            {role === 'store_manager' ? '👤 점주 관제 화면 로그인' : '👔 본사 관리자 대시보드 로그인'}
          </button>
        </form>

        <div className="demo-login-box">
          <p className="demo-hint">💡 [빠른 체험용 원클릭 로그인]</p>
          <div className="demo-btn-group">
            <button
              type="button"
              className="demo-btn store-demo"
              onClick={() => handleDemoLogin('store_manager')}
            >
              🏢 [점주] 강남점 로그인
            </button>
            <button
              type="button"
              className="demo-btn admin-demo"
              onClick={() => handleDemoLogin('admin')}
            >
              👔 [본사 관리자] 슈퍼바이저 로그인
            </button>
          </div>
        </div>

        <div className="auth-footer-links">
          <span>아직 계정이 없으신가요?</span>
          <button type="button" className="signup-link-btn" onClick={onGoToSignup}>
            📝 회원가입 신청하기
          </button>
        </div>

        <footer className="auth-compliance-footer">
          <span>개인정보 처리방침</span> | <span>이용약관</span> | <span>© 2026 AI's Eye. All rights reserved.</span>
        </footer>
      </div>
    </div>
  );
}
