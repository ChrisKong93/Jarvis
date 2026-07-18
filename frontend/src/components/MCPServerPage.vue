<script setup>
import { ref, onMounted, reactive } from 'vue'
import axios from 'axios'

const servers = ref([])
const mcpTools = ref([])
const isLoading = ref(false)
const showAddForm = ref(false)
const editingServer = ref(null)

const formData = reactive({
  name: '',
  transport: 'stdio',
  command: '',
  args: '',
  url: '',
})

const loadData = async () => {
  isLoading.value = true
  try {
    const [serversRes, toolsRes] = await Promise.all([
      axios.get('/api/mcp/servers'),
      axios.get('/api/mcp/tools'),
    ])
    servers.value = serversRes.data.servers || []
    mcpTools.value = toolsRes.data.tools || []
  } catch (e) {
    console.error('Failed to load MCP data:', e)
  } finally {
    isLoading.value = false
  }
}

onMounted(loadData)

const handleAddServer = async () => {
  const name = formData.name.trim()
  if (!name) return alert('请输入服务器名称')

  try {
    await axios.put(`/api/mcp/servers/${encodeURIComponent(name)}`, {
      transport: formData.transport,
      command: formData.command,
      args: formData.args ? formData.args.split(' ').filter(Boolean) : [],
      url: formData.url,
    })
    resetForm()
    await loadData()
  } catch (e) {
    alert('添加 MCP 服务器失败: ' + (e.response?.data?.error || e.message))
  }
}

const handleDeleteServer = async (name) => {
  if (!confirm(`确认删除 MCP 服务器 "${name}"？`)) return
  try {
    await axios.delete(`/api/mcp/servers/${encodeURIComponent(name)}`)
    await loadData()
  } catch (e) {
    alert('删除失败: ' + (e.response?.data?.error || e.message))
  }
}

const handleReconnect = async (name) => {
  try {
    await axios.post(`/api/mcp/servers/${encodeURIComponent(name)}/reconnect`)
    await loadData()
  } catch (e) {
    alert('重连失败: ' + (e.response?.data?.error || e.message))
  }
}

const handleReloadAll = async () => {
  try {
    await axios.post('/api/mcp/servers/reload')
    await loadData()
  } catch (e) {
    alert('重新加载失败: ' + (e.response?.data?.error || e.message))
  }
}

const resetForm = () => {
  formData.name = ''
  formData.transport = 'stdio'
  formData.command = ''
  formData.args = ''
  formData.url = ''
  editingServer.value = null
  showAddForm.value = false
}
</script>

<template>
  <div class="mcp-page">
    <div class="mcp-header">
      <div>
        <h1>🔌 MCP 服务器</h1>
        <p class="mcp-subtitle">
          Model Context Protocol — 通过 MCP 协议接入第三方工具
        </p>
      </div>
      <div class="header-actions">
        <button class="btn-secondary" @click="handleReloadAll" :disabled="isLoading">
          🔄 重新加载
        </button>
        <button class="btn-primary" @click="showAddForm = !showAddForm">
          {{ showAddForm ? '✕ 取消' : '➕ 添加服务器' }}
        </button>
      </div>
    </div>

    <!-- 添加/编辑表单 -->
    <div v-if="showAddForm" class="add-form">
      <div class="form-row">
        <div class="form-group">
          <label>服务器名称 *</label>
          <input v-model="formData.name" class="form-input" placeholder="如: my-mcp-server" />
        </div>
        <div class="form-group">
          <label>传输协议</label>
          <select v-model="formData.transport" class="form-select">
            <option value="stdio">Stdio（子进程）</option>
            <option value="sse">SSE（HTTP）</option>
          </select>
        </div>
      </div>

      <template v-if="formData.transport === 'stdio'">
        <div class="form-row">
          <div class="form-group">
            <label>启动命令 *</label>
            <input v-model="formData.command" class="form-input" placeholder="如: npx, python, node" />
          </div>
          <div class="form-group">
            <label>参数（空格分隔）</label>
            <input v-model="formData.args" class="form-input" placeholder="-y @modelcontextprotocol/server-filesystem /path" />
          </div>
        </div>
      </template>
      <template v-else>
        <div class="form-row">
          <div class="form-group">
            <label>服务器 URL</label>
            <input v-model="formData.url" class="form-input" placeholder="https://example.com/mcp" />
          </div>
        </div>
      </template>

      <div class="form-actions">
        <button class="btn-primary" @click="handleAddServer">✅ 保存</button>
        <button class="btn-secondary" @click="resetForm">取消</button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading">加载中...</div>

    <!-- 服务器列表 -->
    <div v-else-if="servers.length === 0" class="empty-state">
      <div class="empty-icon">🔌</div>
      <p>尚未配置任何 MCP 服务器</p>
      <p class="empty-hint">点击上方「添加服务器」来接入 MCP 工具</p>
    </div>

    <div v-else class="server-list">
      <div v-for="server in servers" :key="server.name" class="server-card">
        <div class="server-header">
          <div class="server-info">
            <h3>{{ server.name }}</h3>
            <span :class="['status-badge', server.connected ? 'online' : 'offline']">
              {{ server.connected ? '已连接' : '离线' }}
            </span>
            <span class="transport-badge">{{ server.transport }}</span>
          </div>
          <div class="server-actions">
            <button class="icon-btn" @click="handleReconnect(server.name)" title="重连">🔄</button>
            <button class="icon-btn danger" @click="handleDeleteServer(server.name)" title="删除">🗑️</button>
          </div>
        </div>

        <div class="server-meta">
          工具数: <strong>{{ server.tools_count }}</strong>
        </div>

        <!-- 工具列表 -->
        <div v-if="server.tools && server.tools.length" class="tool-list">
          <div v-for="tool in server.tools" :key="tool.name" class="tool-item">
            <span class="tool-name">{{ tool.name }}</span>
            <span class="tool-desc">{{ tool.description }}</span>
          </div>
        </div>
        <div v-else-if="server.connected" class="no-tools">
          该服务器未提供工具
        </div>
      </div>
    </div>

    <!-- 全部 MCP 工具概览 -->
    <div v-if="mcpTools.length > 0" class="all-tools-section">
      <h2>📋 所有 MCP 工具（{{ mcpTools.length }} 个）</h2>
      <div class="all-tools-grid">
        <div v-for="tool in mcpTools" :key="tool.name" class="all-tool-card">
          <div class="tool-header">
            <span class="tool-name">{{ tool.name }}</span>
            <span class="tool-server">{{ tool.server }}</span>
          </div>
          <p class="tool-desc">{{ tool.description || '无描述' }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mcp-page {
  max-width: 960px;
  margin: 0 auto;
  padding: 32px 24px;
  width: 100%;
  box-sizing: border-box;
}

.mcp-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 28px;
  gap: 16px;
}

