import React, { useState } from 'react'
import PrivacyPolicyModal from './PrivacyPolicyModal'
import TermsModal from './TermsModal'

// 개인정보 처리방침 · 이용약관을 여는 공통 푸터. 여러 화면에서 재사용한다.
export default function LegalFooter({ className = '' }) {
  const [privacyOpen, setPrivacyOpen] = useState(false)
  const [termsOpen, setTermsOpen] = useState(false)

  return (
    <footer className={`legal-footer ${className}`.trim()}>
      <button
        type="button"
        className="footer-legal-link"
        onClick={() => setPrivacyOpen(true)}
      >
        개인정보 처리방침
      </button>
      <span className="legal-sep" aria-hidden="true">|</span>
      <button
        type="button"
        className="footer-legal-link"
        onClick={() => setTermsOpen(true)}
      >
        이용약관
      </button>
      <span className="legal-sep" aria-hidden="true">|</span>
      <span className="legal-copy">© 2026 AI&apos;s Eye. All rights reserved.</span>

      <PrivacyPolicyModal open={privacyOpen} onClose={() => setPrivacyOpen(false)} />
      <TermsModal open={termsOpen} onClose={() => setTermsOpen(false)} />
    </footer>
  )
}
