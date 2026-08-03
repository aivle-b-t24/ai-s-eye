import React, { useState } from 'react';
import { ROLES, STORES, ENDPOINTS } from '../../constants/auth';

export default function SignupPage({ onGoToLogin, onCompleteSignup, onClose, initialRole = ROLES.STORE_MANAGER, onRoleChange }) {
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

  const [role, setRoleState] = useState(initialRole);
  const setRole = (newRole) => {
    setRoleState(newRole);
    if (onRoleChange) {
      onRoleChange(newRole);
    }
  };

  const [storeId, setStoreId] = useState(STORES.DONGMYEONG);
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
                  {role === ROLES.STORE_MANAGER
                    ? "AI's Eye 가맹점 매장 관제 서비스 이용약관, 점주 개인정보 수집(필수), 매장 AI 비전 데이터 위탁(필수), 매장 장애 및 알림(선택) 동의를 포함합니다."
                    : "AI's Eye 본사 통합 관제 시스템 이용약관, 본사 관리자 정보 수집(필수), 전 가맹점 통합 데이터 처리(필수), 긴급 알림(선택) 동의를 포함합니다."}
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
                  <span className="item-title">
                    {role === ROLES.STORE_MANAGER
                      ? "AI's Eye 가맹점 매장 관제 서비스 이용약관"
                      : "AI's Eye 본사 통합 관제 시스템 이용약관"}
                  </span>
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
                  <span className="item-title">
                    {role === ROLES.STORE_MANAGER
                      ? "점주 개인정보 및 매장 정보 수집·이용 동의"
                      : "본사 관리자 사번 및 시스템 접속 권한 정보 수집·이용 동의"}
                  </span>
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
                  <span className="item-title">
                    {role === ROLES.STORE_MANAGER
                      ? "매장 AI CCTV 비전 분석 및 객체 감지 데이터 위탁 동의"
                      : "전 가맹점 통합 모니터링 데이터 접근 및 처리 위탁 동의"}
                  </span>
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
                  <span className="item-title">
                    {role === ROLES.STORE_MANAGER
                      ? "매장 긴급 장비 장애 및 AI 모니터링 알림 수신"
                      : "가맹점 통합 이상징후 및 슈퍼바이저 긴급 알림 수신"}
                  </span>
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
                  <span className="item-title">
                    {role === ROLES.STORE_MANAGER
                      ? "점주 맞춤형 매장 매출·혼잡도 분석 인사이트 수신"
                      : "전 가맹점 통합 운영 리포트 및 마케팅 인사이트 수신"}
                  </span>
                </label>
              </li>
            </ul>

            {/* 개인정보 수집 및 이용 안내 접기/펼치기 아코디언 */}
            <div className="naver-guide-accordion">
              <div className="accordion-header" onClick={() => setShowPrivacyGuide(!showPrivacyGuide)}>
                <div className="accordion-title">
                  <span className="dot">•</span>
                  <strong>
                    {role === ROLES.STORE_MANAGER
                      ? "점주 개인정보 및 매장 비전 데이터 수집·이용 안내"
                      : "본사 관리자 권한 및 통합 관제 데이터 수집·이용 안내"}
                  </strong>
                  <span className="arrow-icon">{showPrivacyGuide ? '▲' : '▼'}</span>
                </div>
                <span className="sub-link">정부 규제 준수 가이드 기준</span>
              </div>

              {showPrivacyGuide && (
                <div className="accordion-body">
                  <div className={`scroll-box ${isGuideExpanded ? 'expanded' : ''}`}>
                    {role === ROLES.STORE_MANAGER ? (
                      <p>
                        <strong>[점주 전용: 개인정보 보호법 제15조 및 제17조(수집·이용 및 위탁 고지)]</strong><br /><br />
                        개인정보 보호법 제15조제1항제4호(계약 체결/이행) 및 제17조에 따라, 가맹점 관제 서비스 제공을 위해 개별 매장 점주님의 정보를 수집·이용 및 위탁 처리합니다.<br /><br />
                        1. <strong>수집·이용 목적:</strong> 가맹점 계정 생성, 개별 매장(동명점/수완점 등) AI 관제 권한 확인 및 본인 식별<br />
                        2. <strong>수집 항목:</strong> 성명, 아이디, 비밀번호, 이메일 주소, 담당 가맹점 정보<br />
                        3. <strong>처리 위탁:</strong> 매장 실시간 CCTV 객체 감지, 대기시간 및 매장 혼잡도 AI 스트림 분석 처리<br />
                        4. <strong>보유 및 이용 기간:</strong> 회원 탈퇴 시 또는 관계 법령이 정한 일정 기간 보존
                      </p>
                    ) : (
                      <p>
                        <strong>[본사 관리자 전용: 개인정보 보호법 제15조 및 제17조(수집·이용 및 위탁 고지)]</strong><br /><br />
                        개인정보 보호법 제15조제1항제4호(계약 체결/이행) 및 제17조에 따라, 본사 슈퍼바이저 통제 및 가맹점 통합 관제 서비스를 위해 아래와 같이 정보를 처리합니다.<br /><br />
                        1. <strong>수집·이용 목적:</strong> 본사 관리자 계정 생성, 전 가맹점 통합 관제 및 슈퍼바이저 관리 권한 부여<br />
                        2. <strong>수집 항목:</strong> 성명, 사번/아이디, 비밀번호, 이메일 주소, 본사 담당 부서 정보<br />
                        3. <strong>처리 위탁:</strong> 전 가맹점 통합 AI 관제 모니터링 및 이상상황 긴급 알림 데이터 처리<br />
                        4. <strong>보유 및 이용 기간:</strong> 관리자 퇴사/보직해임 시까지 또는 관계 법령이 정한 일정 기간 보존
                      </p>
                    )}
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
              <div className="auth-select-box text-center">
                {role === ROLES.STORE_MANAGER ? '점주 (매장 관제)' : '본사 관리자 (슈퍼바이저)'}
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="storeIdSelect">
                {role === ROLES.STORE_MANAGER ? '담당 매장 선택' : '담당 관제 영역'}
              </label>
              {role === ROLES.STORE_MANAGER ? (
                <select
                  id="storeIdSelect"
                  value={storeId}
                  onChange={(e) => setStoreId(e.target.value)}
                  className="auth-select"
                >
                  <option value={STORES.DONGMYEONG}>매장 1 (동명점)</option>
                  <option value={STORES.SUWAN}>매장 2 (수완점)</option>
                </select>
              ) : (
                <div className="auth-select-box text-center">
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

            <div className="btn-row justify-center">
              <button type="submit" className="auth-submit-btn text-only-submit-btn">
                회원가입 완료 및 로그인
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
