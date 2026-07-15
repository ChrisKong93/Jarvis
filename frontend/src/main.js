import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import axios from 'axios'

axios.interceptors.request.use(config => {
  const token = localStorage.getItem('jarvis-token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

createApp(App).mount('#app')
