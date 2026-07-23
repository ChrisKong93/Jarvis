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

// ---- 表单状态 ----
const form = reactive({
  name: '',
  provider: 'llama_cpp',
  model: '',
  api_key: '',
  base_url: '',
  max_tokens: 2048,
  agent_mode: 'graph',
})
const editingId = ref(null)  // null = 新增, number = 编辑
const showForm = ref(false)  // 表单是否可见

const providers = ref([])
const configs = ref([])
const models = ref([])
const isLoadingModels = ref(false)
const showSaveMessage = ref(false)
const saveMessage = ref('')

// ---- 计算属性 ----

const showManualModelInput = computed(() => {
  return models.value.length === 0 && !isLoadingModels.value
})

const configDisplayName = (cfg) => {
  return cfg.name || `${cfg.provider_name} - ${cfg.default_model || '?'}`
}

const selectedProviderInfo = computed(() => {
  return providers.value.find(p => p.id === form.provider)
})

const needManualBaseUrl = computed(() => {
  const p = selectedProviderInfo.value
  return p && p.dynamic_models && !p.base_url
})

// ---- 数据加载 ----

const loadModels = async (forProvider, forApiKey, forBaseUrl) => {
  // 如果 base_url 为空但 provider 要求手动输入，直接跳过请求
  if (!forBaseUrl && !forApiKey && needManualBaseUrl.value) {
    models.value = []
    isLoadingModels.value = false
    return
  }
  isLoadingModels.value = true
  try {
    const params = { provider: forProvider || form.provider }
    if (forApiKey) params.api_key = forApiKey
    if (forBaseUrl) params.base_url = forBaseUrl
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

const loadConfigs = async () => {
  try {
    const res = await axios.get('/api/user/config')
    configs.value = res.data.configs || []
  } catch (e) {
    console.error('Failed to load configs:', e)
  }
}

const loadData = async () => {
  try {
    const res = await axios.get('/api/providers')
    providers.value = res.data.providers || []
    await loadConfigs()
    if (form.provider) {
      await loadModels()
    }
  } catch (e) {
    console.error('Failed to load providers:', e)
  }
}

const isCustomProvider = (providerId) => {
  const p = providers.value.find(p => p.id === providerId)
  return p && p.dynamic_models && !p.base_url
}

const onProviderChange = () => {
  // 切换 provider 时重置 model
  form.model = ''
  models.value = []
  loadModels(form.provider, form.api_key, form.base_url)
}

onMounted(loadData)

// ---- 表单方法 ----

const resetForm = () => {
  form.name = ''
  form.provider = 'llama_cpp'
  form.model = ''
  form.api_key = ''
  form.base_url = ''
  form.max_tokens = 2048
  form.agent_mode = 'graph'
  editingId.value = null
  showForm.value = false
}

const startAdd = () => {
  resetForm()
  showForm.value = true
}

const startEdit = (cfg) => {
  form.name = cfg.name || ''
  form.provider = cfg.provider_id
  form.model = cfg.default_model || ''
  form.api_key = ''
  form.base_url = cfg.base_url || ''
  form.max_tokens = cfg.max_tokens || 2048
  form.agent_mode = cfg.agent_mode || 'graph'
  editingId.value = cfg.id
  showForm.value = true
  loadModels(cfg.provider_id, '', cfg.base_url)
}

const cancelEdit = () => {
  resetForm()
  showForm.value = false
  loadModels()
}

const handleSave = async () => {
  const payload = {
    name: form.name || '',
    provider_id: form.provider,
    provider_name: providers.value.find(p => p.id === form.provider)?.name || form.provider,
    api_key: form.api_key,
    base_url: form.base_url,
    default_model: form.model,
    max_tokens: form.max_tokens,
    agent_mode: form.agent_mode,
  }

  try {
    if (editingId.value) {
      // 更新已有配置
      await axios.put(`/api/user/config/${editingId.value}`, payload)
      saveMessage.value = '✅ 配置已更新'
    } else {
      // 新增配置
      await axios.post('/api/user/config', payload)
      saveMessage.value = '✅ 配置已添加'
    }
    showSaveMessage.value = true
    await loadConfigs()
    resetForm()
    setTimeout(() => { showSaveMessage.value = false }, 2000)
  } catch (e) {
    saveMessage.value = '❌ 保存失败: ' + (e.response?.data?.error || e.message)
    showSaveMessage.value = true
    setTimeout(() => { showSaveMessage.value = false }, 3000)
  }
}

const handleDelete = async (cfg) => {
  if (!confirm(`确定删除配置「${configDisplayName(cfg)}」？`)) return
  try {
    await axios.delete(`/api/user/config/${cfg.id}`)
    await loadConfigs()
    if (editingId.value === cfg.id) resetForm()
  } catch (e) {
    saveMessage.value = '❌ 删除失败: ' + (e.response?.data?.error || e.message)
    showSaveMessage.value = true
    setTimeout(() => { showSaveMessage.value = false }, 3000)
  }
}

const handleSelectConfig = (cfg) => {
  // 选中配置用于聊天（通知 App.vue）
  emit('settings-change', {
    config_id: cfg.id,
    provider: cfg.provider_id,
    model: cfg.default_model || '',
    api_key: '',
    base_url: cfg.base_url || '',
    max_tokens: cfg.max_tokens || 2048,
    agent_mode: cfg.agent_mode || 'graph',
  })
}
</script>

<template>
  <div class="settings-page">
    <div class="settings-header">
      <h1>⚙️ 模型设置</h1>
      <p class="settings-subtitle">管理你的模型配置，每个配置可独立设置提供者、API Key 和模型参数</p>
    </div>

    <!-- ========== 已保存的配置列表 ========== -->
    <div class="settings-cards">
      <div class="settings-card">
        <div class="card-header">
          <h2>已保存的配置</h2>
          <button class="btn-secondary btn-sm" @click="startAdd">➕ 添加配置</button>
        </div>
        <div class="card-body" v-if="configs.length === 0">
          <p class="empty-hint">还没有保存任何模型配置，点击「添加配置」开始添加。</p>
        </div>
        <div class="config-list" v-else>
          <div v-for="cfg in configs" :key="cfg.id"
               class="config-item"
               :class="{ 'is-editing': editingId === cfg.id }">
            <div class="config-info" @click="startEdit(cfg)">
              <div class="config-name">{{ configDisplayName(cfg) }}</div>
              <div class="config-meta">
                <span class="meta-tag provider-tag">{{ cfg.provider_name }}</span>
                <span v-if="cfg.default_model" class="meta-tag model-tag">{{ cfg.default_model }}</span>
                <span v-if="cfg.base_url" class="meta-tag url-tag">{{ cfg.base_url }}</span>
                <span v-if="cfg.api_key" class="meta-tag key-tag">🔑 已配置</span>
              </div>
            </div>
            <div class="config-actions">
              <button class="btn-use" @click.stop="handleSelectConfig(cfg)" title="使用此配置对话">💬 使用</button>
              <button class="btn-edit" @click.stop="startEdit(cfg)" title="编辑">✏️</button>
              <button class="btn-delete" @click.stop="handleDelete(cfg)" title="删除">🗑️</button>
            </div>
          </div>
        </div>
      </div>

      <!-- ========== 新增/编辑表单 ========== -->
      <div v-if="showForm" class="settings-card">
        <div class="card-header">
          <h2>{{ editingId ? '编辑配置' : '添加配置' }}</h2>
          <span v-if="editingId" class="edit-hint">正在编辑，保存后生效</span>
        </div>
        <div class="card-body">
          <div class="form-row">
            <div class="form-group flex-1">
              <label>配置名称（可选）</label>
              <input v-model="form.name" class="form-input" placeholder="如「我的 GPT-4o」「本地模型」" />
            </div>
          </div>

          <div class="form-row">
            <div class="form-group flex-2">
              <label>模型提供者</label>
              <select v-model="form.provider" class="form-select" @change="onProviderChange">
                <option v-for="p in providers" :key="p.id" :value="p.id">
                  {{ p.name }}
                </option>
              </select>
            </div>
            <div class="form-group flex-3">
              <label>模型名称</label>
              <div class="model-row">
                <select v-if="!showManualModelInput" v-model="form.model" class="form-select">
                  <option value="">选择模型...</option>
                  <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
                </select>
                <input v-else-if="!needManualBaseUrl"
                  v-model="form.model"
                  class="form-input"
                  placeholder="手动输入模型名称"
                />
                <input v-else
                  v-model="form.model"
                  class="form-input"
                  placeholder="手动输入模型名称"
                />
                <button class="btn-secondary" @click="loadModels(form.provider, form.api_key, form.base_url)" :disabled="isLoadingModels">
                  {{ isLoadingModels ? '加载中...' : '🔄 刷新' }}
                </button>
              </div>
              <div v-if="isLoadingModels" class="field-hint loading">正在连接...</div>
              <div v-else-if="needManualBaseUrl" class="field-hint warn">请先填写 API Base URL 和 API Key，然后点击刷新获取模型列表</div>
              <div v-else-if="showManualModelInput" class="field-hint warn">未能获取模型列表，已切换为手动输入</div>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group flex-1">
              <label>API Base URL</label>
              <input v-model="form.base_url" class="form-input" placeholder="https://api.openai.com" />
            </div>
          </div>

          <div class="form-row">
            <div class="form-group flex-1">
              <label>API Key</label>
              <input v-model="form.api_key" class="form-input" type="password" :placeholder="editingId ? '留空则保持原值' : '输入 API Key'" />
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>最大 Token 数</label>
              <input v-model="form.max_tokens" class="form-input" type="number" style="max-width: 200px" />
            </div>
            <div class="form-group">
              <label>Agent 模式</label>
              <select v-model="form.agent_mode" class="form-select" style="max-width: 200px">
                <option value="graph">Graph Agent（流程图）</option>
                <option value="plan_execute">Plan-and-Execute（规划执行）</option>
                <option value="standard">Standard Agent（标准 ReAct）</option>
              </select>
            </div>
          </div>

          <div class="form-actions">
            <button class="btn-primary" @click="handleSave">
              {{ editingId ? '💾 更新配置' : '➕ 添加配置' }}
            </button>
            <button v-if="editingId" class="btn-secondary" @click="cancelEdit">取消编辑</button>
            <span v-if="showSaveMessage" class="save-message">{{ saveMessage }}</span>
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
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px 0;
}

.card-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.edit-hint {
  font-size: 12px;
  color: var(--accent-primary);
}

.card-body {
  padding: 18px 24px 24px;
}

.empty-hint {
  color: var(--text-muted);
  font-size: 14px;
  margin: 8px 0;
}

/* ---- 配置列表 ---- */

.config-list {
  display: flex;
  flex-direction: column;
}

.config-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-color);
  transition: background 0.2s;
  gap: 12px;
}

