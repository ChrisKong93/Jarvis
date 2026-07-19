<script setup>
import { ref, watch, onMounted, computed, provide } from 'vue'
import ChatPanel from '@/components/ChatPanel.vue'
import MCPServerPage from '@/components/MCPServerPage.vue'
import SidebarLeft from '@/components/SidebarLeft.vue'
import SidebarRight from '@/components/SidebarRight.vue'
import LoginPage from '@/components/LoginPage.vue'
import PluginPage from '@/components/PluginPage.vue'
import SettingsPage from '@/components/SettingsPage.vue'
import ToastNotification from '@/components/ToastNotification.vue'
import axios from 'axios'

// ---- Toast 通知系统 ----
const toasts = ref([])
let toastId = 0

const addToast = (message, type = 'error', duration = 5000) => {
  const id = ++toastId
  toasts.value.push({ id, message, type })
  if (duration > 0) {
    setTimeout(() => {
      toasts.value = toasts.value.filter(t => t.id !== id)
    }, duration)
  }
}

const removeToast = (id) => {
  toasts.value = toasts.value.filter(t => t.id !== id)
}

// 全局 provide，子组件可通过 inject('addToast') 使用
provide('addToast', addToast)

const activePage = ref('chat')
const currentMode = ref('agent')
const isOnline = ref(true)
const sessionId = ref('')
const sessionReloadKey = ref(0)
const isDarkMode = ref(true)
const isLoggedIn = ref(false)
const currentUser = ref(null)
const chatStats = ref({
  responseTime: 0,
  tokensPerSecond: 0,
  outputTokens: 0,
  inputTokens: 0,
  totalTokens: 0
})

const currentSettings = ref({
  provider: 'llama_cpp',
  model: '',
  api_key: '',
  base_url: '',
  max_tokens: 2048,
  agent_mode: 'plan_execute'
})

const userConfigs = ref([])
const providersList = ref([])

const configuredProviders = computed(() => {
  return userConfigs.value.map(c => {
    const p = providersList.value.find(pr => pr.id === c.provider_id)
    return {
      provider_id: c.provider_id,
      provider_name: c.provider_name || p?.name || c.provider_id,
      default_model: c.default_model || p?.default_model || '',
      base_url: c.base_url || p?.base_url || ''
    }
  })
})

const loadUserConfigs = async () => {
  try {
    const res = await axios.get('/api/user/config')
    userConfigs.value = res.data.configs || []
  } catch (e) {
    console.error('加载用户配置失败:', e)
    addToast('加载用户配置失败: ' + (e.response?.data?.error || e.message), 'error')
  }
}

const loadSettingsFromServer = async () => {
  try {
    const [providersRes, configRes] = await Promise.all([
      axios.get('/api/providers'),
      axios.get('/api/user/config')
    ])

    const providers = providersRes.data.providers || []
    const configs = configRes.data.configs || []
    providersList.value = providers
    userConfigs.value = configs

    if (configs.length > 0) {
      const savedProviderId = localStorage.getItem('jarvis-provider-id')
      const config = configs.find(c => c.provider_id === savedProviderId) || configs[0]
      const provider = providers.find(p => p.id === config.provider_id)

      currentSettings.value = {
        provider: config.provider_id,
        model: config.default_model || '',
        api_key: '',
        base_url: config.base_url || '',
        max_tokens: config.max_tokens || 2048,
        agent_mode: config.agent_mode || 'plan_execute'
      }
      localStorage.setItem('jarvis-provider-id', config.provider_id)
    } else {
      const savedProviderId = localStorage.getItem('jarvis-provider-id') || 'llama_cpp'
      const provider = providers.find(p => p.id === savedProviderId) || providers[0]
      if (provider) {
        currentSettings.value = {
          provider: provider.id,
          model: provider.default_model || '',
          api_key: '',
          base_url: provider.base_url || '',
          max_tokens: currentSettings.value.max_tokens,
          agent_mode: currentSettings.value.agent_mode
        }
      }
    }
  } catch (e) {
    console.error('从服务器加载设置失败:', e)
    addToast('加载设置失败: ' + (e.response?.data?.error || e.message), 'error')
  }
}

const checkAuth = async () => {
  try {
    const response = await axios.get('/api/auth/me')
    if (response.data.authenticated) {
      isLoggedIn.value = true
      currentUser.value = response.data.user
    } else {
      isLoggedIn.value = false
      currentUser.value = null
    }
  } catch (e) {
    isLoggedIn.value = false
    currentUser.value = null
  }
}

const handleLoginSuccess = async (data) => {
  isLoggedIn.value = true
  currentUser.value = {
    username: data.username
  }
  addToast('登录成功', 'success')
  await initSession()
  await loadSettingsFromServer()
}

const handleLogout = async () => {
  try {
    await axios.post('/api/auth/logout')
  } catch (e) {
    console.error('退出登录失败:', e)
  }
  localStorage.removeItem('jarvis-token')
  localStorage.removeItem('jarvis-username')
  localStorage.removeItem('jarvis-provider-id')
  isLoggedIn.value = false
  currentUser.value = null
  sessionId.value = ''
}

