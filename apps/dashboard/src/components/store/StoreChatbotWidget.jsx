import React, { useState, useEffect, useRef } from 'react'

const CHATBOT_BASE_URL =
  import.meta.env.VITE_CHATBOT_BASE_URL ?? 'http://100.86.5.67:8100'

export default function StoreChatbotWidget({ page }) {
  const [isOpen, setIsOpen] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: 'bot',
      text: '안녕하세요? AI Cafe 챗봇 서비스예요. 궁금하신 매장 운영 내용을 질문해 주세요.',
      source: '',
      time: getCurrentTime(),
    },
  ])
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

  // Real Chatbot API Call (POST ${VITE_CHATBOT_BASE_URL}/chat)
  const handleSend = async (textToSend) => {
    const query = textToSend || inputValue
    if (!query.trim() || isLoading) return

    const activeStoreId = page || 'store-001'

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
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: query,
          store_id: activeStoreId,
        }),
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      const botMsg = {
        id: Date.now() + 1,
        sender: 'bot',
        text: data.answer || '답변을 가져올 수 없습니다.',
        source: data.source || '',
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

  // Open external dedicated standalone popup window (matching image 1 & 3 [ ↗ ] button)
  const openExternalPopupWindow = () => {
    const width = 450
    const height = 680
    const left = window.screen.width / 2 - width / 2
    const top = window.screen.height / 2 - height / 2
    const activeStoreId = page || 'store-001'
    const targetEndpoint = `${CHATBOT_BASE_URL.replace(/\/$/, '')}/chat`

    const popupHtml = `
      <!DOCTYPE html>
      <html lang="ko">
      <head>
        <meta charset="UTF-8" />
        <title>AI Cafe 챗봇 서비스 - 독립 창 (${activeStoreId})</title>
        <style>
          * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Pretendard', 'Noto Sans KR', sans-serif; }
          body { background: #eef3f6; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
          .header { background: #004b8d; color: white; padding: 14px 18px; display: flex; align-items: center; justify-content: space-between; font-weight: 700; }
          .header-title { display: flex; align-items: center; gap: 8px; font-size: 16px; }
          .hero-banner { background: #d9e5f3; padding: 16px; text-align: center; border-bottom: 1px solid #c8d8ea; }
          .mascot { width: 64px; height: 64px; background: #004b8d; border-radius: 50%; color: white; display: flex; align-items: center; justify-content: center; font-size: 32px; margin: 0 auto 8px; }
          .welcome-title { font-size: 15px; font-weight: 800; color: #003366; margin-bottom: 4px; }
          .welcome-sub { font-size: 12px; color: #4a5568; }
          .faq-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 12px; }
          .faq-btn { background: white; border: 1px solid #cbd5e1; border-radius: 10px; padding: 10px 6px; font-size: 11px; font-weight: 700; color: #1e293b; cursor: pointer; transition: all 0.2s; }
          .faq-btn:hover { background: #004b8d; color: white; border-color: #004b8d; }
          .chat-area { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; background: #f8fafc; }
          .msg-row { display: flex; gap: 10px; align-items: flex-start; }
          .msg-row.user { justify-content: flex-end; }
          .avatar { width: 36px; height: 36px; background: #004b8d; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 18px; flex-shrink: 0; }
          .msg-bubble { max-width: 78%; padding: 10px 14px; border-radius: 14px; font-size: 13px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
          .msg-row.bot .msg-bubble { background: #e2e8f0; color: #0f172a; border-top-left-radius: 2px; }
          .msg-row.user .msg-bubble { background: #004b8d; color: white; border-top-right-radius: 2px; }
          .source-tag { font-size: 10px; color: #047857; margin-top: 4px; font-weight: 700; background: #d1fae5; padding: 2px 6px; border-radius: 4px; display: inline-block; }
          .msg-time { font-size: 10px; color: #94a3b8; margin-top: 4px; align-self: flex-end; }
          .input-area { background: white; padding: 12px 16px; border-top: 1px solid #e2e8f0; display: flex; gap: 10px; align-items: center; }
          .input-area input { flex: 1; border: 1px solid #cbd5e1; border-radius: 20px; padding: 10px 16px; font-size: 13px; outline: none; }
          .send-btn { width: 38px; height: 38px; background: #9d174d; border: none; border-radius: 50%; color: white; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 16px; }
        </style>
      </head>
      <body>
        <div class="header">
          <div class="header-title"><span>🐱</span> AI Cafe 챗봇 서비스 (${activeStoreId})</div>
          <div><button onclick="window.close()" style="background:none;border:none;color:white;font-size:18px;cursor:pointer;">✕</button></div>
        </div>
        <div class="hero-banner">
          <div class="mascot">🐱</div>
          <div class="welcome-title">안녕하세요! 저는 AI Cafe 마스코트 아이봇이에요!</div>
          <div class="welcome-sub">궁금하신 매장 운영 내용을 편하게 질문해 주세요.</div>
          <div class="faq-grid">
            <button class="faq-btn" onclick="sendFaq('매장 운영 안내')">📅 매장 운영<br/>안내</button>
            <button class="faq-btn" onclick="sendFaq('품절 및 재고 안내')">☕ 품절 재고<br/>안내</button>
            <button class="faq-btn" onclick="sendFaq('AI 카메라 관제')">🤖 AI 관제<br/>가이드</button>
          </div>
        </div>
        <div class="chat-area" id="chatArea">
          <div class="msg-row bot">
            <div class="avatar">🐱</div>
            <div>
              <div class="msg-bubble">안녕하세요? AI Cafe 챗봇 서비스예요. 궁금하신 내용을 질문해 주세요.</div>
              <div class="msg-time">실시간 연동 가동 중</div>
            </div>
          </div>
        </div>
        <div class="input-area">
          <input type="text" id="userInput" placeholder="질문을 입력하세요..." onkeydown="if(event.key==='Enter') sendMsg()" />
          <button class="send-btn" onclick="sendMsg()">➤</button>
        </div>
        <script>
          function sendFaq(text) {
            document.getElementById('userInput').value = text;
            sendMsg();
          }
          async function sendMsg() {
            const input = document.getElementById('userInput');
            const val = input.value.trim();
            if(!val) return;
            
            const chatArea = document.getElementById('chatArea');
            const userHtml = '<div class="msg-row user"><div><div class="msg-bubble">' + val + '</div></div></div>';
            chatArea.insertAdjacentHTML('beforeend', userHtml);
            input.value = '';
            chatArea.scrollTop = chatArea.scrollHeight;

            const loadingId = 'loading-' + Date.now();
            const loadingHtml = '<div class="msg-row bot" id="' + loadingId + '"><div class="avatar">🐱</div><div><div class="msg-bubble">답변을 생성 중입니다...</div></div></div>';
            chatArea.insertAdjacentHTML('beforeend', loadingHtml);
            chatArea.scrollTop = chatArea.scrollHeight;

            try {
              const res = await fetch('${targetEndpoint}', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: val, store_id: '${activeStoreId}' })
              });

              const loader = document.getElementById(loadingId);
              if(loader) loader.remove();

              if(!res.ok) throw new Error('HTTP ' + res.status);
              const data = await res.json();

              let sourceHtml = '';
              if (data.source) {
                sourceHtml = '<br/><span class="source-tag">📌 출처: ' + data.source + '</span>';
              }
              const botHtml = '<div class="msg-row bot"><div class="avatar">🐱</div><div><div class="msg-bubble">' + (data.answer || '답변을 가져올 수 없습니다.') + sourceHtml + '</div></div></div>';
              chatArea.insertAdjacentHTML('beforeend', botHtml);
              chatArea.scrollTop = chatArea.scrollHeight;
            } catch(err) {
              const loader = document.getElementById(loadingId);
              if(loader) loader.remove();
              const errHtml = '<div class="msg-row bot"><div class="avatar">🐱</div><div><div class="msg-bubble" style="color:#b91c1c;">챗봇 서버(8100)와 통신 중 오류가 발생했습니다.</div></div></div>';
              chatArea.insertAdjacentHTML('beforeend', errHtml);
              chatArea.scrollTop = chatArea.scrollHeight;
            }
          }
        </script>
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
      {/* Floating Trigger Button on Bottom Left (Position Fixed, follows scroll) */}
      <div className="store-chatbot-trigger-container">
        <div className="store-chatbot-speech-bubble">
          <span>궁금한 걸 물어봐!</span>
          <div className="speech-arrow" />
        </div>
        <button
          type="button"
          className="store-chatbot-trigger-btn"
          onClick={() => setIsOpen(!isOpen)}
          title="AI Cafe 챗봇 열기"
        >
          <div className="chatbot-icon-wrapper">
            <span className="chatbot-avatar-emoji">🐱</span>
          </div>
          <span className="chatbot-btn-text">JBNU 챗봇</span>
        </button>
      </div>

      {/* Floating Chatbot Widget Panel on Bottom Right */}
      {isOpen && (
        <div className="store-chatbot-panel">
          {/* Header */}
          <div className="chatbot-header">
            <div className="chatbot-header-left">
              <button type="button" className="chatbot-menu-btn" title="메뉴">
                ☰
              </button>
              <div className="chatbot-header-title">
                <span className="header-icon">🐱</span>
                <span>AI Cafe 챗봇 서비스 ({page || 'store-001'})</span>
              </div>
            </div>
            <div className="chatbot-header-right">
              {/* External New Window Popup Button (Matching Image 1 & 3) */}
              <button
                type="button"
                className="chatbot-external-btn"
                onClick={openExternalPopupWindow}
                title="새 창으로 챗봇 열기"
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
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

          {/* Hero Greeting & Mascot Banner (Matching Image 2 & 3) */}
          <div className="chatbot-hero-banner">
            <div className="mascot-circle">
              <span>🐱</span>
            </div>
            <h4 className="hero-greeting">
              안녕하세요!<br />
              저는 AI Cafe <strong>마스코트 아이봇</strong>이에요!
            </h4>
            <p className="hero-subtext">
              "자주하는 질문 모음"을 누르시면 FAQ를 빠르게 확인하실 수 있어요.
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

          {/* Chat Messages Container */}
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
                    <span>🐱</span>
                  </div>
                )}

                <div className="message-content-group">
                  <div className="message-bubble-box">
                    {msg.text}
                    {msg.source && msg.source !== 'system_error' && (
                      <div className="message-source-tag">
                        📌 출처: {msg.source}
                      </div>
                    )}
                  </div>
                  <span className="message-time-stamp">{msg.time}</span>
                </div>
              </div>
            ))}

            {/* Loading Typing Dots Indicator */}
            {isLoading && (
              <div className="chat-message-row is-bot">
                <div className="bot-avatar-small">
                  <span>🐱</span>
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

          {/* Input Footer Area */}
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
                disabled={isLoading}
              />
              <button type="button" className="chat-bubble-mini-btn" title="자주 쓰는 표현">
                💬
              </button>
            </div>
            <button
              type="button"
              className="chatbot-send-btn"
              onClick={() => handleSend()}
              disabled={isLoading || !inputValue.trim()}
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