.config-item:last-child {
  border-bottom: none;
}

.config-item:hover {
  background: var(--bg-hover);
}

.config-item.is-editing {
  background: var(--bg-active, rgba(99, 102, 241, 0.06));
  border-left: 3px solid var(--accent-primary);
}

.config-info {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.config-name {
  font-size: 15px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.config-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.meta-tag {
  display: inline-block;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--bg-hover);
  color: var(--text-secondary);
  white-space: nowrap;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.provider-tag {
  color: var(--accent-primary);
  background: color-mix(in srgb, var(--accent-primary) 10%, transparent);
}

.model-tag {
  color: var(--accent-success, #10b981);
  background: color-mix(in srgb, var(--accent-success, #10b981) 10%, transparent);
}

.url-tag {
  color: var(--text-secondary);
}

.key-tag {
  color: var(--accent-warning, #f59e0b);
}

.config-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.btn-use {
  padding: 6px 12px;
  background: var(--accent-primary);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s;
  white-space: nowrap;
}
.btn-use:hover { opacity: 0.85; }

.btn-edit, .btn-delete {
  padding: 6px 8px;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-edit:hover { background: var(--bg-hover); border-color: var(--accent-primary); }
.btn-delete:hover { background: rgba(239, 68, 68, 0.1); border-color: #ef4444; }

/* ---- 表单 ---- */

.form-row {
  display: flex;
  gap: 16px;
  margin-bottom: 18px;
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

.btn-sm {
  padding: 6px 14px;
  font-size: 13px;
}

.save-message {
  font-size: 14px;
  color: var(--accent-success);
  font-weight: 500;
}

.field-hint {
  font-size: 12px;
  margin-top: 6px;
}
.field-hint.loading { color: var(--accent-primary); }
.field-hint.warn { color: var(--accent-warning, #f59e0b); }
</style>