const toggleTheme = () => {
  isDarkMode.value = !isDarkMode.value
  document.documentElement.setAttribute('data-theme', isDarkMode.value ? 'dark' : 'light')
  localStorage.setItem('jarvis-theme', isDarkMode.value ? 'dark' : 'light')
}

const handleOpenSettings = () => {
  activePage.value = 'settings'
}

const handleModeChange = (mode) => {
  currentMode.value = mode
}

const handleNewSession = (newSessionId) => {
  sessionId.value = newSessionId
  sessionReloadKey.value++
}

const handleSwitchSession = async (newSessionId) => {
  sessionId.value = newSessionId
  sessionReloadKey.value++
}

const handleDeleteSession = async (deletedSessionId) => {
  if (deletedSessionId === sessionId.value) {
    try {
      const response = await axios.post('/api/session')
      sessionId.value = response.data.session_id
      localStorage.setItem('jarvis-session-id', sessionId.value)
      sessionReloadKey.value++
    } catch (e) {
      console.error('创建新会话失败:', e)
      addToast('创建新会话失败: ' + (e.response?.data?.error || e.message), 'error')
    }
  }
}

const handleUpdateStats = (stats) => {
  chatStats.value = {
    responseTime: stats.response_time || 0,
    tokensPerSecond: stats.tokens_per_second || 0,
    outputTokens: stats.completion_tokens || 0,
    inputTokens: stats.prompt_tokens || 0,
    totalTokens: stats.total_tokens || 0
  }
}

const handleSettingsChange = async (settings) => {
  currentSettings.value = { ...settings }
  localStorage.setItem('jarvis-provider-id', settings.provider)
  await saveSettingsToServer(settings)
  await loadUserConfigs()
}

const handleQuickSwitch = async (providerId) => {
  if (providerId === currentSettings.value.provider) return
  const config = userConfigs.value.find(c => c.provider_id === providerId)
  const provider = providersList.value.find(p => p.id === providerId)
  if (config) {
    currentSettings.value = {
      provider: config.provider_id,
      model: config.default_model || '',
      api_key: '',
      base_url: config.base_url || '',
      max_tokens: config.max_tokens || 2048,
      agent_mode: config.agent_mode || 'plan_execute'
    }
  } else if (provider) {
    currentSettings.value = {
      provider: provider.id,
      model: provider.default_model || '',
      api_key: '',
      base_url: provider.base_url || '',
      max_tokens: currentSettings.value.max_tokens,
      agent_mode: currentSettings.value.agent_mode
    }
  }
  localStorage.setItem('jarvis-provider-id', providerId)
}

const saveSettingsToServer = async (settings) => {
  try {
    const providersRes = await axios.get('/api/providers')
    const provider = providersRes.data.providers.find(p => p.id === settings.provider)

    await axios.post('/api/user/config', {
      provider_id: settings.provider,
      provider_name: provider?.name || settings.provider,
      api_key: settings.api_key,
      base_url: settings.base_url,
      default_model: settings.model,
      max_tokens: settings.max_tokens,
      agent_mode: settings.agent_mode
    })
    addToast('设置已保存', 'success')
  } catch (e) {
    console.error('保存设置到服务器失败:', e)
    addToast('保存设置失败: ' + (e.response?.data?.error || e.message), 'error')
  }
}

const initSession = async () => {
  const savedSession = localStorage.getItem('jarvis-session-id')
  if (savedSession) {
    sessionId.value = savedSession
  } else {
    try {
      const response = await axios.post('/api/session')
      sessionId.value = response.data.session_id
      localStorage.setItem('jarvis-session-id', sessionId.value)
      sessionReloadKey.value++
    } catch (e) {
      console.error('初始化会话失败:', e)
      addToast('初始化会话失败: ' + (e.response?.data?.error || e.message), 'error')
    }
  }
}

onMounted(async () => {
  const savedTheme = localStorage.getItem('jarvis-theme')
  if (savedTheme === 'light') {
    isDarkMode.value = false
    document.documentElement.setAttribute('data-theme', 'light')
  }
  await checkAuth()
  if (isLoggedIn.value) {
    await initSession()
    await loadSettingsFromServer()
  }
})

watch(sessionId, (newSessionId) => {
  localStorage.setItem('jarvis-session-id', newSessionId)
})
</script>

