import React, { useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export default function VisionMonitorPanel({ storeId }) {
  const isStore2 = storeId === 'store-002'

  const cameraName = isStore2 ? 'CAM 02' : 'CAM 01'
  const storeName = isStore2 ? '매장 2' : '매장 1'

  // 분석 이미지는 매장별 최신 1장을 백엔드가 서빙한다.
  // 계속 바뀌므로 2초마다 캐시 버스터(?t=)를 갱신해 새 이미지를 받는다.
  const [imgTick, setImgTick] = useState(() => Date.now())
  const [hasImage, setHasImage] = useState(true)

  useEffect(() => {
    const id = setInterval(() => setImgTick(Date.now()), 2000)
    return () => clearInterval(id)
  }, [])

  const imageUrl =
    `${API_BASE_URL}/api/stores/${storeId}/vision/latest?t=${imgTick}`

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

      <div className="vision-feed" style={{ position: 'relative', overflow: 'hidden' }}>
        {/* 실제 Vision 분석 이미지 (탐지 + 직원/대기 ROI) */}
        <img
          className="vision-feed-image"
          src={imageUrl}
          alt={`${storeName} 실시간 분석`}
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            display: hasImage ? 'block' : 'none',
          }}
          onError={() => setHasImage(false)}
          onLoad={() => setHasImage(true)}
        />

        <div className="vision-feed-toolbar">
          <span className="vision-camera-name">
            <i />
            {cameraName}
          </span>

          <span className="vision-camera-status">
            정상
          </span>
        </div>

        {!hasImage && (
          <div className="vision-detection vision-detection-two">
            <span>분석 이미지 대기 중</span>
          </div>
        )}

        <div className="vision-feed-footer">
          <span>● LIVE</span>
          <strong>{storeName} 실시간 분석 중</strong>
        </div>
      </div>
    </article>
  )
}
