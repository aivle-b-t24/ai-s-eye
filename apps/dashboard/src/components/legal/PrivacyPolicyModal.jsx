import React from 'react'

// 개인정보 처리방침 전문 — 회원가입 폼과 공개 링크가 같은 내용을 공유한다(단일 출처).
export function PrivacyPolicyBody() {
  return (
    <div className="privacy-body">
      <p className="privacy-intro">
        AI&apos;s Eye(이하 &quot;서비스&quot;)는 「개인정보 보호법」 제30조에 따라 정보주체의 개인정보를 보호하고
        관련 고충을 신속히 처리하기 위하여 다음과 같이 개인정보 처리방침을 수립·공개합니다.
      </p>

      <p><strong>제1조 (처리 목적)</strong> — 회원 식별·인증, 본사 관리자 계정 관리 및 매장 관제 서비스 제공을 위해 개인정보를 처리하며, 목적 외 용도로 이용하지 않습니다.</p>

      <p><strong>제2조 (수집 항목 및 보유기간)</strong></p>
      <table className="consent-table">
        <tbody>
          <tr><th>필수 항목</th><td>이메일, 비밀번호, 담당자명, 회사(프랜차이즈)명</td></tr>
          <tr><th>자동 수집</th><td>접속 로그, 쿠키, 기기·브라우저 정보</td></tr>
          <tr><th>보유기간</th><td>회원 탈퇴 시까지 (관계 법령에 규정이 있는 경우 해당 기간)</td></tr>
        </tbody>
      </table>

      <p><strong>제3조 (파기 절차·방법)</strong> — 보유기간 경과·처리목적 달성 시 지체 없이 파기합니다. 전자적 파일은 복구 불가능한 방식으로 삭제하고, 출력물은 분쇄·소각합니다.</p>

      <p><strong>제4조 (제3자 제공)</strong> — 정보주체의 동의 또는 법령에 근거한 경우를 제외하고 개인정보를 제3자에게 제공하지 않습니다.</p>

      <p><strong>제5조 (처리 위탁)</strong> — 회원 인증 처리를 위해 Google Firebase Authentication을 이용하며, 수탁자가 개인정보를 안전하게 처리하도록 관리·감독합니다.</p>

      <p><strong>제6조 (정보주체의 권리)</strong> — 언제든지 개인정보의 열람·정정·삭제·처리정지를 요구할 수 있으며, 수집·이용 동의를 거부할 권리가 있습니다(거부 시 회원가입이 제한될 수 있습니다).</p>

      <p><strong>제7조 (안전성 확보조치)</strong> — 비밀번호는 일방향 암호화하여 저장하고 모든 통신은 HTTPS로 암호화합니다. 비밀번호는 180일마다 변경을 권장하고, 로그인 반복 실패 시 일시 잠금·reCAPTCHA로 접근을 통제하며, 개인정보 조회·출력 시 마스킹 처리합니다.</p>

      <p><strong>제8조 (쿠키 등 자동 수집장치)</strong> — 맞춤 서비스 제공을 위해 쿠키를 사용할 수 있으며, 정보주체는 브라우저 설정에서 쿠키 저장을 거부할 수 있습니다.</p>

      <p>
        <strong>제9조 (개인정보 보호책임자)</strong> — AI&apos;s Eye 운영팀 (AIVLE 24조), 문의:
        {' '}AI&apos;s Eye@aivle.kt
      </p>

      <p><strong>제10조 (권익침해 구제방법)</strong> — 개인정보분쟁조정위원회(1833-6972, kopico.go.kr), 개인정보침해신고센터(국번없이 118, privacy.kisa.or.kr) 등에 분쟁 해결 및 상담을 신청할 수 있습니다.</p>

      <p className="privacy-effective">본 방침은 2026년 8월 5일부터 적용됩니다.</p>
    </div>
  )
}

export default function PrivacyPolicyModal({ open, onClose }) {
  if (!open) return null
  return (
    <div
      className="legal-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="개인정보 처리방침"
      onClick={onClose}
    >
      <div className="legal-modal" onClick={(e) => e.stopPropagation()}>
        <div className="legal-modal-head">
          <h2>개인정보 처리방침</h2>
          <button
            type="button"
            className="legal-modal-close"
            onClick={onClose}
            aria-label="닫기"
            title="닫기"
          >
            ✕
          </button>
        </div>
        <PrivacyPolicyBody />
      </div>
    </div>
  )
}