<template>
  <ToastNotification :toasts="toasts" @remove="removeToast" />
  
  <div v-if="!isLoggedIn" class="login-wrapper">
    <LoginPage @login-success="handleLoginSuccess" />
  </div>
  
  <div v-else class="app-container">
    <SidebarLeft
      :current-session-id="sessionId"
      :session-reload-key="sessionReloadKey"
      :active-page="activePage"
      @new-session="handleNewSession"
      @switch-session="handleSwitchSession"
      @delete-session="handleDeleteSession"
      @active-page-change="activePage = $event"
    />
    
    <main class="main-content">
      <header class="header">
        <div class="header-left">
          <div :class="['status-indicator', { online: isOnline, offline: !isOnline }]">
            <span class="status-dot"></span>
            <span>{{ isOnline ? 'Online' : 'Offline' }}</span>
          </div>
          <div v-if="activePage === 'chat'" class="provider-switcher">
            <div class="switcher-label">模型</div>
            <select class="switcher-select" @change="handleQuickSwitch($event.target.value)">
               <option v-for="cp in configuredProviders" :key="cp.provider_id" :value="cp.provider_id" :selected="cp.provider_id === currentSettings.provider">
                 {{ cp.provider_name }}
               </option>
               <option v-if="configuredProviders.length === 0" value="" disabled>暂无已配置模型</option>
             </select>
            <span class="switcher-model">{{ currentSettings.model || '未选择' }}</span>
          </div>
        </div>
        
        <div class="header-center">
          <h1>Jarvis</h1>
        </div>
        
        <div class="header-right">
          <div class="user-info">
            <span class="username">{{ currentUser?.username }}</span>
            <button class="logout-btn" @click="handleLogout" title="退出登录">
              退出
            </button>
          </div>
          <div v-if="activePage === 'chat'" class="mode-toggle">
            <button 
              :class="['mode-btn', { active: currentMode === 'agent' }]"
              @click="handleModeChange('agent')"
            >
              Agent
            </button>
            <button 
              :class="['mode-btn', { active: currentMode === 'chat' }]"
              @click="handleModeChange('chat')"
            >
              Chat
            </button>
          </div>
          <button class="theme-toggle" @click="toggleTheme" :title="isDarkMode ? '切换到日间模式' : '切换到夜间模式'">
            {{ isDarkMode ? '🌞' : '🌙' }}
          </button>
        </div>
      </header>
      
      <ChatPanel v-if="activePage === 'chat'" :mode="currentMode" :settings="currentSettings" :session-id="sessionId" @open-settings="handleOpenSettings" @update-stats="handleUpdateStats" />
      <PluginPage v-else-if="activePage === 'plugins'" class="page-content" />
      <MCPServerPage v-else-if="activePage === 'mcp'" class="page-content" />
      <SettingsPage v-else-if="activePage === 'settings'" :settings="currentSettings" @settings-change="handleSettingsChange" />
    </main>
    
    <SidebarRight v-if="activePage === 'chat'" :stats="chatStats" />
  </div>
</template>

<style scoped>
.login-wrapper {
  min-height: 100vh;
}

.app-container {
  display: flex;
  height: 100vh;
  background: var(--bg-primary);
  overflow: hidden;
  transition: background-color 0.3s ease;
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.header {
  background: rgba(30, 41, 59, 0.5);
  backdrop-filter: blur(10px);
  padding: 12px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--border-color);
  gap: 12px;
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

[data-theme="light"] .header {
  background: rgba(255, 255, 255, 0.8);
}

.header-left, .header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-center {
  flex: 1;
  text-align: center;
}

.header-center h1 {
  font-size: 16px;
  margin: 0;
  font-weight: 600;
  color: var(--text-white);
  transition: color 0.3s ease;
}

.page-content {
  flex: 1;
  overflow-y: auto;
}

[data-theme="light"] .header-center h1 {
  color: var(--text-primary);
}

.page-content {
  flex: 1;
  overflow-y: auto;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-right: 10px;
}

.username {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 4px 12px;
  background: var(--bg-input);
  border-radius: 20px;
  transition: color 0.3s ease, background-color 0.3s ease;
}

.logout-btn {
  font-size: 12px;
  color: var(--text-muted);
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: all 0.2s;
}

.logout-btn:hover {
  color: var(--accent-error);
  background: rgba(239, 68, 68, 0.1);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
  transition: color 0.3s ease;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
  transition: background-color 0.3s ease;
}

.status-indicator.online { color: var(--accent-success); }
.status-indicator.online .status-dot {
  background: var(--accent-success);
  animation: pulse 2s ease-in-out infinite;
}

.status-indicator.offline { color: var(--accent-error); }
.status-indicator.offline .status-dot { background: var(--accent-error); }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.provider-switcher {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  padding: 4px 10px;
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

.switcher-label {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}

.switcher-select {
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 500;
  outline: none;
  cursor: pointer;
  padding: 2px 4px;
}

.switcher-select option {
  background: var(--bg-card);
  color: var(--text-primary);
}

.switcher-model {
  font-size: 11px;
  color: var(--accent-primary);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mode-toggle {
  display: flex;
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  overflow: hidden;
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

.mode-btn {
  padding: 6px 14px;
  font-size: 12px;
  color: var(--text-secondary);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
}

.mode-btn.active {
  background: rgba(99, 102, 241, 0.3);
  color: var(--text-primary);
}

.theme-toggle {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 16px;
}

.theme-toggle:hover {
  border-color: var(--accent-primary);
  background: rgba(99, 102, 241, 0.1);
}
</style>
