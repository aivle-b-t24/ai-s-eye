import { getApp, getApps, initializeApp } from 'firebase/app'
import { getAuth } from 'firebase/auth'

import { IS_LOCAL_AUTH_MODE } from './auth/runtimeAuth'

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}

let firebaseAuth = null

if (!IS_LOCAL_AUTH_MODE) {
  const missingKeys = Object.entries(firebaseConfig)
    .filter(([, value]) => !value)
    .map(([key]) => key)

  if (missingKeys.length > 0) {
    throw new Error(`Firebase 설정이 없습니다: ${missingKeys.join(', ')}`)
  }

  const firebaseApp = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig)
  firebaseAuth = getAuth(firebaseApp)
}

export { firebaseAuth }
