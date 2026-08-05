import React, { useEffect, useState } from 'react'
import { useAuthContext } from '../../auth/AuthContext'
import { isPasswordExpired } from '../../utils/password'

// 세션 동안 "다음에 하기"를 누른 계정은 다시 띄우지 않는다.
const DISMISS_PREFIX = 'aiseye.pwExpiryDismissed.'

export default function PasswordExpiryPrompt() {
  const { currentUser, handlePasswordReset } = useAuthContext()
  const [dismissed, setDismissed] = useState(false)
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const uid = currentUser?.uid

  useEffect(() => {
    setNotice('')
    if (!uid) {
      setDismissed(false)
      return
    }
    setDismissed(Boolean(sessionStorage.getItem(DISMISS_PREFIX + uid)))
  }, [uid])

  if (!currentUser || dismissed) return null
  if (!isPasswordExpired(currentUser.passwordChangedAt)) return null

  const later = () => {
    if (uid) sessionStorage.setItem(DISMISS_PREFIX + uid, '1')
    setDismissed(true)
  }

  const goChange = async () => {
    setBusy(true)
    setNotice('')
    try {
      await handlePasswordReset(currentUser.email)
      setNotice('비밀번호 재설정 메일을 보냈습니다. 메일의 링크에서 변경해 주세요.')
    } catch (error) {
      setNotice(error.message || '비밀번호 재설정 메일을 보내지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="legal-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="비밀번호 변경 안내"
    >
      <div className="legal-modal pw-expiry-modal">
        <div className="legal-modal-head">
          <h2>비밀번호 변경 안내</h2>
        </div>
        <p className="pw-expiry-text">
          보안을 위해 비밀번호는 180일(약 6개월)마다 변경하시길 권장합니다.
          마지막 변경 후 권장 주기가 지났습니다. 지금 변경하시겠어요?
        </p>
        {notice && <p className="pw-expiry-notice">{notice}</p>}
        <div className="pw-expiry-actions">
          <button type="button" className="auth-submit-btn" onClick={goChange} disabled={busy}>
            {busy ? '메일 발송 중...' : '비밀번호 변경하러 가기'}
          </button>
          <button type="button" className="pw-expiry-later" onClick={later} disabled={busy}>
            다음에 하기
          </button>
        </div>
      </div>
    </div>
  )
}
