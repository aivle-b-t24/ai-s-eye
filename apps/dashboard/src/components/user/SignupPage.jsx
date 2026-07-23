import React, { useState } from 'react';

export default function SignupPage({ onGoToLogin, onCompleteSignup }) {
  const [step, setStep] = useState(1);
  const [agreeTerms, setAgreeTerms] = useState(false);
  const [agreePrivacy, setAgreePrivacy] = useState(false);
  const [agreeMarketing, setAgreeMarketing] = useState(false);

  const [role, setRole] = useState('store_manager');
  const [storeId, setStoreId] = useState('store-001');
  const [userId, setUserId] = useState('');
  const [userName, setUserName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  
  const [isIdChecked, setIsIdChecked] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const isMinLength = password.length >= 8 && password.length <= 16;
  const hasLetter = /[a-zA-Z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  const hasSpecial = /[!@#$%^&*(),.?":{}|<>]/.test(password);
  const isPasswordValid = isMinLength && hasLetter && hasNumber && hasSpecial;
  const isPasswordMatch = password && password === confirmPassword;

  const handleIdCheck = () => {
    if (!userId.trim()) {
      setErrorMessage('아이디를 입력해 주세요.');
      return;
    }
    if (userId === 'admin' || userId === 'owner') {
      setErrorMessage('❌ 이미 사용 중인 아이디입니다.');
      setIsIdChecked(false);
    } else {
      setErrorMessage('');
      setSuccessMessage('🟢 사용 가능한 아이디입니다.');
      setIsIdChecked(true);
    }
  };

  const handleNextStep = () => {
    if (!agreeTerms || !agreePrivacy) {
      setErrorMessage('필수 약관 및 개인정보 수집 이용에 동의해 주세요.');
      return;
    }
    setErrorMessage('');
    setStep(2);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!isIdChecked) {
      setErrorMessage('아이디 중복 확인을 진행해 주세요.');
      return;
    }
    if (!userName.trim()) {
      setErrorMessage('성명을 입력해 주세요.');
      return;
    }
    if (!isPasswordValid) {
      setErrorMessage('비밀번호 작성 규칙을 확인해 주세요.');
      return;
    }
    if (!isPasswordMatch) {
      setErrorMessage('비밀번호가 일치하지 않습니다.');
      return;
    }

    setErrorMessage('');
    alert('🎉 회원가입 신청이 성공적으로 완료되었습니다! 로그인 화면으로 이동합니다.');
    onCompleteSignup();
  };

  return (
    <div className="auth-wrapper">
      <div className="auth-card signup-card">
        <div className="auth-header">
          <span className="auth-badge">AI MONITORING SYSTEM</span>
          <h2 className="auth-title">회원가입 신청</h2>
          <p className="auth-subtitle">
            {step === 1 ? 'Step 1: 약관 및 개인정보 수집 동의' : 'Step 2: 회원 계정 정보 입력'}
          </p>
        </div>

        {errorMessage && <div className="auth-error-alert">{errorMessage}</div>}
        {successMessage && <div className="auth-success-alert">{successMessage}</div>}

        {step === 1 ? (
          <div className="terms-section">
            <div className="terms-box">
              <h4>[필수] 개인정보 수집 및 이용 동의</h4>
              <p>
                <strong>수집 목적:</strong> AI's Eye 시스템 계정 생성, 매장 관제 권한 확인 및 관리자 연락<br />
                <strong>수집 항목:</strong> 성명, 아이디, 비밀번호, 이메일, 담당 매장 정보<br />
                <strong>보유 및 이용 기간:</strong> 회원 탈퇴 시까지 또는 법령이 정한 보유 기간 동안
              </p>
            </div>

            <div className="terms-checkboxes">
              <label className="checkbox-label highlight-check">
                <input
                  type="checkbox"
                  checked={agreeTerms}
                  onChange={(e) => setAgreeTerms(e.target.checked)}
                />
                [필수] 서비스 이용약관 동의
              </label>

              <label className="checkbox-label highlight-check">
                <input
                  type="checkbox"
                  checked={agreePrivacy}
                  onChange={(e) => setAgreePrivacy(e.target.checked)}
                />
                [필수] 개인정보 수집 및 이용 동의
              </label>

              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={agreeMarketing}
                  onChange={(e) => setAgreeMarketing(e.target.checked)}
                />
                [선택] 시스템 긴급 장비 알림 수신 동의
              </label>
            </div>

            <button type="button" className="auth-submit-btn" onClick={handleNextStep}>
              다음 단계로 이동 (회원 정보 입력) →
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="auth-form">
            <div className="form-group">
              <label>회원 구분 (권한)</label>
              <div className="role-selector-radios">
                <label className={`radio-pill ${role === 'store_manager' ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="signupRole"
                    value="store_manager"
                    checked={role === 'store_manager'}
                    onChange={() => setRole('store_manager')}
                  />
                  🏢 점주 (매장 관제)
                </label>
                <label className={`radio-pill ${role === 'admin' ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="signupRole"
                    value="admin"
                    checked={role === 'admin'}
                    onChange={() => setRole('admin')}
                  />
                  👔 본사 관리자 (슈퍼바이저)
                </label>
              </div>
            </div>

            {role === 'store_manager' && (
              <div className="form-group">
                <label htmlFor="storeIdSelect">담당 매장 선택</label>
                <select
                  id="storeIdSelect"
                  value={storeId}
                  onChange={(e) => setStoreId(e.target.value)}
                  className="auth-select"
                >
                  <option value="store-001">🏢 매장 1 (강남점)</option>
                  <option value="store-002">🏢 매장 2 (홍대점)</option>
                </select>
              </div>
            )}

            <div className="form-group">
              <label htmlFor="signupId">아이디</label>
              <div className="input-with-btn">
                <input
                  id="signupId"
                  type="text"
                  placeholder="영문/숫자 4~12자리"
                  value={userId}
                  onChange={(e) => {
                    setUserId(e.target.value);
                    setIsIdChecked(false);
                    setSuccessMessage('');
                  }}
                />
                <button type="button" className="check-btn" onClick={handleIdCheck}>
                  중복 확인
                </button>
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="signupName">성명</label>
              <input
                id="signupName"
                type="text"
                placeholder="홍길동"
                value={userName}
                onChange={(e) => setUserName(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label htmlFor="signupEmail">이메일 주소</label>
              <input
                id="signupEmail"
                type="email"
                placeholder="example@aivle.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label htmlFor="signupPw">비밀번호</label>
              <input
                id="signupPw"
                type="password"
                placeholder="8~16자리 (영문, 숫자, 특수문자 조합)"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <div className="pw-checklist">
                <span className={isMinLength ? 'check-ok' : ''}>
                  {isMinLength ? '✓' : '○'} 8~16자리
                </span>
                <span className={hasLetter ? 'check-ok' : ''}>
                  {hasLetter ? '✓' : '○'} 영문 포함
                </span>
                <span className={hasNumber ? 'check-ok' : ''}>
                  {hasNumber ? '✓' : '○'} 숫자 포함
                </span>
                <span className={hasSpecial ? 'check-ok' : ''}>
                  {hasSpecial ? '✓' : '○'} 특수문자 포함
                </span>
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="confirmPw">비밀번호 확인</label>
              <input
                id="confirmPw"
                type="password"
                placeholder="비밀번호 재입력"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
              {confirmPassword && (
                <span className={`match-hint ${isPasswordMatch ? 'ok' : 'error'}`}>
                  {isPasswordMatch ? '🟢 비밀번호가 일치합니다.' : '🔴 비밀번호가 일치하지 않습니다.'}
                </span>
              )}
            </div>

            <div className="btn-row">
              <button type="button" className="secondary-btn" onClick={() => setStep(1)}>
                ← 이전 단계
              </button>
              <button type="submit" className="auth-submit-btn">
                회원가입 완료 및 가입신청
              </button>
            </div>
          </form>
        )}

        <div className="auth-footer-links">
          <span>이미 계정이 있으신가요?</span>
          <button type="button" className="signup-link-btn" onClick={onGoToLogin}>
            🔒 로그인 화면으로 돌아가기
          </button>
        </div>
      </div>
    </div>
  );
}
