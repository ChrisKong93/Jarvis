<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const props = defineProps({
  stats: {
    type: Object,
    default: () => ({
      responseTime: 0,
      tokensPerSecond: 0,
      outputTokens: 0,
      inputTokens: 0,
      totalTokens: 0
    })
  },
  currentSessionId: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['new-session', 'clear-messages', 'switch-session', 'delete-session'])

const sessions = ref([])

const loadSessions = async () => {
  try {
    const response = await axios.get('/api/sessions')
    sessions.value = response.data.sessions || []
  } catch (e) {
    console.error('加载会话列表失败:', e)
  }
}

onMounted(loadSessions)

const handleNewSession = async () => {
  try {
    const response = await axios.post('/api/session')
    await loadSessions()
    emit('new-session', response.data.session_id)
    emit('clear-messages')
  } catch (e) {
    console.error('创建会话失败:', e)
    alert('创建会话失败')
  }
}

const handleSaveRecord = async () => {
  try {
    const response = await axios.get(`/api/session/${props.currentSessionId}`)
    const messages = response.data.messages || []
    if (messages.length > 0) {
      const blob = new Blob([JSON.stringify(messages, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `jarvis-chat-${new Date().toISOString().split('T')[0]}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      alert('聊天记录已保存')
    } else {
      alert('暂无聊天记录')
    }
  } catch (e) {
    console.error('保存记录失败:', e)
    alert('保存记录失败')
  }
}

const handleClearMemory = async () => {
  if (confirm('确定要清空所有记忆吗？')) {
    try {
      await axios.delete('/api/memory')
      alert('记忆已清空')
    } catch (e) {
      console.error('清空记忆失败:', e)
      alert('清空记忆失败')
    }
  }
}

const handleSwitchSession = (sessionId) => {
  emit('switch-session', sessionId)
}

const handleDeleteSession = (sessionId) => {
  if (confirm('确定要删除这个会话吗？')) {
    axios.delete(`/api/session/${sessionId}`).then(() => {
      loadSessions()
    }).catch(e => {
      console.error('删除会话失败:', e)
    })
  }
}

const formatTime = (isoString) => {
  const date = new Date(isoString)
  const now = new Date()
  const diff = now - date
  
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return date.toLocaleDateString('zh-CN')
}
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="avatar">J</div>
      <div class="agent-info">
        <h2>Jarvis</h2>
        <p>AI Assistant</p>
      </div>
    </div>
    
    <div class="section-title">会话列表</div>
    <div class="sessions-panel">
      <div 
        v-for="session in sessions" 
        :key="session.session_id"
        :class="['session-item', { active: session.session_id === currentSessionId }]"
      >
        <div class="session-info" @click="handleSwitchSession(session.session_id)">
          <div class="session-preview">{{ session.preview }}</div>
          <div class="session-meta">
            <span class="session-time">{{ formatTime(session.last_active) }}</span>
            <span class="session-count">{{ session.message_count }}条消息</span>
          </div>
        </div>
        <button 
          class="session-delete" 
          @click.stop="handleDeleteSession(session.session_id)"
          title="删除会话"
        >
          ×
        </button>
      </div>
      <div v-if="sessions.length === 0" class="empty-message">暂无会话</div>
    </div>
    
    <div class="section-title">性能指标</div>
    <div class="stats-panel">
      <div class="stat-item">
        <span class="stat-label">响应时间</span>
        <span class="stat-value">{{ stats.responseTime.toFixed(1) }}s</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">Tokens/s</span>
        <span class="stat-value">{{ stats.tokensPerSecond.toFixed(1) }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">输出Tokens</span>
        <span class="stat-value">{{ stats.outputTokens }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">输入Tokens</span>
        <span class="stat-value">{{ stats.inputTokens }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">总Tokens</span>
        <span class="stat-value">{{ stats.totalTokens }}</span>
      </div>
    </div>
    
    <div class="sidebar-actions">
      <button class="sidebar-btn" @click="handleNewSession">🔄 新建会话</button>
      <button class="sidebar-btn" @click="handleSaveRecord">💾 保存记录</button>
      <button class="sidebar-btn danger" @click="handleClearMemory">🗑️ 清空记忆</button>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 280px;
  min-width: 280px;
  background: var(--gradient-secondary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  padding: 20px;
  flex-shrink: 0;
  transition: background 0.3s ease, border-color 0.3s ease;
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 20px;
  transition: border-color 0.3s ease;
}

.avatar {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: var(--gradient-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: bold;
  color: white;
}

.agent-info h2 { font-size: 16px; font-weight: 600; color: var(--text-white); transition: color 0.3s ease; }
.agent-info p { font-size: 12px; color: var(--text-secondary); transition: color 0.3s ease; }

.section-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
  transition: color 0.3s ease;
}

.sessions-panel {
  flex: 1;
  overflow-y: auto;
  max-height: 200px;
}

.session-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  background: var(--bg-hover);
  border-radius: 10px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.session-item:hover {
  background: var(--bg-active);
}

.session-item.active {
  background: var(--bg-active);
  border-color: var(--border-light);
}

.session-info {
  flex: 1;
  min-width: 0;
}

.session-preview {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
  transition: color 0.3s ease;
}

.session-meta {
  display: flex;
  gap: 10px;
  font-size: 11px;
  color: var(--text-muted);
  transition: color 0.3s ease;
}

.session-delete {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 18px;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.2s;
  opacity: 0;
}

.session-item:hover .session-delete {
  opacity: 1;
}

.session-delete:hover {
  background: rgba(239, 68, 68, 0.2);
  color: var(--accent-error);
}

.empty-message {
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
  padding: 20px;
  transition: color 0.3s ease;
}

.stats-panel {
  margin-top: 15px;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  font-size: 12px;
}

.stat-label { color: var(--text-secondary); transition: color 0.3s ease; }
.stat-value { color: var(--text-white); font-weight: 500; transition: color 0.3s ease; }

.sidebar-actions {
  margin-top: auto;
  padding-top: 15px;
  border-top: 1px solid var(--border-color);
  transition: border-color 0.3s ease;
}

.sidebar-btn {
  width: 100%;
  padding: 10px 14px;
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 10px;
  font-size: 13px;
  color: var(--accent-primary);
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.sidebar-btn:hover {
  background: rgba(99, 102, 241, 0.2);
  border-color: rgba(99, 102, 241, 0.4);
}

.sidebar-btn.danger {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.2);
  color: var(--accent-error);
}

.sidebar-btn.danger:hover {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.4);
}
</style>