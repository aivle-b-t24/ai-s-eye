import React, { useState, useEffect, useRef } from 'react'
import { authenticatedFetch, currentIdToken } from '../../api/authenticatedFetch'
import { storeDisplayName } from '../../api/storeDirectory'
import { CHATBOT_BASE_URL } from '../../constants/env'

function renderBotText(text) {
  return (text || '').split('\n').map((line, i) => {
    const t = line.trim()
    if (t.startsWith('⚠️')) return <div key={i} className="chat-note">{t.replace(/^⚠️\s*/, '')}</div>
    if (t.startsWith('•')) return <div key={i} className="chat-bullet">{t}</div>
    if (t === '') return <div key={i} className="chat-gap" />
    return <div key={i} className="chat-line">{line}</div>
  })
}

export default function StoreChatbotWidget({ page, storeName }) {
  const resolvedStoreName = storeName || storeDisplayName(page)
  const [isOpen, setIsOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)

  // 📍 채팅 패널 높이(위쪽 가장자리 드래그로 조절). 아래가 고정이라 위로 끌면 커진다.
  const [panelHeight, setPanelHeight] = useState(620)
  const isResizing = useRef(false)
  const resizeStart = useRef({ y: 0, h: 620 })

  const handleResizeStart = (e) => {
    e.preventDefault()
    e.stopPropagation()
    isResizing.current = true
    resizeStart.current = { y: e.clientY, h: panelHeight }
    window.addEventListener('mousemove', handleResizeMove)
    window.addEventListener('mouseup', handleResizeEnd)
  }

  const handleResizeMove = (e) => {
    if (!isResizing.current) return
    // 위로 드래그(clientY 감소) = 높이 증가
    const delta = resizeStart.current.y - e.clientY
    const maxH = window.innerHeight - 60
    // 최소 = 처음(기본) 높이 620px. 그보다 작게는 안 줄고 더 크게만 조절된다.
    const next = Math.min(maxH, Math.max(620, resizeStart.current.h + delta))
    setPanelHeight(next)
  }

  const handleResizeEnd = () => {
    isResizing.current = false
    window.removeEventListener('mousemove', handleResizeMove)
    window.removeEventListener('mouseup', handleResizeEnd)
  }
  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: 'bot',
      text: '안녕하세요! AI 카페 매니저예요. 매장 운영시간, 품절 메뉴, 주차, 매장 현황 등 궁금하신 점을 편하게 질문해 주세요.',
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
  /* StoreChatbotWidget.jsx 89번 라인 handleToggleOpen 함수 수정 */
  const handleToggleOpen = (e) => {
    if (hasDragged.current) {
      e.preventDefault()
      e.stopPropagation()
      return
    }
    // 최소화(—)로 닫았다가 다시 열면 이전 대화를 그대로 유지한다(초기화 안 함).
    setIsOpen(!isOpen)
  }

  // 닫기(✕): 대화를 초기화하고 닫는다(다음에 열면 새 대화).
  const handleCloseReset = () => {
    setMessages([
      {
        id: Date.now(),
        sender: 'bot',
        text: '안녕하세요! AI 카페 매니저예요. 매장 운영시간, 품절 메뉴, 주차, 매장 현황 등 궁금하신 점을 편하게 질문해 주세요.',
        source: '',
        time: getCurrentTime(),
      },
    ])
    setIsOpen(false)
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
    if (!query.trim()) return

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

    /* const popupHtml 바로 위에 이 1줄 덩어리를 추가! */
    const existingMessagesHtml = messages
      .map((msg) => {
        const isUser = msg.sender === 'user'
        const textFormatted = (msg.text || '')
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/\n/g, '<br />')

        return `
          <div class="msg-row ${isUser ? 'user' : 'bot'}">
            ${!isUser ? '<div class="avatar">☕</div>' : ''}
            <div>
              <div class="msg-bubble">${textFormatted}</div>
            </div>
          </div>
        `
      })
      .join('')

    

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
      {/* 📍 플로팅 챗봇 트리거 버튼 — 패널이 열리면 숨긴다(추천버튼 위 겹침 클릭 방지) */}
      {!isOpen && (
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
      )}

      {/* 챗봇 대화 패널 */}
      {isOpen && (
        <div className="store-chatbot-panel" style={{ '--chat-h': `${panelHeight}px` }}>
          <div
            className="chatbot-resize-handle"
            onMouseDown={handleResizeStart}
            title="드래그해서 채팅 높이 조절"
          />
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
                className="chatbot-close-btn"
                onClick={() => setIsOpen(false)}
                title="최소화"
              >
                —
              </button>
              <button
                type="button"
                className="chatbot-close-btn"
                onClick={handleCloseReset}
                title="닫기"
              >
                ✕
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

          <div className="chat-quick-row">
            <button type="button" className="chat-suggestion-chip" onClick={() => handleSend('매장 운영 안내')}>매장 운영</button>
            <button type="button" className="chat-suggestion-chip" onClick={() => handleSend('품절 및 재고 안내')}>품절 재고</button>
            <button type="button" className="chat-suggestion-chip" onClick={() => handleSend('지금 매장 붐벼?')}>매장 현황</button>
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