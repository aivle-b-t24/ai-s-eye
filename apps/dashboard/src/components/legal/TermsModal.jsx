import React from 'react'
import { createPortal } from 'react-dom'

// 이용약관(요약본) — 표준 항목만 담은 간결한 버전. 상세 조항은 실제 운영 시 확장.
export function TermsBody() {
  return (
    <div className="privacy-body">
      <p className="privacy-intro">
        본 약관은 AI&apos;s Eye(이하 &quot;서비스&quot;)가 제공하는 매장 관제 서비스의 이용과 관련하여 서비스와 회원의
        권리·의무 및 책임사항을 규정합니다.
      </p>

      <p><strong>제1조 (목적)</strong> — 회원이 서비스를 이용함에 있어 필요한 조건과 절차, 서비스와 회원 간의 권리·의무를 정함을 목적으로 합니다.</p>

      <p><strong>제2조 (약관의 효력 및 변경)</strong> — 본 약관은 회원가입 시 동의함으로써 효력이 발생하며, 관련 법령의 범위 내에서 개정될 수 있습니다. 개정 시 적용일과 사유를 사전에 공지합니다.</p>

      <p><strong>제3조 (이용계약의 성립)</strong> — 회원가입 신청자가 약관에 동의하고 가입을 신청하면 서비스가 이를 승낙함으로써 이용계약이 성립합니다.</p>

      <p><strong>제4조 (회원의 의무)</strong> — 회원은 아이디·비밀번호를 제3자에게 노출되지 않도록 관리해야 하며, 타인의 정보 도용, 서비스 운영 방해, 법령·약관 위반 행위를 하여서는 안 됩니다.</p>

      <p><strong>제5조 (서비스 제공 및 변경)</strong> — 서비스는 연중무휴 제공을 원칙으로 하되, 시스템 점검·장애 등 불가피한 경우 일시 중단될 수 있으며 이 경우 사전 또는 사후에 공지합니다.</p>

      <p><strong>제6조 (개인정보 보호)</strong> — 회원의 개인정보는 관계 법령 및 서비스의 개인정보 처리방침에 따라 보호·처리됩니다.</p>

      <p><strong>제7조 (이용계약 해지)</strong> — 회원은 언제든지 탈퇴를 신청하여 이용계약을 해지할 수 있으며, 해지 시 관계 법령에 따른 보존 대상을 제외한 개인정보는 지체 없이 파기됩니다.</p>

      <p><strong>제8조 (면책 및 준거법)</strong> — 천재지변·회원의 귀책 등 서비스의 고의·과실 없이 발생한 손해에 대해서는 책임을 지지 않으며, 본 약관은 대한민국 법령에 따라 해석됩니다.</p>

      <p className="privacy-effective">본 약관은 2026년 8월 5일부터 시행합니다.</p>
    </div>
  )
}

export default function TermsModal({ open, onClose }) {
  if (!open) return null
  return createPortal(
    <div
      className="legal-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="이용약관"
      onClick={onClose}
    >
      <div className="legal-modal" onClick={(e) => e.stopPropagation()}>
        <div className="legal-modal-head">
          <h2>이용약관</h2>
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
        <TermsBody />
      </div>
    </div>,
    document.body,
  )
}
