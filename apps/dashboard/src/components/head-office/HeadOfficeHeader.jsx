import { useEffect, useRef, useState } from 'react'

const NAVIGATION_ITEMS = [
  { id: 'hq-overview', label: '운영 개요' },
  { id: 'hq-stores', label: '가맹점 분석' },
  { id: 'hq-ai', label: 'AI 인사이트' },
]

const HEADER_SCROLL_OFFSET = 96
const PAGE_BOTTOM_THRESHOLD = 8
const SCROLL_SELECTION_HOLD_MS = 900

function getSectionFromHash() {
  if (typeof window === 'undefined') {
    return NAVIGATION_ITEMS[0].id
  }

  const hashSection = window.location.hash.replace('#', '')
  return NAVIGATION_ITEMS.some(({ id }) => id === hashSection)
    ? hashSection
    : NAVIGATION_ITEMS[0].id
}

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

export default function HeadOfficeHeader({ user, onLogout }) {

  const [activeSection, setActiveSection] = useState(getSectionFromHash)
  const navigationTargetRef = useRef(null)
  const selectionTimerRef = useRef(null)

  const holdActiveSection = (sectionId) => {
    navigationTargetRef.current = sectionId
    setActiveSection(sectionId)

    if (selectionTimerRef.current !== null) {
      window.clearTimeout(selectionTimerRef.current)
    }

    selectionTimerRef.current = window.setTimeout(() => {
      navigationTargetRef.current = null
      selectionTimerRef.current = null
    }, SCROLL_SELECTION_HOLD_MS)
  }

  useEffect(() => {
    let animationFrameId = null

    const updateActiveSection = () => {
      animationFrameId = null
      if (navigationTargetRef.current) {
        setActiveSection(navigationTargetRef.current)
        return
      }

      const scrollHeight = document.documentElement.scrollHeight
      const maxScrollTop = scrollHeight - window.innerHeight
      const isAtPageBottom = maxScrollTop > 0
        && window.scrollY >= maxScrollTop - PAGE_BOTTOM_THRESHOLD

      if (isAtPageBottom) {
        setActiveSection(NAVIGATION_ITEMS.at(-1).id)
        return
      }

      const marker = window.scrollY + HEADER_SCROLL_OFFSET
      let currentSection = NAVIGATION_ITEMS[0].id

      NAVIGATION_ITEMS.forEach(({ id }) => {
        const section = document.getElementById(id)
        if (!section) {
          return
        }

        const sectionTop = section.getBoundingClientRect().top + window.scrollY
        if (sectionTop <= marker) {
          currentSection = id
        }
      })

      setActiveSection(currentSection)
    }

    const scheduleUpdate = () => {
      if (animationFrameId === null) {
        animationFrameId = window.requestAnimationFrame(updateActiveSection)
      }
    }

    const hashSection = getSectionFromHash()
    if (window.location.hash) {
      navigationTargetRef.current = hashSection
      selectionTimerRef.current = window.setTimeout(() => {
        navigationTargetRef.current = null
        selectionTimerRef.current = null
      }, SCROLL_SELECTION_HOLD_MS)
    }

    updateActiveSection()
    window.addEventListener('scroll', scheduleUpdate, { passive: true })
    window.addEventListener('resize', scheduleUpdate)

    return () => {
      window.removeEventListener('scroll', scheduleUpdate)
      window.removeEventListener('resize', scheduleUpdate)
      if (animationFrameId !== null) {
        window.cancelAnimationFrame(animationFrameId)
      }
      if (selectionTimerRef.current !== null) {
        window.clearTimeout(selectionTimerRef.current)
      }
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
          href="#hq-overview"
          onClick={() => holdActiveSection('hq-overview')}
        >
          <span>AI&apos;s Eye</span>
          <strong>HQ OPERATIONS</strong>
        </a>




        <nav className="head-office-navigation" aria-label="본사 운영 메뉴">
          {NAVIGATION_ITEMS.map(({ id, label }) => {
            const isActive = activeSection === id

            return (
              <a
                key={id}
                href={`#${id}`}
                className={isActive ? 'is-active' : ''}
                aria-current={isActive ? 'location' : undefined}
                onClick={() => holdActiveSection(id)}
              >
                {label}
              </a>
            )
          })}
        </nav>

        <div className="head-office-user">
          <div>
            <span>본사 슈퍼바이저</span>
            <strong>{maskName(user?.name ?? '관리자')}</strong>
          </div>
          <button type="button" onClick={onLogout}>로그아웃</button>
        </div>
      </div>
    </header>
  )
}


