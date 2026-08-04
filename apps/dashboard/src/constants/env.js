// Centralized Environment Variables Configuration
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://100.86.5.67:8001'

export const AICC_BASE_URL =
  import.meta.env.VITE_AICC_BASE_URL ||
  import.meta.env.VITE_CHATBOT_BASE_URL ||
  import.meta.env.VITE_AICC_URL ||
  'http://100.86.5.67:8101'

export const CHATBOT_BASE_URL = AICC_BASE_URL
export const AICC_URL = AICC_BASE_URL

