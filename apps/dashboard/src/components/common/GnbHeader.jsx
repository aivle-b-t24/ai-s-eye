import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'

import { ROUTES } from '../../constants/routes'

const maskName = (name) => {
  if (!name) return ''
  const parts = name.split(' ')
  if (parts.length > 0 && parts[0].length >= 2) {
    const mainName = parts[0]
    let masked = ''
    if (mainName.length === 2) {
      masked = `${mainName[0]}*`
    } else {
      const mid = Math.floor(mainName.length / 2)
      masked = `${mainName.slice(0, mid)}*${mainName.slice(mid + 1)}`
    }
    parts[0] = masked
    return parts.join(' ')
  }
  return name
}

export default function GnbHeader({
  page,
  _loadStateOnly,
  _loading,
  user,
  needsOnboarding = false,
  onLogout,
  onOpenProfile,
}) {
  const navigate = useNavigate()

  const navClass = ({ isActive }) => `store-nav-link${isActive ? ' is-active' : ''}`

  return (
    <header className="gnb-header">
      <div
        className="brand-zone brand-zone-clickable"
        role="button"
        tabIndex={0}
        onClick={() => navigate(ROUTES.HOME)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') navigate(ROUTES.HOME)
        }}
        aria-label="메인 페이지로 이동"
        title="메인 페이지로 이동"
      >
        <span className="brand-badge">AI MONITORING SYSTEM</span>
        <h1 className="brand-title">AI&apos;s Eye</h1>
      </div>

      <nav className="store-nav" aria-label="매장 관리">
        <NavLink
          to={needsOnboarding ? ROUTES.ONBOARDING : ROUTES.DASHBOARD}
          className={({ isActive }) =>
            `store-nav-link${
              isActive || (needsOnboarding && page === 'onboarding') ? ' is-active' : ''
            }`
          }
        >
          대시보드
        </NavLink>
        <NavLink to={ROUTES.MENUS} className={navClass}>
          메뉴 &amp; 정책
        </NavLink>
        <NavLink to={ROUTES.SETTINGS} className={navClass}>
          설정
        </NavLink>
      </nav>

      <div className="header-actions">
        <div className="user-profile-badge">
          <span
            className="user-name clickable"
            onClick={onOpenProfile}
            title="프로필 상세정보 보기"
          >
            {maskName(user.name)}
          </span>
        </div>

        <div className="user-profile-badge">
          <button type="button" className="logout-btn" onClick={onLogout}>
            로그아웃
          </button>
        </div>
      </div>
    </header>
  )
}