.mcp-header h1 {
  font-size: 24px;
  color: var(--text-primary);
  margin: 0 0 6px;
  transition: color 0.3s;
}

.mcp-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.add-form {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 16px;
  padding: 24px;
  margin-bottom: 24px;
}

.form-row {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.form-group {
  flex: 1;
  min-width: 200px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.form-input,
.form-select {
  width: 100%;
  padding: 10px 14px;
  background: var(--bg-hover);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  font-size: 14px;
  color: var(--text-primary);
  box-sizing: border-box;
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: var(--accent-primary);
}

.form-actions {
  display: flex;
  gap: 10px;
  padding-top: 8px;
}

.server-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 32px;
}

.server-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  padding: 20px;
  transition: border-color 0.3s;
}

.server-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.server-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.server-info h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text-primary);
}

.status-badge {
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 20px;
  font-weight: 500;
}

.status-badge.online {
  background: rgba(34, 197, 94, 0.15);
  color: var(--accent-success);
}

.status-badge.offline {
  background: rgba(239, 68, 68, 0.15);
  color: var(--accent-error);
}

.transport-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--bg-hover);
  color: var(--text-muted);
  border: 1px solid var(--border-color);
}

.server-actions {
  display: flex;
  gap: 4px;
}

.icon-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-secondary);
  transition: all 0.2s;
}

.icon-btn:hover {
  border-color: var(--accent-primary);
  background: rgba(99, 102, 241, 0.1);
}

.icon-btn.danger:hover {
  border-color: var(--accent-error);
  background: rgba(239, 68, 68, 0.1);
  color: var(--accent-error);
}

.server-meta {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.tool-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tool-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--bg-hover);
  border-radius: 8px;
  font-size: 13px;
}

.tool-name {
  font-weight: 600;
  color: var(--accent-primary);
  font-family: 'SF Mono', monospace;
  font-size: 12px;
  white-space: nowrap;
}

.tool-desc {
  color: var(--text-secondary);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.no-tools {
  font-size: 13px;
  color: var(--text-muted);
  padding: 8px 0;
}

.all-tools-section {
  margin-top: 16px;
}

.all-tools-section h2 {
  font-size: 18px;
  color: var(--text-primary);
  margin: 0 0 16px;
}

.all-tools-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.all-tool-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 14px 16px;
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.tool-server {
  font-size: 11px;
  padding: 1px 8px;
  background: rgba(99, 102, 241, 0.1);
  color: var(--accent-primary);
  border-radius: 6px;
}

.loading {
  text-align: center;
  padding: 40px;
  color: var(--text-muted);
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-secondary);
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-hint {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 8px;
}

.btn-primary {
  padding: 10px 20px;
  background: var(--gradient-primary);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s;
  white-space: nowrap;
}

.btn-primary:hover { opacity: 0.9; }

.btn-secondary {
  padding: 10px 20px;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  font-size: 14px;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}

.btn-secondary:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
</style>
