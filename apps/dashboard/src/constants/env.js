// Centralized Environment Variables Configuration
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export const CHATBOT_BASE_URL =
  import.meta.env.VITE_AICC_BASE_URL
  ?? import.meta.env.VITE_CHATBOT_BASE_URL
  ?? 'http://localhost:8100'
