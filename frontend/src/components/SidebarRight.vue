<script setup>
import { ref, onMounted, watch, reactive, computed } from 'vue'
import axios from 'axios'

const props = defineProps({
  activePanel: {
    type: String,
    default: 'tools'
  },
  settings: {
    type: Object,
    default: () => ({
      provider: 'llama_cpp',
      model: '',
      api_key: '',
      base_url: '',
      max_tokens: 2048,
      agent_mode: 'graph'
    })
  }
})

const emit = defineEmits(['panel-change', 'settings-change'])

const tools = ref([])
const memory = ref({ short_term: [], long_term: [] })
const memoryStats = ref({ short_term_count: 0, long_term_count: 0 })
const activeMemoryTab = ref('short')
const localSettings = reactive({ ...props.settings })
const providers = ref([])
const userConfigs = ref([])
const showSaveMessage = ref(false)
const models = ref([])
const isLoadingModels = ref(false)

const configuredProviderIds = computed(() => userConfigs.value.map(c => c.provider_id))

const loadUserConfigs = async () => {
  try {
    const res = await axios.get('/api/user/config')
    userConfigs.value = res.data.configs || []
  } catch (e) {
    console.error('Failed to load user configs:', e)
  }
}

const loadData = async () => {
  try {
    const [toolsRes, memoryRes, statsRes, providersRes] = await Promise.all([
      axios.get('/api/tools'),
      axios.get('/api/memory'),
      axios.get('/api/memory/stats'),
      axios.get('/api/providers')
    ])
    tools.value = toolsRes.data.tools || toolsRes.data
    memory.value = memoryRes.data || { short_term: [], long_term: [] }
    memoryStats.value = {
        short_term_count: (statsRes.data && statsRes.data.short_term_summaries) || 0,
        long_term_count: (statsRes.data && statsRes.data.long_term_memories) || 0
      }
    providers.value = providersRes.data.providers || providersRes.data || []
    
    const currentProvider = providers.value.find(p => p.id === localSettings.provider)
    if (currentProvider) {
      if (currentProvider.base_url) localSettings.base_url = currentProvider.base_url
      if (currentProvider.api_key) localSettings.api_key = currentProvider.api_key
      if (currentProvider.default_model) localSettings.model = currentProvider.default_model
    }
    
    await loadUserConfigs()
    
    await loadModels()
  } catch (e) {
    console.error('Failed to load data:', e)
  }
}

onMounted(loadData)

watch(() => props.settings, (newSettings) => {
  Object.assign(localSettings, newSettings)
}, { deep: true })

const handleMemoryTabChange = (tab) => {
  activeMemoryTab.value = tab
}

const getCurrentProvider = () => {
  return providers.value.find(p => p.id === localSettings.provider)
}

watch(() => localSettings.provider, (newProvider) => {
  const savedConfig = userConfigs.value.find(c => c.provider_id === newProvider)
  const provider = providers.value.find(p => p.id === newProvider)
  
  if (savedConfig) {
    localSettings.base_url = savedConfig.base_url || ''
    localSettings.model = savedConfig.default_model || ''
    localSettings.max_tokens = savedConfig.max_tokens || 2048
    localSettings.agent_mode = savedConfig.agent_mode || 'graph'
    localSettings.api_key = ''
  } else if (provider) {
    localSettings.base_url = provider.base_url || ''
    localSettings.model = provider.default_model || ''
    localSettings.api_key = ''
  }
  localStorage.setItem('jarvis-provider-id', newProvider)
})

const loadModels = async () => {
  isLoadingModels.value = true
  try {
    const params = { provider: localSettings.provider }
    if (localSettings.api_key) params.api_key = localSettings.api_key
    if (localSettings.base_url) params.base_url = localSettings.base_url
    
    const response = await axios.get('/api/models', { params })
    const rawModels = response.data.models || []
    models.value = rawModels.map(m => m.name || m.id || m).filter(Boolean)
  } catch (e) {
    console.error('Failed to load models:', e)
    models.value = []
  } finally {
    isLoadingModels.value = false
  }
}

watch(() => localSettings.provider, () => {
  loadModels()
})

const handleRefreshMemory = async () => {
  await loadData()
}

const handleSaveSettings = async () => {
  try {
    emit('settings-change', { ...localSettings })
    showSaveMessage.value = true
    await loadUserConfigs()
    setTimeout(() => {
      showSaveMessage.value = false
    }, 2000)
  } catch (e) {
    console.error('Failed to save settings:', e)
    alert('保存设置失败')
  }
}

