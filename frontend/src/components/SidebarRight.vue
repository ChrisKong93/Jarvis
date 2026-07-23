<script setup>
import { ref, onMounted, watch } from 'vue'
import axios from 'axios'

const memory = ref({ short_term: [], long_term: [] })
const memoryStats = ref({ short_term_count: 0, long_term_count: 0 })
const activeMemoryTab = ref('short')

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
  }
})

const emit = defineEmits(['update-stats'])

const loadData = async () => {
  try {
    const memoryRes = await axios.get('/api/memory')
    memory.value = memoryRes.data || { short_term: [], long_term: [] }
    memoryStats.value = {
        short_term_count: memory.value.short_term.length,
        long_term_count: memory.value.long_term.length
      }
  } catch (e) {
    console.error('Failed to load data:', e)
  }
}

onMounted(loadData)

// 每次完成新对话后自动刷新记忆列表
watch(() => props.stats.totalTokens, (newVal, oldVal) => {
  if (newVal && newVal !== oldVal) {
    loadData()
  }
})

const handleMemoryTabChange = (tab) => {
  activeMemoryTab.value = tab
}

const handleRefreshMemory = async () => {
  await loadData()
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
    <div class="memory-panel">
      <div class="memory-header">
        <h3>🧠 记忆系统</h3>
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
          短期
        </button>
        <button 
          :class="['memory-tab', { active: activeMemoryTab === 'long' }]"
          @click="handleMemoryTabChange('long')"
        >
          长期
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
      
      <div class="stats-divider"></div>
      
      <div class="stats-panel">
        <h4>📊 性能指标</h4>
        <div class="stats-list">
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
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar-right {
  width: 260px;
  min-width: 260px;
  border-left: 1px solid var(--border-color);
  background: var(--bg-secondary);
  display: flex;
  flex-direction: column;
  transition: background-color 0.3s ease, border-color 0.3s ease;
  height: 100vh;
  padding: 16px;
}

.memory-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.memory-header h3 {
  margin: 0;
  font-size: 15px;
  color: var(--text-primary);
  transition: color 0.3s;
}

.refresh-btn {
  padding: 4px 8px;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-muted);
}

.memory-stats {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.memory-stat {
  flex: 1;
  background: var(--bg-hover);
  border-radius: 8px;
  padding: 10px;
  text-align: center;
}

.memory-stat .stat-value {
  display: block;
  font-size: 20px;
  font-weight: 600;
  color: var(--accent-primary);
}

.memory-stat .stat-label {
  font-size: 11px;
  color: var(--text-muted);
}

.memory-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 10px;
  background: var(--bg-hover);
  border-radius: 8px;
  padding: 3px;
}

.memory-tab {
  flex: 1;
  padding: 5px 8px;
  border: none;
  background: transparent;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.2s;
}

.memory-tab.active {
  background: var(--accent-primary);
  color: white;
}

.memory-list {
  flex: 1;
  overflow-y: auto;
  margin-bottom: 10px;
}

.memory-item {
  padding: 8px 10px;
  background: var(--bg-hover);
  border-radius: 8px;
  margin-bottom: 6px;
}

.memory-time {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.memory-content {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.4;
  transition: color 0.3s;
}

.clear-memory-btn {
  width: 100%;
  padding: 8px;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--accent-error);
  transition: all 0.2s;
  margin-bottom: 16px;
}

.clear-memory-btn:hover {
  background: rgba(239, 68, 68, 0.1);
}

.stats-divider {
  height: 1px;
  background: var(--border-color);
  margin-bottom: 16px;
}

.stats-panel {
  margin-bottom: 0;
}

.stats-panel h4 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px;
  transition: color 0.3s;
}

.stats-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  font-size: 12px;
}

.stat-label { color: var(--text-secondary); transition: color 0.3s; }
.stat-value { color: var(--text-white); font-weight: 500; transition: color 0.3s; }

.empty-message {
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
  padding: 20px 0;
}
</style>
