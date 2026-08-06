import React from 'react'

const ICONS = {
  eye: (
    <>
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  trend: (
    <>
      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
      <polyline points="17 6 23 6 23 12" />
    </>
  ),
  chat: (
    <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
  ),
  grid: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
    </>
  ),
}

function Icon({ name }) {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICONS[name]}
    </svg>
  )
}

const FEATURES = [
  {
    icon: 'eye',
    title: '실시간 인원·혼잡도 관제',
    desc: '매장 카메라 영상에서 방문 인원과 대기열을 비전 AI가 실시간으로 감지합니다.',
  },
  {
    icon: 'trend',
    title: '혼잡·대기 예측',
    desc: '수용 인원 대비 혼잡도와 진행 중 주문(backlog)으로 대기 팀 수를 추정합니다.',
  },
  {
    icon: 'chat',
    title: '카카오 챗봇 응대',
    desc: '“지금 붐비나요?”, “얼마나 기다려요?” 같은 문의에 챗봇이 실시간으로 답합니다.',
  },
  {
    icon: 'grid',
    title: '본사 통합 대시보드',
    desc: '여러 매장을 한 화면에서 모니터링하고 매장·점주 계정 발급까지 관리합니다.',
  },
]

const STEPS = [
  { no: '01', title: '연동 & 온보딩', desc: '매장 카메라를 연동하고 메뉴·정책 등 매장 정보를 등록합니다.' },
  { no: '02', title: '실시간 관제', desc: '혼잡도·대기·품질 상태를 대시보드에서 실시간으로 확인합니다.' },
  { no: '03', title: '고객 응대', desc: '수집한 정보로 카카오 챗봇이 손님 문의에 자동으로 응답합니다.' },
]

const VALUE = [
  {
    tag: '점주',
    featured: false,
    items: [
      '실시간 매장 상황을 한눈에 파악',
      '대기·혼잡 관리로 응대 타이밍 확보',
      '반복 문의는 챗봇이 자동 응대',
    ],
  },
  {
    tag: '본사',
    featured: true,
    items: [
      '다매장을 하나의 대시보드로 통합 모니터링',
      '매장·점주 계정 발급 및 관리',
      '데이터 기반의 운영 판단 지원',
    ],
  },
]

const STATS = [
  { value: '94%', label: '추적 정확도 (IDF1)' },
  { value: '5초 이내', label: '챗봇 응답' },
  { value: '실시간', label: '혼잡도 관제' },
  { value: '다매장', label: '본사 통합' },
]

export default function ServiceIntro() {
  return (
    <section className="landing-intro" aria-label="서비스 소개">
      <div className="intro-glow intro-glow-a" aria-hidden="true" />
      <div className="intro-glow intro-glow-b" aria-hidden="true" />

      {/* ① 핵심 기능 */}
      <div className="intro-block">
        <span className="intro-eyebrow">WHAT WE DO</span>
        <h2 className="intro-heading">매장 운영을 데이터로 바꾸는 4가지</h2>
        <p className="intro-sub">카메라 한 대로 시작해, 관제부터 고객 응대까지 하나로 이어집니다.</p>
        <div className="intro-feature-grid">
          {FEATURES.map((f) => (
            <article className="intro-feature-card" key={f.title}>
              <span className="intro-feature-badge">
                <Icon name={f.icon} />
              </span>
              <h3>{f.title}</h3>
              <p>{f.desc}</p>
            </article>
          ))}
        </div>
      </div>

      {/* ② 이용 흐름 */}
      <div className="intro-block">
        <span className="intro-eyebrow">HOW IT WORKS</span>
        <h2 className="intro-heading">3단계로 시작합니다</h2>
        <div className="intro-steps">
          <div className="intro-steps-line" aria-hidden="true" />
          {STEPS.map((s) => (
            <div className="intro-step" key={s.no}>
              <span className="intro-step-node">{s.no}</span>
              <h3>{s.title}</h3>
              <p>{s.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* ③ 대상별 가치 */}
      <div className="intro-block">
        <span className="intro-eyebrow">FOR YOU</span>
        <h2 className="intro-heading">점주와 본사, 각자에게 맞게</h2>
        <div className="intro-value-grid">
          {VALUE.map((v) => (
            <div
              className={`intro-value-card ${v.featured ? 'is-featured' : ''}`}
              key={v.tag}
            >
              <span className="intro-value-tag">{v.tag}</span>
              <ul>
                {v.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      {/* ④ 수치 */}
      <div className="intro-stat-band">
        {STATS.map((s) => (
          <div className="intro-stat" key={s.label}>
            <strong>{s.value}</strong>
            <span>{s.label}</span>
          </div>
        ))}
      </div>
      <p className="intro-stats-note">* 내부 측정·데모 기준 수치입니다.</p>
    </section>
  )
}