const handleClearMemory = async () => {
  if (confirm('确定要清空所有记忆吗？')) {
    try {
      await axios.delete('/api/memory')
      await loadData()
    } catch (e) {
      console.error('Failed to clear memory:', e)
    }
  }
}
</script>

<template>
  <aside class="sidebar-right">
    <div class="sidebar-tabs">
      <button 
        :class="['tab-btn', { active: activePanel === 'tools' }]"
        @click="emit('panel-change', 'tools')"
      >
        🛠️ 工具
      </button>
      <button 
        :class="['tab-btn', { active: activePanel === 'memory' }]"
        @click="emit('panel-change', 'memory')"
      >
        🧠 记忆
      </button>
      <button 
        :class="['tab-btn', { active: activePanel === 'settings' }]"
        @click="emit('panel-change', 'settings')"
      >
        ⚙️ 设置
      </button>
    </div>
    
    <div class="sidebar-content">
      <div v-if="activePanel === 'tools'" class="tools-panel">
        <h3>可用工具</h3>
        <div class="tool-list">
          <div 
            v-for="tool in tools" 
            :key="tool.name" 
            class="tool-card"
          >
            <div class="tool-name">{{ tool.name }}</div>
            <div class="tool-desc">{{ tool.description }}</div>
          </div>
        </div>
        <div v-if="tools.length === 0" class="empty-message">暂无可用工具</div>
      </div>
      
      <div v-if="activePanel === 'memory'" class="memory-panel">
        <div class="memory-header">
          <h3>记忆系统</h3>
          <button class="refresh-btn" @click="handleRefreshMemory">🔄</button>
        </div>
        
        <div class="memory-stats">
          <div class="memory-stat">
            <span class="stat-value">{{ memoryStats.short_term_count }}</span>
            <span class="stat-label">短期记忆</span>
          </div>
          <div class="memory-stat">
            <span class="stat-value">{{ memoryStats.long_term_count }}</span>
            <span class="stat-label">长期记忆</span>
          </div>
        </div>
        
        <div class="memory-tabs">
          <button 
            :class="['memory-tab', { active: activeMemoryTab === 'short' }]"
            @click="handleMemoryTabChange('short')"
          >
            短期记忆
          </button>
          <button 
            :class="['memory-tab', { active: activeMemoryTab === 'long' }]"
            @click="handleMemoryTabChange('long')"
          >
            长期记忆
          </button>
        </div>
        
        <div class="memory-list">
          <div 
            v-for="item in (activeMemoryTab === 'short' ? memory.short_term : memory.long_term)" 
            :key="item.id" 
            class="memory-item"
          >
            <div class="memory-time">{{ new Date((item.timestamp || item.created_at) * 1000).toLocaleString() }}</div>
            <div class="memory-content">{{ item.summary || item.content }}</div>
          </div>
          <div v-if="(!memory.short_term.length && activeMemoryTab === 'short') || (!memory.long_term.length && activeMemoryTab === 'long')" class="empty-message">
            暂无{{ activeMemoryTab === 'short' ? '短期' : '长期' }}记忆
          </div>
        </div>
        
        <button class="clear-memory-btn" @click="handleClearMemory">🗑️ 清空记忆</button>
      </div>
      
      <div v-if="activePanel === 'settings'" class="settings-panel">
        <h3>模型设置</h3>
        
        <div class="form-group">
          <label>模型提供者</label>
          <select v-model="localSettings.provider" class="form-select">
            <option v-for="p in providers" :key="p.id" :value="p.id">
              {{ p.name }} {{ configuredProviderIds.includes(p.id) ? '✓' : '' }}
            </option>
          </select>
          <div class="provider-status">
            <span v-if="configuredProviderIds.includes(localSettings.provider)" class="status-configured">
              已配置
            </span>
            <span v-else class="status-unconfigured">
              未配置
            </span>
          </div>
        </div>
        
        <div class="form-group">
          <label>模型名称</label>
          <select v-model="localSettings.model" class="form-select">
            <option value="">选择模型...</option>
            <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
          </select>
          <button v-if="isLoadingModels" class="load-models-btn" disabled>加载中...</button>
          <button v-else class="load-models-btn" @click="loadModels">🔄 刷新模型</button>
        </div>
        
        <div class="form-group">
          <label>API Key</label>
          <input v-model="localSettings.api_key" type="text" class="form-input" placeholder="API Key" />
        </div>
        
        <div class="form-group">
          <label>Base URL</label>
          <input v-model="localSettings.base_url" type="text" class="form-input" placeholder="http://localhost:8080" />
        </div>
        
        <div class="form-group">
          <label>最大 Tokens</label>
          <input v-model.number="localSettings.max_tokens" type="number" class="form-input" min="256" max="16384" />
        </div>
        
        <button class="save-btn" @click="handleSaveSettings">保存设置</button>
        <div v-if="showSaveMessage" class="save-message">✓ 设置已保存并生效</div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar-right {
  width: 280px;
  min-width: 280px;
  background: var(--gradient-secondary);
  border-left: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: background 0.3s ease, border-color 0.3s ease;
}

