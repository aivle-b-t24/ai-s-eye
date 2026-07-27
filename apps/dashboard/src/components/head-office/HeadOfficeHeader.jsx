import { useEffect, useState } from 'react'

const NAVIGATION_ITEMS = [
  { id: 'hq-overview', label: '운영 개요' },
  { id: 'hq-stores', label: '가맹점 분석' },
  { id: 'hq-ai', label: 'AI 인사이트' },
]

const HEADER_SCROLL_OFFSET = 96

export default function HeadOfficeHeader({ user, onLogout }) {
  const [activeSection, setActiveSection] = useState('hq-overview')

  useEffect(() => {
    let animationFrameId = null

    const updateActiveSection = () => {
      animationFrameId = null
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

    updateActiveSection()
    window.addEventListener('scroll', scheduleUpdate, { passive: true })
    window.addEventListener('resize', scheduleUpdate)

    return () => {
      window.removeEventListener('scroll', scheduleUpdate)
      window.removeEventListener('resize', scheduleUpdate)
      if (animationFrameId !== null) {
        window.cancelAnimationFrame(animationFrameId)
      }
    }
  }, [])

  return (
    <header className="head-office-header">
      <div className="head-office-header-inner">
        <a className="head-office-brand" href="#hq-overview">
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
            <strong>{user?.name ?? '관리자'}</strong>
          </div>
          <button type="button" onClick={onLogout}>로그아웃</button>
        </div>
      </div>
    </header>
  )
}
