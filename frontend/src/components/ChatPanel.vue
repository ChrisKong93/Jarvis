<script setup>
import { ref, reactive, nextTick, onMounted, watch } from 'vue'
import { marked } from 'marked'
import axios from 'axios'

marked.setOptions({
  breaks: true,
  gfm: true
})

const props = defineProps({
  mode: {
    type: String,
    default: 'agent'
  },
  settings: {
    type: Object,
    default: () => ({
      provider: 'llama_cpp',
      model: '',
      api_key: '',
      base_url: '',
      max_tokens: 2048,
      agent_mode: 'plan_execute'
    })
  },
  sessionId: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update-stats', 'open-settings'])

const messages = ref([])
const messageInput = ref('')
const chatContainer = ref(null)
const isProcessing = ref(false)
const streamStarted = ref(false)
let abortController = null

// 折叠状态
const collapsedSections = reactive({})

const toggleCollapse = (msgIndex, key) => {
  const id = `${msgIndex}-${key}`
  collapsedSections[id] = !collapsedSections[id]
}

const isCollapsed = (msgIndex, key) => {
  const id = `${msgIndex}-${key}`
  // 计划默认展开，工具默认收起
  const defaultCollapsed = key !== 'plan'
  return collapsedSections[id] !== undefined ? collapsedSections[id] : defaultCollapsed
}

const sendMessage = async () => {
  const content = messageInput.value.trim()
  if (!content || isProcessing.value) return

  isProcessing.value = true
  streamStarted.value = false
  abortController = new AbortController()

  const userMsg = {
    role: 'user',
    content,
    timestamp: new Date().toLocaleString()
  }
  messages.value.push(userMsg)
  messageInput.value = ''
  await scrollToBottom()

  const endpoint = props.mode === 'agent' ? '/api/agent' : '/api/chat'
  const requestData = {
    messages: [{ role: 'user', content }],
    session_id: props.sessionId,
    max_tokens: props.settings.max_tokens,
    provider: props.settings.provider,
    agent_mode: props.settings.agent_mode
  }
  if (props.settings.model) requestData.model = props.settings.model

  // 插入占位 assistant 消息（先 push 索引，后续通过索引更新）
  const msgIndex = messages.value.length
  messages.value.push({
    role: 'assistant',
    content: '',
    tool_used: false,
    tool_info: null,
    plan: null,         // 计划步骤列表
    timestamp: new Date().toLocaleString(),
    stats: null,
  })

  const getMsg = () => messages.value[msgIndex]

  try {
    const response = await fetch(endpoint + '/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestData),
      signal: abortController.signal,
    })

    if (!response.ok) {
      const errText = await response.text().catch(() => 'Unknown error')
      throw new Error(`HTTP ${response.status}: ${errText}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || '' // 保留未完成的行

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (!raw) continue

        let event
        try { event = JSON.parse(raw) } catch { continue }

        if (!streamStarted.value) streamStarted.value = true

        switch (event.type) {
          case 'token':
            getMsg().content += event.content
            await scrollToBottom()
            break
          case 'thinking':
            getMsg().content += `\n> 💭 ${event.content}\n\n`
            await scrollToBottom()
            break
          case 'plan':
            getMsg().plan = event.steps || event.plan || []
            await scrollToBottom()
            break
          case 'tool_call':
            getMsg().tool_used = true
            const toolInfo = getMsg().tool_info || []
            toolInfo.push({
              tool_name: event.tool_name,
              parameters: event.parameters,
              result: '',
              is_reflection: event.is_reflection || false,
            })
            getMsg().tool_info = toolInfo
            break
          case 'tool_result':
            const info = getMsg().tool_info
            if (info && info.length) {
              info[info.length - 1].result = event.result
            }
            await scrollToBottom()
            break
          case 'summary_start':
            getMsg().content += '\n---\n\n'
            await scrollToBottom()
            break
          case 'done':
            getMsg().stats = {
              response_time: event.response_time,
              completion_tokens: event.completion_tokens,
              prompt_tokens: event.prompt_tokens,
              total_tokens: event.total_tokens,
              tokens_per_second: event.tokens_per_second || 0,
            }
            emit('update-stats', getMsg().stats)
            break
          case 'error':
            throw new Error(event.content)
        }
      }
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      // 用户取消，保留已生成的内容
    } else {
      // 如果已经有部分内容，追加错误信息而不是替换
      getMsg().content += `\n\n❌ 请求失败: ${error.message}`
    }
  } finally {
    isProcessing.value = false
    abortController = null
    await scrollToBottom()
  }
}

const handleKeydown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

const scrollToBottom = async () => {
  await nextTick()
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

const handleAttachFile = () => {
  alert('文件上传功能开发中...')
}

const handleSettings = () => {
  emit('open-settings')
}

const handleStop = () => {
  if (abortController) {
    abortController.abort()
    isProcessing.value = false
    abortController = null
  }
}

const handleCopyMessage = (index) => {
  const message = messages.value[index]
  if (message) {
    navigator.clipboard.writeText(message.content).then(() => {
      alert('已复制到剪贴板')
    })
  }
}

const handleQuoteMessage = (index) => {
  const message = messages.value[index]
  if (message) {
    messageInput.value = `引用: ${message.content.substring(0, 50)}...\n\n`
  }
}

const loadSessionMessages = async (sessionId) => {
  if (!sessionId) return
  try {
    const response = await axios.get(`/api/session/${sessionId}`)
    const sessionMessages = response.data.messages || []
    messages.value = sessionMessages.map(m => ({
      role: m.role,
      content: m.content,
      timestamp: m.timestamp || new Date().toLocaleString(),
      stats: m.stats || null,
      tool_info: m.tool_info || null,
      plan: m.plan || null,
    }))
    await scrollToBottom()
  } catch (e) {
    console.error('加载会话消息失败:', e)
  }
}

onMounted(() => {
  scrollToBottom()
})

watch(() => props.sessionId, (newSessionId) => {
  loadSessionMessages(newSessionId)
})

watch(() => messages.value.length, scrollToBottom)
</script>

<template>
  <div class="chat-panel">
    <div ref="chatContainer" class="chat-container">
      <div 
        v-for="(message, index) in messages" 
        :key="index" 
        :class="['message', message.role]"
      >
        <div class="message-header">
          <span :class="['message-role', message.role]">
            {{ message.role === 'user' ? 'You' : 'Jarvis' }}
          </span>
          <span class="message-time">{{ message.timestamp }}</span>
          <div class="message-actions">
            <button class="msg-action-btn" @click="handleCopyMessage(index)">复制</button>
            <button class="msg-action-btn" @click="handleQuoteMessage(index)">引用</button>
          </div>
        </div>

        <!-- 计划步骤（Plan-and-Execute） -->
        <div v-if="message.plan && message.plan.length" class="section-card plan-section">
          <div class="section-header" @click="toggleCollapse(index, 'plan')">
            <span class="section-icon">📋</span>
            <span class="section-title">执行计划（{{ message.plan.length }} 步）</span>
            <span class="collapse-arrow">{{ isCollapsed(index, 'plan') ? '▶' : '▼' }}</span>
          </div>
          <div v-if="!isCollapsed(index, 'plan')" class="section-body">
            <div v-for="(step, si) in message.plan" :key="si" class="plan-step">
              <span class="step-number">{{ si + 1 }}</span>
              <span class="step-text">{{ step }}</span>
            </div>
          </div>
        </div>

        <!-- 工具调用信息（可折叠） -->
        <div v-if="message.tool_info && message.tool_info.length" class="section-card tool-section">
          <div class="section-header" @click="toggleCollapse(index, 'tool')">
            <span class="section-icon">🔧</span>
            <span class="section-title">工具调用（{{ message.tool_info.length }} 次）</span>
            <span class="collapse-arrow">{{ isCollapsed(index, 'tool') ? '▶' : '▼' }}</span>
          </div>
          <div v-if="!isCollapsed(index, 'tool')" class="section-body">
            <div v-for="(tool, idx) in message.tool_info" :key="idx" class="tool-call-card">
              <div class="tool-call-header">
                <span class="tool-call-name">{{ tool.tool_name }}</span>
                <span v-if="tool.is_reflection" class="reflection-badge">反思</span>
              </div>
              <div class="tool-call-detail">
                <span class="detail-label">参数</span>
                <pre class="detail-json">{{ JSON.stringify(tool.parameters, null, 2) }}</pre>
              </div>
              <div class="tool-call-detail">
                <span class="detail-label">结果</span>
                <pre class="detail-result">{{ tool.result }}</pre>
              </div>
            </div>
          </div>
        </div>

        <!-- 最终回答 -->
        <div class="message-content" v-html="marked(message.content)"></div>
        
        <div v-if="message.stats" class="message-stats">
          <span>⏱️ {{ message.stats.response_time.toFixed(1) }}s</span>
          <span>📊 {{ message.stats.tokens_per_second.toFixed(2) }} tokens/s</span>
          <span>输出: {{ message.stats.completion_tokens }}</span>
          <span>输入: {{ message.stats.prompt_tokens }}</span>
        </div>
      </div>
      
      <div v-if="isProcessing && !streamStarted" class="message assistant">
        <div class="message-header">
          <span class="message-role assistant">Jarvis</span>
          <span class="message-time">{{ new Date().toLocaleString() }}</span>
        </div>
        <div class="message-content">
          <div class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
          <p>正在思考...</p>
        </div>
      </div>
    </div>
    
    <div class="input-area">
      <div class="input-toolbar">
        <button class="icon-btn" @click="handleAttachFile" title="上传文件">📎</button>
        <button class="icon-btn" @click="handleSettings" title="设置">⚙️</button>
        <button 
          :disabled="!isProcessing"
          class="icon-btn"
          @click="handleStop"
          title="停止生成"
        >
          ⏹️
        </button>
      </div>
      
      <div class="input-wrapper">
        <textarea
          v-model="messageInput"
          :disabled="isProcessing"
          class="message-input"
          placeholder="输入消息..."
          rows="2"
          @keydown="handleKeydown"
        ></textarea>
        <button 
          :disabled="isProcessing || !messageInput.trim()"
          class="send-btn"
          @click="sendMessage"
        >
          {{ isProcessing ? '发送中...' : '发送' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  background: var(--bg-primary);
  transition: background-color 0.3s ease;
}

.chat-container::-webkit-scrollbar { width: 6px; }
.chat-container::-webkit-scrollbar-thumb { background: var(--border-color); border-radius: 3px; }

.message {
  margin-bottom: 20px;
  animation: fadeIn 0.3s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.message-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.message-role {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 10px;
}

.message-role.user { background: rgba(99, 102, 241, 0.2); color: var(--accent-primary); }
.message-role.assistant { background: rgba(34, 197, 94, 0.2); color: var(--accent-success); }

.message-time { font-size: 11px; color: var(--text-muted); transition: color 0.3s ease; }

.message-actions {
  margin-left: auto;
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.message:hover .message-actions { opacity: 1; }

.msg-action-btn {
  padding: 2px 8px;
  font-size: 11px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
}

.msg-action-btn:hover { color: var(--text-primary); border-color: var(--accent-primary); }

.message-content {
  padding: 14px 18px;
  border-radius: 14px;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.message.user .message-content {
  background: var(--gradient-user);
  color: var(--text-primary);
  border: 1px solid rgba(99, 102, 241, 0.3);
  margin-left: auto;
  max-width: 70%;
}

.message.assistant .message-content {
  background: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  max-width: 80%;
}

.message-content :deep(h1) { font-size: 20px; font-weight: 700; color: var(--text-white); margin: 16px 0 8px; padding-bottom: 8px; border-bottom: 2px solid var(--border-color); }
.message-content :deep(h2) { font-size: 18px; font-weight: 600; color: var(--text-white); margin: 14px 0 6px; padding-bottom: 6px; border-bottom: 1px solid var(--border-color); }
.message-content :deep(h3) { font-size: 16px; font-weight: 600; color: var(--text-primary); margin: 12px 0 4px; }
.message-content :deep(ul), .message-content :deep(ol) { margin: 8px 0; padding-left: 24px; }
.message-content :deep(li) { margin: 4px 0; color: var(--text-primary); }
.message-content :deep(code) { background: var(--bg-input); padding: 2px 6px; border-radius: 4px; font-family: 'SF Mono', monospace; font-size: 12px; color: var(--accent-error); }
.message-content :deep(pre) { background: var(--bg-input); padding: 12px; border-radius: 8px; overflow-x: auto; margin: 8px 0; border: 1px solid var(--border-color); }
.message-content :deep(pre code) { background: transparent; padding: 0; color: var(--text-primary); font-size: 12px; }
.message-content :deep(a) { color: var(--accent-info); text-decoration: none; }
.message-content :deep(a:hover) { text-decoration: underline; }
.message-content :deep(strong) { color: var(--text-white); font-weight: 600; }
.message-content :deep(blockquote) { border-left: 3px solid var(--accent-secondary); padding: 8px 16px; margin: 12px 0; background: rgba(139, 92, 246, 0.1); color: var(--accent-secondary); }

/* ---- 可折叠区域（计划 & 工具） ---- */
.section-card {
  margin-top: 10px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--border-color);
  background: var(--bg-card);
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.section-header:hover {
  background: var(--bg-hover);
}

.section-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.section-title {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.collapse-arrow {
  font-size: 10px;
  color: var(--text-muted);
  transition: transform 0.2s;
}

.section-body {
  padding: 8px 14px 14px;
}

/* 计划步骤 */
.plan-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-color);
}

.plan-step:last-child {
  border-bottom: none;
}

.step-number {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-primary);
  color: white;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 700;
}

.step-text {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.5;
}

/* 工具调用卡片 */
.tool-call-card {
  margin-bottom: 10px;
  padding: 10px;
  background: var(--bg-hover);
  border-radius: 8px;
}

.tool-call-card:last-child {
  margin-bottom: 0;
}

.tool-call-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.tool-call-name {
  font-family: 'SF Mono', monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-primary);
  background: rgba(99, 102, 241, 0.1);
  padding: 2px 8px;
  border-radius: 6px;
}

.reflection-badge {
  font-size: 10px;
  padding: 1px 6px;
  background: rgba(245, 158, 11, 0.15);
  color: var(--accent-warning, #f59e0b);
  border-radius: 4px;
  font-weight: 500;
}

.tool-call-detail {
  margin-top: 6px;
}

.detail-label {
  display: block;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  margin-bottom: 3px;
}

.detail-json {
  margin: 0;
  font-size: 11px;
  color: var(--text-secondary);
  font-family: 'SF Mono', monospace;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.5;
}

.detail-result {
  margin: 0;
  font-size: 12px;
  color: var(--text-primary);
  font-family: 'SF Mono', monospace;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.5;
  max-height: 200px;
  overflow-y: auto;
}
/* ---- 可折叠区域结束 ---- */

.message-stats {
  display: flex;
  gap: 12px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-muted);
  transition: color 0.3s ease;
}

.typing-indicator {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}

.typing-indicator span {
  width: 6px;
  height: 6px;
  background: var(--accent-success);
  border-radius: 50%;
  animation: typing 1.4s ease-in-out infinite;
}

.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}

.input-area {
  padding: 16px 24px;
  background: rgba(30, 41, 59, 0.5);
  border-top: 1px solid var(--border-color);
  transition: background-color 0.3s ease, border-color 0.3s ease;
}

[data-theme="light"] .input-area {
  background: rgba(255, 255, 255, 0.8);
}

.input-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.icon-btn {
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s;
  font-size: 14px;
}

.icon-btn:hover:not(:disabled) {
  color: var(--text-primary);
  border-color: var(--accent-primary);
  background: rgba(99, 102, 241, 0.1);
}

.icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.input-wrapper {
  display: flex;
  gap: 12px;
}

.message-input {
  flex: 1;
  padding: 12px 16px;
  border: 1px solid var(--border-color);
  border-radius: 14px;
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 14px;
  resize: vertical;
  min-height: 48px;
  max-height: 200px;
  outline: none;
  transition: border-color 0.2s;
}

.message-input:focus {
  border-color: var(--accent-primary);
}

.message-input::placeholder {
  color: var(--text-muted);
}

.message-input:disabled {
  opacity: 0.5;
}

.send-btn {
  padding: 12px 24px;
  background: var(--gradient-primary);
  border: none;
  border-radius: 14px;
  color: white;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.send-btn:hover:not(:disabled) {
  opacity: 0.9;
  transform: translateY(-1px);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>