import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { getLanguage, loadLanguage } from './i18n'
import './styles.css'
import './social.css'

// Load the visitor's dictionary (and the tiny English one) before the first
// render so nothing paints untranslated. If it cannot be fetched the app
// renders in English, which is the source text, rather than a blank page.
Promise.all([loadLanguage(getLanguage()), loadLanguage('en')]).then(() => {
  createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  )
})
