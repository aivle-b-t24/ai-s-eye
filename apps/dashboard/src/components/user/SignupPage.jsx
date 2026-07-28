import React, { useState } from 'react';

export default function SignupPage({ onGoToLogin, onCompleteSignup, onClose }) {
  const [step, setStep] = useState(1);
  const [agreeTerms, setAgreeTerms] = useState(false);
  const [agreePrivacy, setAgreePrivacy] = useState(false);
  const [agreeThirdParty, setAgreeThirdParty] = useState(false);
  const [agreeAlerts, setAgreeAlerts] = useState(false);
  const [agreeMarketing, setAgreeMarketing] = useState(false);

  const [showPrivacyGuide, setShowPrivacyGuide] = useState(true);
  const [isGuideExpanded, setIsGuideExpanded] = useState(false);

  const agreeAll = agreeTerms && agreePrivacy && agreeThirdParty && agreeAlerts && agreeMarketing;
  const canProceed = agreeTerms && agreePrivacy && agreeThirdParty;

  const handleToggleAll = () => {
    const nextVal = !agreeAll;
    setAgreeTerms(nextVal);
    setAgreePrivacy(nextVal);
    setAgreeThirdParty(nextVal);
    setAgreeAlerts(nextVal);
    setAgreeMarketing(nextVal);
  };

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
      setErrorMessage('이미 사용 중인 아이디입니다.');
      setIsIdChecked(false);
    } else {
      setErrorMessage('');
      setSuccessMessage('사용 가능한 아이디입니다.');
      setIsIdChecked(true);
    }
  };

  const handleNextStep = () => {
    if (!canProceed) {
      setErrorMessage('필수 동의 항목(3개)에 모두 동의해 주셔야 다음 단계로 이동할 수 있습니다.');
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
    alert('회원가입 신청이 성공적으로 완료되었습니다! 로그인 화면으로 이동합니다.');
    onCompleteSignup();
  };

  return (
    <div className="auth-wrapper">
      <div className="auth-card signup-card">
        {/* 좌측 상단 뒤로가기 버튼 */}
        <button
          type="button"
          className="auth-back-arrow-btn"
          onClick={() => {
            if (step === 2) {
              setStep(1);
              setErrorMessage('');
              setSuccessMessage('');
            } else {
              onGoToLogin();
            }
          }}
          aria-label={step === 2 ? '약관 동의 화면으로 돌아가기' : '로그인 화면으로 돌아가기'}
          title={step === 2 ? '약관 동의 화면으로 돌아가기' : '로그인 화면으로 돌아가기'}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>

        {/* 우측 상단 X자 닫기 버튼 */}
        <button
          type="button"
          className="auth-close-x-btn"
          onClick={onClose}
          aria-label="닫기"
          title="닫기"
        >
          ✕
        </button>



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
          <div className="naver-terms-wrapper">
            {/* 전체 동의하기 카카오/네이버 스타일 카드 */}
            <div className={`naver-all-agree-card ${agreeAll ? 'checked' : ''}`} onClick={handleToggleAll}>
              <div className="naver-check-circle">
                <span>✓</span>
              </div>
              <div className="naver-all-agree-text">
                <strong>전체 동의하기</strong>
                <p>
                  AI's Eye 서비스 이용약관, 개인정보 수집 및 이용(필수), AI 비전 데이터 위탁(필수), 장비 및 마케팅 알림(선택) 동의를 포함합니다.
                </p>
              </div>
            </div>

            {/* 개별 동의 목록 */}
            <ul className="naver-terms-list">
              <li className="naver-terms-item">
                <label className="naver-checkbox-row">
                  <input
                    type="checkbox"
                    checked={agreeTerms}
                    onChange={(e) => setAgreeTerms(e.target.checked)}
                  />
                  <span className={`naver-check-circle ${agreeTerms ? 'checked' : ''}`}>✓</span>
                  <span className="badge-required">필수</span>
                  <span className="item-title">AI's Eye 서비스 이용약관</span>
                </label>
                <button type="button" className="view-link-btn" onClick={() => setShowPrivacyGuide(true)}>보기</button>
              </li>

              <li className="naver-terms-item">
                <label className="naver-checkbox-row">
                  <input
                    type="checkbox"
                    checked={agreePrivacy}
                    onChange={(e) => setAgreePrivacy(e.target.checked)}
                  />
                  <span className={`naver-check-circle ${agreePrivacy ? 'checked' : ''}`}>✓</span>
                  <span className="badge-required">필수</span>
                  <span className="item-title">개인정보 수집 및 이용 동의</span>
                </label>
                <button type="button" className="view-link-btn" onClick={() => setShowPrivacyGuide(true)}>보기</button>
              </li>

              <li className="naver-terms-item">
                <label className="naver-checkbox-row">
                  <input
                    type="checkbox"
                    checked={agreeThirdParty}
                    onChange={(e) => setAgreeThirdParty(e.target.checked)}
                  />
                  <span className={`naver-check-circle ${agreeThirdParty ? 'checked' : ''}`}>✓</span>
                  <span className="badge-required">필수</span>
                  <span className="item-title">AI CCTV 비전 분석 및 처리 위탁 동의</span>
                </label>
                <button type="button" className="view-link-btn" onClick={() => setShowPrivacyGuide(true)}>보기</button>
              </li>

              <li className="naver-terms-item">
                <label className="naver-checkbox-row">
                  <input
                    type="checkbox"
                    checked={agreeAlerts}
                    onChange={(e) => setAgreeAlerts(e.target.checked)}
                  />
                  <span className={`naver-check-circle ${agreeAlerts ? 'checked' : ''}`}>✓</span>
                  <span className="badge-optional">선택</span>
                  <span className="item-title">시스템 긴급 장비 장애 및 AI 모니터링 알림 수신</span>
                </label>
              </li>

              <li className="naver-terms-item">
                <label className="naver-checkbox-row">
                  <input
                    type="checkbox"
                    checked={agreeMarketing}
                    onChange={(e) => setAgreeMarketing(e.target.checked)}
                  />
                  <span className={`naver-check-circle ${agreeMarketing ? 'checked' : ''}`}>✓</span>
                  <span className="badge-optional">선택</span>
                  <span className="item-title">마케팅 정보 활용 및 맞춤형 AI 인사이트 수신</span>
                </label>
              </li>
            </ul>

            {/* 개인정보 수집 및 이용 안내 접기/펼치기 아코디언 */}
            <div className="naver-guide-accordion">
              <div className="accordion-header" onClick={() => setShowPrivacyGuide(!showPrivacyGuide)}>
                <div className="accordion-title">
                  <span className="dot">•</span>
                  <strong>개인정보 수집 및 이용 안내</strong>
                  <span className="arrow-icon">{showPrivacyGuide ? '▲' : '▼'}</span>
                </div>
                <span className="sub-link">정부 규제 준수 가이드 기준</span>
              </div>

              {showPrivacyGuide && (
                <div className="accordion-body">
                  <div className={`scroll-box ${isGuideExpanded ? 'expanded' : ''}`}>
                    <p>
                      <strong>[개인정보 보호법 제15조 및 제17조(수집·이용 및 위탁 고지)]</strong><br /><br />
                      개인정보 보호법 제15조제1항제4호(계약 체결/이행) 및 제17조에 따라, 아래와 같이 개인정보를 수집·이용 및 위탁 처리합니다.<br />
                      AI's Eye 회원가입 시 하나의 계정으로 전체 매장 관제 및 본사 통합 시스템 이용이 가능하며, 수집된 정보는 서비스 제공 목적 외 용도로 활용되지 않습니다.<br /><br />
                      1. <strong>수집·이용 목적:</strong> 계정 생성, 매장 AI 관제 권한 확인 및 본인 식별<br />
                      2. <strong>수집 항목:</strong> 성명, 아이디, 비밀번호, 이메일 주소, 담당 매장 정보<br />
                      3. <strong>처리 위탁:</strong> AI 실시간 CCTV 객체 감지 및 비전 분석 스트림 데이터 수탁 처리<br />
                      4. <strong>보유 및 이용 기간:</strong> 회원 탈퇴 시까지 또는 관계 법령이 정한 일정 기간 동안 보존
                    </p>
                  </div>
                  <button
                    type="button"
                    className="more-toggle-btn"
                    onClick={() => setIsGuideExpanded(!isGuideExpanded)}
                  >
                    {isGuideExpanded ? '접기 ▲' : '더 보기 ▼'}
                  </button>
                </div>
              )}
            </div>

            {/* 다음 버튼 */}
            <button
              type="button"
              className={`naver-next-btn ${canProceed ? 'active' : ''}`}
              onClick={handleNextStep}
            >
              다음
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
                  점주 (매장 관제)
                </label>
                <label className={`radio-pill ${role === 'admin' ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="signupRole"
                    value="admin"
                    checked={role === 'admin'}
                    onChange={() => setRole('admin')}
                  />
                  본사 관리자 (슈퍼바이저)
                </label>
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="storeIdSelect">
                {role === 'store_manager' ? '담당 매장 선택' : '담당 관제 영역'}
              </label>
              {role === 'store_manager' ? (
                <select
                  id="storeIdSelect"
                  value={storeId}
                  onChange={(e) => setStoreId(e.target.value)}
                  className="auth-select"
                >
                  <option value="store-001">매장 1 (강남점)</option>
                  <option value="store-002">매장 2 (홍대점)</option>
                </select>
              ) : (
                <div
                  className="auth-select"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    background: '#fafcfb',
                    border: '1px solid var(--border-light, #d0d7de)',
                    color: '#1a1a1a',
                    fontFamily: 'inherit',
                    fontSize: '0.95rem',
                    fontWeight: 'normal',
                    cursor: 'default',
                    userSelect: 'none'
                  }}
                >
                  전 가맹점 통합 관제 (본사 직속)
                </div>


              )}
            </div>



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
                  {isPasswordMatch ? '비밀번호가 일치합니다.' : '비밀번호가 일치하지 않습니다.'}
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
            로그인 화면으로 돌아가기
          </button>
        </div>

      </div>
    </div>
  );
}
