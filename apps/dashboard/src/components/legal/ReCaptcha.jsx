import React, { useEffect, useRef } from 'react'

// 운영에서는 VITE_RECAPTCHA_SITE_KEY로 실제 사이트키를 주입한다.
// 기본값은 Google 공식 reCAPTCHA v2 테스트 사이트키(항상 통과, 안내 배너 표시).
const SITE_KEY =
  import.meta.env.VITE_RECAPTCHA_SITE_KEY || '6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI'

let scriptPromise = null
function loadRecaptchaScript() {
  if (scriptPromise) return scriptPromise
  scriptPromise = new Promise((resolve, reject) => {
    if (window.grecaptcha && window.grecaptcha.render) {
      resolve()
      return
    }
    const script = document.createElement('script')
    script.src = 'https://www.google.com/recaptcha/api.js?render=explicit'
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('reCAPTCHA 스크립트를 불러오지 못했습니다.'))
    document.head.appendChild(script)
  })
  return scriptPromise
}

/**
 * Google reCAPTCHA v2 위젯.
 * @param {(token: string) => void} onChange 토큰이 발급/만료될 때 호출(만료·오류 시 '')
 * @param {number} resetKey 값이 바뀌면 위젯을 리셋한다(가입 실패 후 재시도용)
 */
export default function ReCaptcha({ onChange, resetKey = 0 }) {
  const containerRef = useRef(null)
  const widgetIdRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    loadRecaptchaScript()
      .then(() => {
        const tryRender = () => {
          if (cancelled || !containerRef.current) return
          if (!window.grecaptcha || !window.grecaptcha.render) {
            setTimeout(tryRender, 100)
            return
          }
          if (widgetIdRef.current !== null || containerRef.current.childNodes.length) return
          widgetIdRef.current = window.grecaptcha.render(containerRef.current, {
            sitekey: SITE_KEY,
            callback: (token) => onChange(token),
            'expired-callback': () => onChange(''),
            'error-callback': () => onChange(''),
          })
        }
        tryRender()
      })
      .catch(() => onChange(''))
    return () => {
      cancelled = true
    }
    // onChange는 useState setter로 안정적이므로 최초 1회만 렌더한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (resetKey === 0) return
    if (widgetIdRef.current !== null && window.grecaptcha) {
      window.grecaptcha.reset(widgetIdRef.current)
      onChange('')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey])

  return <div className="recaptcha-box" ref={containerRef} />
}
