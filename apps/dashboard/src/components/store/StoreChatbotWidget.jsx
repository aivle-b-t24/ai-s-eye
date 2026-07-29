import React, { useState, useEffect, useRef } from 'react'

export default function StoreChatbotWidget({ page }) {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState([
    {
      id: 1,
      sender: 'bot',
      text: '안녕하세요? AI Cafe 챗봇 서비스예요. 궁금하신 매장 운영 내용을 질문해 주세요.',
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
  }, [messages, isOpen])

  const handleSend = (textToSend) => {
    const query = textToSend || inputValue
    if (!query.trim()) return

    const userMsg = {
      id: Date.now(),
      sender: 'user',
      text: query,
      time: getCurrentTime(),
    }

    setMessages((prev) => [...prev, userMsg])
    if (!textToSend) setInputValue('')

    // Generate intelligent AI Cafe response
    setTimeout(() => {
      let botReply = '죄송해요, 문의하신 내용에 대한 답변을 준비 중입니다. 매장 설정 또는 본사 고객센터로 문의해 주세요.'
      
      const lower = query.toLowerCase()
      if (lower.includes('운영') || lower.includes('시간') || lower.includes('학사') || lower.includes('매장')) {
        botReply = '🏪 [매장 운영 안내]\n현재 동명점은 실시간 AI 관제 모드로 24시간 가동 중입니다. 기본 영업시간은 07:00 ~ 23:00 이며, 무인 관제 상태는 실시간 Polling(2s)으로 유지됩니다.'
      } else if (lower.includes('품절') || lower.includes('재고') || lower.includes('수강') || lower.includes('메뉴')) {
        botReply = '☕ [품절 및 재고 안내]\n현재 품절 발생 항목은 4개입니다. 대시보드 하단 [메뉴 관리] 패널에서 품절 상태를 바로 전환하실 수 있습니다.'
      } else if (lower.includes('카메라') || lower.includes('관제') || lower.includes('등록') || lower.includes('ai')) {
        botReply = '🤖 [AI 카메라 관제 안내]\nCAM 01 실시간 비전 센서가 대기열 및 근무 직원을 정밀 추적 중입니다. 화질 점검 및 이벤트 알림은 [관제 설정]에서 변경 가능합니다.'
      } else if (lower.includes('안녕') || lower.includes('반가')) {
        botReply = '안녕하세요! 점주님의 성공적인 매장 운영을 돕는 AI Cafe 챗봇입니다. 무엇을 도와드릴까요?'
      }

      const botMsg = {
        id: Date.now() + 1,
        sender: 'bot',
        text: botReply,
        time: getCurrentTime(),
      }
      setMessages((prev) => [...prev, botMsg])
    }, 600)
  }

  // Open external dedicated standalone popup window (matching image 1 & 3 [ ↗ ] button)
  const openExternalPopupWindow = () => {
    const width = 450
    const height = 680
    const left = window.screen.width / 2 - width / 2
    const top = window.screen.height / 2 - height / 2

    const popupHtml = `
      <!DOCTYPE html>
      <html lang="ko">
      <head>
        <meta charset="UTF-8" />
        <title>AI Cafe 챗봇 서비스 - 독립 창</title>
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
          .avatar { width: 36px; height: 36px; background: #004b8d; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 18px; }
          .msg-bubble { max-width: 75%; padding: 10px 14px; border-radius: 14px; font-size: 13px; line-height: 1.5; white-space: pre-wrap; }
          .msg-row.bot .msg-bubble { background: #e2e8f0; color: #0f172a; border-top-left-radius: 2px; }
          .msg-row.user .msg-bubble { background: #004b8d; color: white; border-top-right-radius: 2px; }
          .msg-time { font-size: 10px; color: #94a3b8; margin-top: 4px; align-self: flex-end; }
          .input-area { background: white; padding: 12px 16px; border-top: 1px solid #e2e8f0; display: flex; gap: 10px; align-items: center; }
          .input-area input { flex: 1; border: 1px solid #cbd5e1; border-radius: 20px; padding: 10px 16px; font-size: 13px; outline: none; }
          .send-btn { width: 38px; height: 38px; background: #9d174d; border: none; border-radius: 50%; color: white; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 16px; }
        </style>
      </head>
      <body>
        <div class="header">
          <div class="header-title"><span>🐱</span> AI Cafe 챗봇 서비스</div>
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
              <div class="msg-time">실시간 연동 중</div>
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
          function sendMsg() {
            const input = document.getElementById('userInput');
            const val = input.value.trim();
            if(!val) return;
            
            const chatArea = document.getElementById('chatArea');
            const userHtml = '<div class="msg-row user"><div><div class="msg-bubble">' + val + '</div></div></div>';
            chatArea.insertAdjacentHTML('beforeend', userHtml);
            input.value = '';
            chatArea.scrollTop = chatArea.scrollHeight;

            setTimeout(() => {
              let botReply = '답변을 준비 중입니다. 매장 대시보드에서 상세 현황을 확인하실 수 있습니다.';
              if (val.includes('운영')) botReply = '🏪 [매장 운영 안내] 현재 매장은 24시간 AI 관제 상태입니다.';
              else if (val.includes('품절')) botReply = '☕ [품절 안내] 하단 메뉴 관리 패널에서 품절 설정을 하실 수 있습니다.';
              else if (val.includes('카메라') || val.includes('관제')) botReply = '🤖 [AI 관제 안내] CAM 01 센서가 실시간 트래킹 중입니다.';

              const botHtml = '<div class="msg-row bot"><div class="avatar">🐱</div><div><div class="msg-bubble">' + botReply + '</div></div></div>';
              chatArea.insertAdjacentHTML('beforeend', botHtml);
              chatArea.scrollTop = chatArea.scrollHeight;
            }, 500);
          }
        </script>
      </body>
      </html>
    `

    const popup = window.open('', 'AICafeChatbotPopup', `width=${width},height=${height},left=${left},top=${top},scrollbars=yes,resizable=yes`)
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
                <span>AI Cafe 챗봇 서비스</span>
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
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
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
              >
                <span className="faq-icon">📅</span>
                <span className="faq-label">매장 운영<br />안내</span>
              </button>

              <button
                type="button"
                className="faq-quick-card"
                onClick={() => handleSend('품절 및 재고 안내')}
              >
                <span className="faq-icon">☕</span>
                <span className="faq-label">품절 재고<br />안내</span>
              </button>

              <button
                type="button"
                className="faq-quick-card"
                onClick={() => handleSend('AI 카메라 관제 가이드')}
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
                  </div>
                  <span className="message-time-stamp">{msg.time}</span>
                </div>
              </div>
            ))}
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
              />
              <button type="button" className="chat-bubble-mini-btn" title="자주 쓰는 표현">
                💬
              </button>
            </div>
            <button
              type="button"
              className="chatbot-send-btn"
              onClick={() => handleSend()}
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
