import React from 'react'

export default function VisionMonitorPanel({ storeId }) {
  const isStore2 = storeId === 'store-002'

  const cameraName = isStore2 ? 'CAM 02' : 'CAM 01'
  const storeName = isStore2 ? '매장 2' : '매장 1'

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
    </article>
  )
}