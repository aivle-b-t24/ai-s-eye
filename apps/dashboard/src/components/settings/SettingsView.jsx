import React, { useState } from 'react';
import RoiEditor from './RoiEditor';
import SceneEditor from './SceneEditor';
import CapacitySetting from './CapacitySetting';

export default function SettingsView({
  apiBaseUrl,
  setPage,
  storeId,
  isChatbotEnabled = true,
  onToggleChatbot,
}) {
  const [activeTab, setActiveTab] = useState('space');
  const [activeSpaceTab, setActiveSpaceTab] = useState('roi');

  return (
    <section className="setting-view">
      <div className="setting-header">
        <h2>⚙️ 대시보드 환경설정</h2>
        <button className="back-btn" onClick={() => setPage(storeId)}>
          ← [점주] 담당 매장 대시보드로 돌아가기
        </button>
      </div>

      <div className="setting-tabs" role="tablist" aria-label="설정 항목">
        <button
          type="button"
          id="setting-tab-space"
          role="tab"
          aria-selected={activeTab === 'space'}
          aria-controls="setting-panel-space"
          className={activeTab === 'space' ? 'active' : ''}
          onClick={() => setActiveTab('space')}
        >
          공간·카메라 설정
        </button>
        <button
          type="button"
          id="setting-tab-system"
          role="tab"
          aria-selected={activeTab === 'system'}
          aria-controls="setting-panel-system"
          className={activeTab === 'system' ? 'active' : ''}
          onClick={() => setActiveTab('system')}
        >
          시스템 정보
        </button>
      </div>

      {activeTab === 'space' && (
        <div
          id="setting-panel-space"
          role="tabpanel"
          aria-labelledby="setting-tab-space"
          className="setting-tab-content"
        >
          <div className="setting-section-intro">
            <div>
              <p className="eyebrow">STORE SPACE SETUP</p>
              <h3>공간·카메라 설정</h3>
              <p>CCTV 원본 화면에서 직원·대기·좌석·출입구 구역을 설정합니다.</p>
            </div>
            <ol>
              <li>ROI로 인원 판정 구역 설정</li>
              <li>테이블·카운터 장면 보정</li>
              <li>수용 인원 설정·저장</li>
            </ol>
          </div>

          <div className="space-setting-tabs" role="tablist" aria-label="공간 설정 종류">
            <button
              type="button"
              role="tab"
              aria-selected={activeSpaceTab === 'roi'}
              className={activeSpaceTab === 'roi' ? 'active' : ''}
              onClick={() => setActiveSpaceTab('roi')}
            >
              ROI·인원 판정
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeSpaceTab === 'scene'}
              className={activeSpaceTab === 'scene' ? 'active' : ''}
              onClick={() => setActiveSpaceTab('scene')}
            >
              디지털 트윈 장면
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activeSpaceTab === 'capacity'}
              className={activeSpaceTab === 'capacity' ? 'active' : ''}
              onClick={() => setActiveSpaceTab('capacity')}
            >
              수용 인원
            </button>
          </div>

          {activeSpaceTab === 'roi' ? (
            <RoiEditor apiBaseUrl={apiBaseUrl} storeId={storeId} />
          ) : activeSpaceTab === 'scene' ? (
            <SceneEditor apiBaseUrl={apiBaseUrl} storeId={storeId} />
          ) : (
            <CapacitySetting storeId={storeId} />
          )}
        </div>
      )}

      {activeTab === 'system' && (
        <div
          id="setting-panel-system"
          role="tabpanel"
          aria-labelledby="setting-tab-system"
          className="setting-tab-content"
        >
          <div className="panel setting-panel">
            <h3>시스템 및 폴링 정보</h3>
            <div className="setting-group">
              <label>API Base URL</label>
              <input type="text" value={apiBaseUrl} readOnly />
            </div>
            <div className="setting-group">
              <label>실시간 폴링 정책</label>
              <input type="text" value="매장 화면 진입 시 /state 단일 Polling (2초) | 본사/설정 진입 시 Polling 중지" readOnly />
            </div>

            {/* AI Chatbot Assistant ON/OFF Setting Toggle */}
            <div className="setting-group chatbot-setting-group">
              <label>
                AI 챗봇 어시스턴트 기능 ({storeId === 'store-001' ? '매장 1 (동명점)' : storeId === 'store-002' ? '매장 2 (상무점)' : storeId})
              </label>
              <div className="chatbot-toggle-wrapper">
                <div className="toggle-info-text">
                  <span className={`chatbot-badge ${isChatbotEnabled ? 'is-enabled' : 'is-disabled'}`}>
                    {isChatbotEnabled ? '🟢 ON (사용 중)' : '🔴 OFF (비활성화)'}
                  </span>
                  <span className="toggle-desc">
                    {storeId === 'store-001' ? '매장 1 (동명점)' : storeId === 'store-002' ? '매장 2 (상무점)' : storeId} 화면 전용 AI Cafe 챗봇 버튼 및 팝업 표시 설정
                  </span>
                </div>
                <button
                  type="button"
                  className={`chatbot-switch-btn ${isChatbotEnabled ? 'is-active' : ''}`}
                  onClick={() => onToggleChatbot && onToggleChatbot(!isChatbotEnabled)}
                  title={isChatbotEnabled ? '챗봇 끄기' : '챗봇 켜기'}
                >
                  <span className="switch-handle" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
