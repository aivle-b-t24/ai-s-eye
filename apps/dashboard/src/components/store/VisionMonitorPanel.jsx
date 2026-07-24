import React from 'react'

export default function VisionMonitorPanel({ storeId }) {
  const isStore2 = storeId === 'store-002'

  const cameraName = isStore2 ? 'CAM 02' : 'CAM 01'
  const storeName = isStore2 ? '매장 2' : '매장 1'

  const events = [
    {
      id: 1,
      type: 'entry',
      label: '입장 감지',
      value: '+3명',
      time: '09:43:10',
    },
    {
      id: 2,
      type: 'exit',
      label: '퇴장 감지',
      value: '-1명',
      time: '09:42:58',
    },
    {
      id: 3,
      type: 'waiting',
      label: '대기열 증가',
      value: '+2명',
      time: '09:42:45',
    },
  ]

  return (
    <article className="vision-card">
      <header className="vision-card-header">
        <div>
          <p className="eyebrow">AI Camera</p>
          <h2>실시간 카메라 모니터링</h2>
        </div>

        <button type="button" className="vision-more-button">
          전체 보기
          <span>→</span>
        </button>
      </header>

      <div className="vision-feed">
        <div className="vision-feed-toolbar">
          <span className="vision-camera-name">
            <i />
            {cameraName}
          </span>

          <span className="vision-camera-status">
            정상
          </span>
        </div>

        <div className="vision-detection vision-detection-one">
          <span>PERSON 01</span>
        </div>

        <div className="vision-detection vision-detection-two">
          <span>PERSON 02</span>
        </div>

        <div className="vision-detection vision-detection-three">
          <span>WAITING</span>
        </div>

        <div className="vision-feed-footer">
          <span>● LIVE</span>
          <strong>{storeName} 실시간 분석 중</strong>
        </div>
      </div>

      <section className="vision-events">
        <div className="vision-events-heading">
          <strong>최근 감지 이벤트</strong>
          <span>최근 30초</span>
        </div>

        <div className="vision-event-list">
          {events.map((event) => (
            <div
              key={event.id}
              className={`vision-event vision-event-${event.type}`}
            >
              <span className="vision-event-icon">
                {event.type === 'entry'
                  ? '↑'
                  : event.type === 'exit'
                    ? '↓'
                    : '○'}
              </span>

              <span className="vision-event-label">
                {event.label}
              </span>

              <strong>{event.value}</strong>
              <time>{event.time}</time>
            </div>
          ))}
        </div>
      </section>
    </article>
  )
}