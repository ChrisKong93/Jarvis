<script setup>
import { ref, onMounted, watch, reactive, computed } from 'vue'
import axios from 'axios'

const props = defineProps({
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

const emit = defineEmits(['settings-change'])

const localSettings = reactive({ ...props.settings })
const providers = ref([])
const userConfigs = ref([])
const models = ref([])
const isLoadingModels = ref(false)
const showSaveMessage = ref(false)

const configuredProviderIds = computed(() => userConfigs.value.map(c => c.provider_id))

const loadUserConfigs = async () => {
  try {
    const res = await axios.get('/api/user/config')
    userConfigs.value = res.data.configs || []
  } catch (e) {
    console.error('Failed to load user configs:', e)
  }
}

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

const showManualModelInput = computed(() => {
  return models.value.length === 0 && !isLoadingModels.value
})

const loadData = async () => {
  try {
    const res = await axios.get('/api/providers')
    providers.value = res.data.providers || []
    await loadUserConfigs()
    if (localSettings.provider) {
      await loadModels()
    }
  } catch (e) {
    console.error('Failed to load providers:', e)
  }
}

onMounted(loadData)

watch(() => props.settings, (newSettings) => {
  Object.assign(localSettings, newSettings)
}, { deep: true })

const handleSave = async () => {
  emit('settings-change', { ...localSettings })
  showSaveMessage.value = true
  await loadUserConfigs()
  setTimeout(() => {
    showSaveMessage.value = false
  }, 2000)
}
</script>

<template>
  <div class="settings-page">
    <div class="settings-header">
      <h1>⚙️ 模型设置</h1>
      <p class="settings-subtitle">配置你的模型提供者、API Key 和模型参数</p>
    </div>
    
    <div class="settings-cards">
      <div class="settings-card">
        <div class="card-body">
          <div class="form-row">
            <div class="form-group flex-2">
              <label>模型提供者</label>
              <select v-model="localSettings.provider" class="form-select" @change="loadModels">
                <option v-for="p in providers" :key="p.id" :value="p.id">
                  {{ p.name }} {{ configuredProviderIds.includes(p.id) ? '✓' : '' }}
                </option>
              </select>
              <div class="provider-status">
                <span v-if="configuredProviderIds.includes(localSettings.provider)" class="status-configured">已配置</span>
                <span v-else class="status-unconfigured">未配置</span>
              </div>
            </div>
            <div class="form-group flex-3">
              <label>模型名称</label>
              <div class="model-row">
                <!-- 有模型列表时：下拉选择 -->
                <select v-if="!showManualModelInput" v-model="localSettings.model" class="form-select">
                  <option value="">选择模型...</option>
                  <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
                </select>
                <!-- 没有模型列表时：手动输入 -->
                <input v-else
                  v-model="localSettings.model"
                  class="form-input"
                  placeholder="手动输入模型名称（如 qwen2.5-7b-instruct）"
                />
                <button class="btn-secondary" @click="loadModels" :disabled="isLoadingModels">
                  {{ isLoadingModels ? '加载中...' : '🔄 刷新' }}
                </button>
              </div>
              <div v-if="isLoadingModels" class="model-status loading">正在连接服务端获取模型列表...</div>
              <div v-else-if="showManualModelInput" class="model-status manual">
                ⚠️ 未能获取模型列表，已切换为手动输入模式
              </div>
            </div>
          </div>
          
          <div class="form-row">
            <div class="form-group flex-1">
              <label>API Base URL</label>
              <input v-model="localSettings.base_url" class="form-input" placeholder="https://api.deepseek.com" />
            </div>
          </div>
          
          <div class="form-row">
            <div class="form-group flex-1">
              <label>API Key</label>
              <input v-model="localSettings.api_key" class="form-input" type="password" placeholder="输入 API Key" />
            </div>
          </div>
          
          <div class="form-row">
            <div class="form-group">
              <label>最大 Token 数</label>
              <input v-model="localSettings.max_tokens" class="form-input" type="number" style="max-width: 200px" />
            </div>
            <div class="form-group">
              <label>Agent 模式</label>
              <select v-model="localSettings.agent_mode" class="form-select" style="max-width: 200px">
                <option value="graph">Graph Agent（流程图）</option>
                <option value="plan_execute">Plan-and-Execute（规划执行）</option>
                <option value="standard">Standard Agent（标准 ReAct）</option>
              </select>
            </div>
          </div>
          
          <div class="form-actions">
            <button class="btn-primary" @click="handleSave">💾 保存设置</button>
            <span v-if="showSaveMessage" class="save-message">✅ 配置已保存</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  max-width: 800px;
  margin: 0 auto;
  padding: 32px 24px;
  width: 100%;
  box-sizing: border-box;
}

.settings-header {
  margin-bottom: 28px;
}

.settings-header h1 {
  font-size: 24px;
  color: var(--text-primary);
  margin: 0 0 6px;
  transition: color 0.3s;
}

.settings-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
  transition: color 0.3s;
}

.settings-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 16px;
  overflow: hidden;
  transition: background 0.3s, border-color 0.3s;
}

.card-body {
  padding: 28px;
}

.form-row {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.form-group {
  min-width: 180px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
  transition: color 0.3s;
}

.form-select,
.form-input {
  width: 100%;
  padding: 10px 14px;
  background: var(--bg-hover);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  font-size: 14px;
  color: var(--text-primary);
  transition: all 0.3s;
  box-sizing: border-box;
}

.form-select:focus,
.form-input:focus {
  outline: none;
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.flex-1 { flex: 1; }
.flex-2 { flex: 2; }
.flex-3 { flex: 3; }

.model-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.model-row .form-select {
  flex: 1;
}

.provider-status {
  margin-top: 6px;
  font-size: 12px;
}

.status-configured { color: var(--accent-success); }
.status-unconfigured { color: var(--text-muted); }

.form-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  padding-top: 8px;
}

.btn-primary {
  padding: 12px 28px;
  background: var(--gradient-primary);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s, transform 0.1s;
}

.btn-primary:hover { opacity: 0.92; }
.btn-primary:active { transform: scale(0.98); }

.btn-secondary {
  padding: 10px 16px;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}

.btn-secondary:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.save-message {
  font-size: 14px;
  color: var(--accent-success);
  font-weight: 500;
}

.model-status {
  font-size: 12px;
  margin-top: 6px;
}

.model-status.loading {
  color: var(--accent-primary);
}

.model-status.empty {
  color: var(--accent-warning, #f59e0b);
}

.model-status.manual {
  color: var(--accent-warning, #f59e0b);
}
</style>
