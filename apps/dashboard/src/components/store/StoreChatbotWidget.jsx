import React, { useState, useEffect, useRef } from 'react'
import { authenticatedFetch, currentIdToken } from '../../api/authenticatedFetch'
import { storeDisplayName } from '../../api/storeDirectory'
import { CHATBOT_BASE_URL } from '../../constants/env'

function renderBotText(text) {
  return (text || '').split('\n').map((line, i) => {
    const t = line.trim()
    if (t.startsWith('⚠️')) return <div key={i} className="chat-note">{t}</div>
    if (t.startsWith('•')) return <div key={i} className="chat-bullet">{t}</div>
    if (t === '') return <div key={i} className="chat-gap" />
    return <div key={i} className="chat-line">{line}</div>
  })
}

export default function StoreChatbotWidget({ page, storeName }) {
  const resolvedStoreName = storeName || storeDisplayName(page)
  const [isOpen, setIsOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: 'bot',
      text: '안녕하세요! AI 카페 매니저예요. 매장 운영시간, 품절 메뉴, 주차, 실시간 관제 등 궁금하신 점을 편하게 질문해 주세요.',
      source: '',
      time: getCurrentTime(),
    },
  ])
  

  // 📍 1. 자유 위치 지정을 위한 좌표 State (초기 위치: 화면 좌측 하단)
  const [position, setPosition] = useState({
    x: 40,
    y: window.innerHeight - 120,
  })

  const isDragging = useRef(false)
  const dragStart = useRef({ x: 0, y: 0 })
  const hasDragged = useRef(false) // 드래그 여부 구분용

  // 📍 2. 마우스 누름 (드래그 시작)
  const handleMouseDown = (e) => {
    // input 입력창을 누를 때는 드래그하지 않음
    if (e.target.tagName === 'INPUT') return

    isDragging.current = true
    hasDragged.current = false // 초기화

    // 현재 포인터와 챗봇 위치 간의 차이 계산
    dragStart.current = {
      x: e.clientX - position.x,
      y: e.clientY - position.y,
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
  }

  // 📍 3. 마우스 이동 (실시간 좌표 갱신)
  const handleMouseMove = (e) => {
    if (!isDragging.current) return

    const newX = e.clientX - dragStart.current.x
    const newY = e.clientY - dragStart.current.y

    // 약간이라도 움직였으면 드래그 상태로 변경 (클릭으로 창 열리는 것 방지)
    if (Math.abs(newX - position.x) > 3 || Math.abs(newY - position.y) > 3) {
      hasDragged.current = true
    }

    // 화면(뷰포트) 바깥으로 넘어가가지 않게 범위 제한
    const maxX = window.innerWidth - 90
    const maxY = window.innerHeight - 90

    setPosition({
      x: Math.max(10, Math.min(newX, maxX)),
      y: Math.max(10, Math.min(newY, maxY)),
    })
  }

  // 📍 4. 마우스 뗌 (드래그 종료)
  const handleMouseUp = () => {
    isDragging.current = false
    window.removeEventListener('mousemove', handleMouseMove)
    window.removeEventListener('mouseup', handleMouseUp)
  }

  // 📍 5. 버튼 클릭 동작 (드래그 중일 때는 창이 열리지 않게 처리)
  const handleToggleOpen = (e) => {
    if (hasDragged.current) {
      e.preventDefault()
      e.stopPropagation()
      return
    }
    setIsOpen(!isOpen)
  }

  const [inputValue, setInputValue] = useState('')
  const messagesEndRef = useRef(null)

  function getCurrentTime() {
    const now = new Date()
    let hours = now.getHours()
    const minutes = now.getMinutes().toString().padStart(2, '0')
    const ampm = hours >= 12 ? '오후' : '오전'
    hours = hours % 12
    hours = hours ? hours : 12
    return `${ampm} ${hours}:${minutes}`
  }

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    if (isOpen) {
      scrollToBottom()
    }
  }, [messages, isOpen, isLoading])

  const handleSend = async (textToSend) => {
    const query = textToSend || inputValue
    if (!query.trim() || isLoading) return

    const activeStoreId = (page === 'store-002' || page === 'suwan' || page === 'sangmu') ? 'store-002' : 'store-001'

    const userMsg = {
      id: Date.now(),
      sender: 'user',
      text: query,
      time: getCurrentTime(),
    }

    setMessages((prev) => [...prev, userMsg])
    if (!textToSend) setInputValue('')
    setIsLoading(true)

    try {
      const endpoint = `${CHATBOT_BASE_URL.replace(/\/$/, '')}/chat`
      // 📍 [추가 위치 1] API 호출 직전에 대화 히스토리 가공
      const history = messages
        .filter((m) => m.id !== 1 && m.text) // 초기 인사 제외
        .slice(-6)                          // 최근 6개(3턴)만
        .map((m) => ({ 
          role: m.sender === 'user' ? 'user' : 'model', 
          text: m.text 
        }))
      const response = await authenticatedFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query, store_id: activeStoreId, history }),
      })

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`)

      const data = await response.json()
      const botMsg = {
        id: Date.now() + 1,
        sender: 'bot',
        text: data.answer || '답변을 가져올 수 없습니다.',
        source: data.source || '',
        suggestions: data.suggestions || [],
        time: getCurrentTime(),
      }
      setMessages((prev) => [...prev, botMsg])
    } catch (err) {
      console.error('Chatbot API Call Failed:', err)
      const errorMsg = {
        id: Date.now() + 1,
        sender: 'bot',
        text: '죄송합니다. 챗봇 서버(8100)와 통신 중 오류가 발생했습니다. 네트워크 연결을 확인해 주세요.',
        source: 'system_error',
        time: getCurrentTime(),
      }
      setMessages((prev) => [...prev, errorMsg])
    } finally {
      setIsLoading(false)
    }
  }

  const openExternalPopupWindow = async () => {
    const width = 450
    const height = 680
    const left = window.screen.width / 2 - width / 2
    const top = window.screen.height / 2 - height / 2
    const activeStoreId = page || 'store-001'
    const targetEndpoint = `${CHATBOT_BASE_URL.replace(/\/$/, '')}/chat`
    const token = await currentIdToken()

    const popupHtml = `
      <!DOCTYPE html>
      <html lang="ko">
      <head>
        <meta charset="UTF-8" />
        <title>AI's Eye 카페 매니저 - 독립 창 (${activeStoreId})</title>
        <style>
          * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Pretendard', 'Noto Sans KR', sans-serif; }
          body { background: #fdfbf7; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
          .header { background: #173f3a; color: white; padding: 14px 18px; display: flex; align-items: center; justify-content: space-between; font-weight: 700; border-bottom: 2px solid #316f68; }
          .header-title { display: flex; align-items: center; gap: 8px; font-size: 16px; }
          .hero-banner { background: #f4efe6; padding: 16px; text-align: center; border-bottom: 1px solid #e5ded3; }
          .mascot { width: 56px; height: 56px; background: #173f3a; border-radius: 50%; color: white; display: flex; align-items: center; justify-content: center; font-size: 28px; margin: 0 auto 8px; border: 2px solid #316f68; box-shadow: 0 4px 12px rgba(23, 63, 58, 0.2); }
          .welcome-title { font-size: 15px; font-weight: 800; color: #173f3a; margin-bottom: 4px; }
          .welcome-sub { font-size: 12px; color: #5c4b37; }
          .faq-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 12px; }
          .faq-btn { background: white; border: 1px solid #e2d8c9; border-radius: 10px; padding: 10px 6px; font-size: 11px; font-weight: 700; color: #2c1e16; cursor: pointer; transition: all 0.2s; }
          .faq-btn:hover { background: #173f3a; color: white; border-color: #173f3a; }
          .chat-area { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; background: #faf8f5; }
          .msg-row { display: flex; gap: 10px; align-items: flex-start; }
          .msg-row.user { justify-content: flex-end; }
          .avatar { width: 36px; height: 36px; background: #173f3a; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 18px; flex-shrink: 0; }
          .msg-bubble { max-width: 78%; padding: 10px 14px; border-radius: 14px; font-size: 13px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
          .msg-row.bot .msg-bubble { background: #eee9e0; color: #1f2937; border-top-left-radius: 2px; }
          .msg-row.user .msg-bubble { background: #173f3a; color: white; border-top-right-radius: 2px; }
          .input-area { background: white; padding: 12px 16px; border-top: 1px solid #e5ded3; display: flex; gap: 10px; align-items: center; }
          .input-area input { flex: 1; border: 1px solid #d8cdbe; border-radius: 20px; padding: 10px 16px; font-size: 13px; outline: none; }
          .send-btn { width: 38px; height: 38px; background: #173f3a; border: none; border-radius: 50%; color: white; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 16px; }
        </style>
      </head>
      <body>
        <div class="header">
          <div class="header-title"><span>☕</span> AI Cafe 매니저 (${activeStoreId})</div>
          <div><button onclick="window.close()" style="background:none;border:none;color:white;font-size:18px;cursor:pointer;">✕</button></div>
        </div>
        <div class="hero-banner">
          <div class="mascot">☕</div>
          <div class="welcome-title">안녕하세요! 저는 AI's Eye 카페 매니저예요!</div>
          <div class="welcome-sub">매장 운영시간, 품절 메뉴, 주차, AI 관제 현황을 알려드릴게요.</div>
        </div>
        <div class="chat-area" id="chatArea">
          <div class="msg-row bot">
            <div class="avatar">☕</div>
            <div>
              <div class="msg-bubble">안녕하세요! AI 카페 매니저예요. 궁금하신 내용을 질문해 주세요.</div>
            </div>
          </div>
        </div>
        <div class="input-area">
          <input type="text" id="userInput" placeholder="질문을 입력하세요..." onkeydown="if(event.key==='Enter') sendMsg()" />
          <button class="send-btn" onclick="sendMsg()">➤</button>
        </div>
      </body>
      </html>
    `

    const popup = window.open(
      '',
      'AICafeChatbotPopup',
      `width=${width},height=${height},left=${left},top=${top},scrollbars=yes,resizable=yes`
    )
    if (popup) {
      popup.document.write(popupHtml)
      popup.document.close()
      setIsOpen(false)
    }
  }

  return (
    <>
      {/* 📍 마우스 드래그가 가능한 플로팅 챗봇 트리거 버튼 */}
      <div
        className="store-chatbot-trigger-container"
        onMouseDown={handleMouseDown}
        
      >
        <div className="store-chatbot-speech-bubble">
          <span>카페 운영 질문 언제든 가능!</span>
          <div className="speech-arrow" />
        </div>
        <button
          type="button"
          className="store-chatbot-trigger-btn"
          onClick={handleToggleOpen}
          title="AI Cafe 챗봇 열기"
        >
          <div className="chatbot-icon-wrapper">
            <span className="chatbot-avatar-emoji">☕</span>
          </div>
          <span className="chatbot-btn-text">카페 매니저</span>
        </button>
      </div>

      {/* 챗봇 대화 패널 */}
      {isOpen && (
        <div className="store-chatbot-panel">
          <div className="chatbot-header">
            <div className="chatbot-header-left">
              <div className="chatbot-header-title">
                <span className="header-icon">☕</span>
                <span>AI Cafe 매니저 ({resolvedStoreName})</span>
              </div>
            </div>
            <div className="chatbot-header-right">
              <button
                type="button"
                className="chatbot-external-btn"
                onClick={openExternalPopupWindow}
                title="새 창으로 챗봇 열기"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                  <polyline points="15 3 21 3 21 9"></polyline>
                  <line x1="10" y1="14" x2="21" y2="3"></line>
                </svg>
              </button>
              <button
                type="button"
                className="chatbot-close-btn"
                onClick={() => setIsOpen(false)}
                title="닫기"
              >
                ✕
              </button>
            </div>
          </div>

          <div className="chatbot-hero-banner">
            <div className="mascot-circle">
              <span>☕</span>
            </div>
            <h4 className="hero-greeting">
              안녕하세요!<br />
              저는 AI's Eye <strong>카페 매니저</strong>예요!
            </h4>
            <p className="hero-subtext">
              매장 영업시간, 품절 메뉴, 주차, AI 관제 현황을 알려드릴게요.
            </p>

            <div className="faq-quick-grid">
              <button
                type="button"
                className="faq-quick-card"
                onClick={() => handleSend('매장 운영 안내')}
                disabled={isLoading}
              >
                <span className="faq-icon">📅</span>
                <span className="faq-label">매장 운영<br />안내</span>
              </button>

              <button
                type="button"
                className="faq-quick-card"
                onClick={() => handleSend('품절 및 재고 안내')}
                disabled={isLoading}
              >
                <span className="faq-icon">☕</span>
                <span className="faq-label">품절 재고<br />안내</span>
              </button>

              <button
                type="button"
                className="faq-quick-card"
                onClick={() => handleSend('AI 카메라 관제 가이드')}
                disabled={isLoading}
              >
                <span className="faq-icon">🤖</span>
                <span className="faq-label">AI 관제<br />가이드</span>
              </button>
            </div>
          </div>

          <div className="chatbot-messages-body">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`chat-message-row ${
                  msg.sender === 'user' ? 'is-user' : 'is-bot'
                }`}
              >
                {msg.sender === 'bot' && (
                  <div className="bot-avatar-small">
                    <span>☕</span>
                  </div>
                )}
                <div className="message-content-group">
                  
                  <div className="message-bubble-box">
                    {msg.sender === 'bot' ? renderBotText(msg.text) : msg.text}
                  </div>

                  <span className="message-time-stamp">{msg.time}</span>
                  {msg.suggestions?.length > 0 && (
                    <div className="chat-suggestions">
                      {msg.suggestions.map((s) => (
                        <button
                          key={s}
                          type="button"
                          className="chat-suggestion-chip"
                          onClick={() => handleSend(s)}
                          disabled={isLoading}
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                  
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="chat-message-row is-bot">
                <div className="bot-avatar-small">
                  <span>☕</span>
                </div>
                <div className="message-content-group">
                  <div className="message-bubble-box chatbot-loading-dots">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="chatbot-input-footer">
            <div className="input-box-wrapper">
              <input
                type="text"
                className="chatbot-text-input"
                placeholder="질문을 입력하세요."
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSend()
                }}
                // disabled={isLoading}
              />
              <button type="button" className="chat-bubble-mini-btn" title="자주 쓰는 표현">
                💬
              </button>
            </div>
            <button
              type="button"
              className="chatbot-send-btn"
              onClick={() => handleSend()}
              disabled={!inputValue.trim()}
              title="전송"
            >
              ➤
            </button>
          </div>
        </div>
      )}
    </>
  )
}