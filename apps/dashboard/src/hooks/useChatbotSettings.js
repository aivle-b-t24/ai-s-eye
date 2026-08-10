import { useState } from 'react'

export function useChatbotSettings() {
  const [chatbotSettingsMap, setChatbotSettingsMap] = useState(() => {
    try {
      const saved = localStorage.getItem('aicafe_chatbot_settings_map')
      return saved ? JSON.parse(saved) : {}
    } catch {
      return {}
    }
  })

  const handleToggleChatbotForStore = (targetStoreId, enabled) => {
    setChatbotSettingsMap((prev) => {
      const next = { ...prev, [targetStoreId]: enabled }
      localStorage.setItem('aicafe_chatbot_settings_map', JSON.stringify(next))
      return next
    })
  }

  return {
    chatbotSettingsMap,
    handleToggleChatbotForStore,
  }
}
