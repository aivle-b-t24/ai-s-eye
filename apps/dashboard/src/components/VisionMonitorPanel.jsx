import React from 'react';

export default function VisionMonitorPanel() {
  return (
    <article className="panel video-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Vision Monitor</p>
          <h2>AI 비전 카메라 실시간 피드</h2>
        </div>
        <span className="status-tag active">Cam 01 • 1080p 60fps</span>
      </div>

      <div className="video-viewport">
        <div className="camera-overlay">
          <div className="cam-header">
            <span>[CAM-01] MAIN ENTRANCE & COUNTER</span>
            <span className="rec-dot">● REC</span>
          </div>
          <div className="zone-labels">
            <span className="zone-box box-counter">Zone: Counter (Active)</span>
            <span className="zone-box box-waiting">Zone: Waiting Line</span>
          </div>
        </div>
        <div className="video-placeholder-graphic">
          <div className="radar-grid"></div>
          <p>📹 AI 객체 바운딩 박스 & 동선 분석 활성화 중</p>
        </div>
      </div>
    </article>
  );
}