.sidebar-tabs {
  display: flex;
  padding: 12px;
  gap: 8px;
  border-bottom: 1px solid var(--border-color);
  transition: border-color 0.3s ease;
}

.tab-btn {
  flex: 1;
  padding: 8px 4px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.tab-btn.active {
  background: rgba(99, 102, 241, 0.2);
  color: var(--accent-primary);
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.sidebar-content h3 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 16px;
  transition: color 0.3s ease;
}

.memory-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.refresh-btn {
  padding: 6px;
  border: none;
  background: var(--bg-hover);
  color: var(--text-secondary);
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.refresh-btn:hover {
  background: var(--bg-active);
  color: var(--text-primary);
}

.empty-message {
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
  padding: 24px;
  transition: color 0.3s ease;
}

/* Tools Panel */
.tool-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-card {
  padding: 12px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 10px;
}

.tool-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--accent-primary);
  margin-bottom: 4px;
}

.tool-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

/* Memory Panel */
.memory-stats {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.memory-stat {
  flex: 1;
  text-align: center;
  padding: 12px;
  background: rgba(99, 102, 241, 0.1);
  border-radius: 10px;
}

.memory-stat .stat-value {
  display: block;
  font-size: 24px;
  font-weight: 700;
  color: var(--accent-primary);
}

.memory-stat .stat-label {
  font-size: 11px;
  color: var(--text-secondary);
}

.memory-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
}

.memory-tab {
  flex: 1;
  padding: 6px;
  border: none;
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.memory-tab:hover {
  background: var(--bg-input);
}

.memory-tab.active {
  background: rgba(99, 102, 241, 0.2);
  color: var(--accent-primary);
}

.memory-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.memory-item {
  padding: 12px;
  background: var(--bg-card);
  border-left: 3px solid var(--accent-primary);
  border-radius: 8px;
}

.memory-time {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.memory-content {
  font-size: 12px;
  color: var(--text-primary);
  line-height: 1.4;
}

.clear-memory-btn {
  width: 100%;
  padding: 10px;
  margin-top: 16px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 10px;
  color: var(--accent-error);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.clear-memory-btn:hover {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.4);
}

/* Settings Panel */
.form-group {
  margin-bottom: 14px;
}

.form-group label {
  display: block;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.form-input, .form-select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}

.form-input:focus, .form-select:focus {
  border-color: var(--accent-primary);
}

.form-input::placeholder {
  color: var(--text-muted);
}

.load-models-btn {
  width: 100%;
  padding: 6px;
  margin-top: 4px;
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 6px;
  color: var(--accent-primary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.load-models-btn:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.2);
  border-color: rgba(99, 102, 241, 0.4);
}

.load-models-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.save-btn {
  width: 100%;
  padding: 10px;
  background: var(--gradient-primary);
  border: none;
  border-radius: 10px;
  color: white;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  margin-top: 16px;
  transition: all 0.2s;
}

.save-btn:hover {
  opacity: 0.9;
}

.save-message {
  text-align: center;
  color: var(--accent-success);
  font-size: 12px;
  margin-top: 8px;
  animation: fadeInOut 2s ease;
}

.provider-status {
  margin-top: 6px;
  font-size: 12px;
}

.status-configured {
  color: var(--accent-success);
  font-weight: 500;
}

.status-unconfigured {
  color: var(--text-muted);
}

@keyframes fadeInOut {
  0% { opacity: 0; }
  20% { opacity: 1; }
  80% { opacity: 1; }
  100% { opacity: 0; }
}
</style>