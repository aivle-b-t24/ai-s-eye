import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  currentHqSection,
  HQ_NAVIGATION_ITEMS,
} from './hqNavigation'

const maskName = (name) => {
  if (!name) return ''
  const parts = name.split(' ')
  if (parts.length > 0 && parts[0].length >= 2) {
    const mainName = parts[0]
    let masked = ''
    if (mainName.length === 2) {
      masked = mainName[0] + '*'
    } else {
      const mid = Math.floor(mainName.length / 2)
      masked = mainName.slice(0, mid) + '*' + mainName.slice(mid + 1)
    }
    parts[0] = masked
    return parts.join(' ')
  }
  return name
}

export default function HeadOfficeHeader({ user, onLogout, onOpenProfile }) {

  const navigate = useNavigate()
  const [activeSection, setActiveSection] = useState(currentHqSection)

  useEffect(() => {
    const syncSection = () => setActiveSection(currentHqSection())
    syncSection()
    window.addEventListener('hashchange', syncSection)

    return () => {
      window.removeEventListener('hashchange', syncSection)
    }
  }, [])

  return (
    <header className="head-office-header">
      <button
        type="button"
        className="header-back-btn hq-back-btn"
        onClick={onLogout}
        aria-label="뒤로가기 (로그인 화면으로 이동)"
        title="로그인 화면으로 돌아가기"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="19" y1="12" x2="5" y2="12" />
          <polyline points="12 19 5 12 12 5" />
        </svg>
      </button>

      <div className="head-office-header-inner">
        <a
          className="head-office-brand"
          href="/"
          onClick={(e) => {
            e.preventDefault()
            navigate('/')
          }}
          aria-label="메인 페이지로 이동"
        >
          <strong>HQ OPERATIONS</strong>
          <span>AI&apos;s Eye</span>
        </a>




        <nav className="head-office-navigation" aria-label="본사 운영 메뉴">
          {HQ_NAVIGATION_ITEMS.map(({ id, label }) => {
            const isActive = activeSection === id

            return (
              <a
                key={id}
                href={`#${id}`}
                className={isActive ? 'is-active' : ''}
                aria-current={isActive ? 'page' : undefined}
                onClick={() => setActiveSection(id)}
              >
                {label}
              </a>
            )
          })}
        </nav>

        <div className="head-office-user">
          <div>
            <span>본사 슈퍼바이저</span>
            <strong
              className="clickable"
              onClick={onOpenProfile}
              title="프로필 상세정보 보기"
            >
              {maskName(user?.name ?? '관리자')}
            </strong>
          </div>
          <button type="button" onClick={onLogout}>로그아웃</button>
        </div>
      </div>
    </header>
  )
}
