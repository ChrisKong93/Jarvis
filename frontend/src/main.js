import { createApp } from 'vue'
import App from './App.vue'
import './style.css'
import axios from 'axios'

// 请求拦截器：注入 JWT Token
axios.interceptors.request.use(config => {
  const token = localStorage.getItem('jarvis-token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：401 自动跳转登录（排除登录/注册接口）
const AUTH_ENDPOINTS = ['/api/auth/login', '/api/auth/register']
axios.interceptors.response.use(
  response => response,
  error => {
    if (error.response && error.response.status === 401) {
      const url = error.config?.url || ''
      // 排除登录/注册接口本身的 401
      const isAuthEndpoint = AUTH_ENDPOINTS.some(endpoint => url.startsWith(endpoint))
      if (!isAuthEndpoint) {
        localStorage.removeItem('jarvis-token')
        localStorage.removeItem('jarvis-username')
        localStorage.removeItem('jarvis-provider-id')
        localStorage.removeItem('jarvis-session-id')
        window.location.reload()
      }
    }
    return Promise.reject(error)
  }
)

createApp(App).mount('#app')
