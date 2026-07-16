<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const plugins = ref([])
const showInstallDialog = ref(false)
const newPlugin = ref({
  name: '',
  display_name: '',
  version: '1.0.0',
  description: '',
  author: '',
  icon: '🧩',
})

const loadPlugins = async () => {
  try {
    const response = await axios.get('/api/plugins')
    plugins.value = response.data.plugins || []
  } catch (e) {
    console.error('加载插件失败:', e)
  }
}

const togglePlugin = async (plugin) => {
  try {
    await axios.put(`/api/plugins/${plugin.id}/toggle`, {
      is_enabled: !plugin.is_enabled
    })
    plugin.is_enabled = !plugin.is_enabled
  } catch (e) {
    console.error('切换插件失败:', e)
  }
}

const uninstallPlugin = async (plugin) => {
  if (!confirm(`确定卸载插件「${plugin.display_name}」吗？`)) return
  try {
    await axios.delete(`/api/plugins/${plugin.id}`)
    plugins.value = plugins.value.filter(p => p.id !== plugin.id)
  } catch (e) {
    console.error('卸载插件失败:', e)
    alert('卸载失败，默认插件不可删除')
  }
}

const installPlugin = async () => {
  if (!newPlugin.value.name || !newPlugin.value.display_name) {
    alert('插件名称和显示名不能为空')
    return
  }
  try {
    const response = await axios.post('/api/plugins', newPlugin.value)
    if (response.data.success) {
      showInstallDialog.value = false
      newPlugin.value = { name: '', display_name: '', version: '1.0.0', description: '', author: '', icon: '🧩' }
      await loadPlugins()
    }
  } catch (e) {
    alert('安装失败，插件名可能已存在')
  }
}

onMounted(loadPlugins)
</script>

<template>
  <div class="plugin-page">
    <div class="plugin-header">
      <h1>🧩 插件管理</h1>
      <p class="plugin-subtitle">管理和配置 Jarvis 的所有工具插件</p>
    </div>

    <div class="plugin-actions">
      <button class="btn-install" @click="showInstallDialog = true">➕ 安装插件</button>
    </div>

    <div class="plugin-grid">
      <div v-for="plugin in plugins" :key="plugin.id" class="plugin-card">
        <div class="plugin-icon">{{ plugin.icon }}</div>
        <div class="plugin-info">
          <div class="plugin-name">
            {{ plugin.display_name }}
            <span class="plugin-version">v{{ plugin.version }}</span>
          </div>
          <div class="plugin-desc">{{ plugin.description }}</div>
          <div class="plugin-meta">
            <span v-if="plugin.author">作者：{{ plugin.author }}</span>
            <span v-if="plugin.is_default" class="tag-default">默认</span>
          </div>
        </div>
        <div class="plugin-controls">
          <label class="switch">
            <input type="checkbox" :checked="plugin.is_enabled" @change="togglePlugin(plugin)" />
            <span class="slider"></span>
          </label>
          <button
            v-if="!plugin.is_default"
            class="btn-uninstall"
            @click="uninstallPlugin(plugin)"
            title="卸载"
          >🗑️</button>
        </div>
      </div>
    </div>

    <!-- 安装对话框 -->
    <div v-if="showInstallDialog" class="dialog-overlay" @click.self="showInstallDialog = false">
      <div class="dialog">
        <h3>安装插件</h3>
        <div class="form-group">
          <label>名称（标识符）</label>
          <input v-model="newPlugin.name" placeholder="如：my_plugin" />
        </div>
        <div class="form-group">
          <label>显示名称</label>
          <input v-model="newPlugin.display_name" placeholder="如：我的插件" />
        </div>
        <div class="form-group">
          <label>描述</label>
          <textarea v-model="newPlugin.description" placeholder="插件功能描述" rows="2"></textarea>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>版本</label>
            <input v-model="newPlugin.version" placeholder="1.0.0" />
          </div>
          <div class="form-group">
            <label>作者</label>
            <input v-model="newPlugin.author" placeholder="作者名" />
          </div>
          <div class="form-group">
            <label>图标</label>
            <input v-model="newPlugin.icon" placeholder="🧩" />
          </div>
        </div>
        <div class="dialog-actions">
          <button class="btn-cancel" @click="showInstallDialog = false">取消</button>
          <button class="btn-confirm" @click="installPlugin">安装</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plugin-page {
  width: 100%;
}

.plugin-header {
  margin-bottom: 16px;
}

.plugin-header h1 {
  font-size: 18px;
  color: var(--text-primary);
  margin: 0 0 4px;
  transition: color 0.3s;
}

.plugin-subtitle {
  display: none;
}

.plugin-actions {
  margin-bottom: 14px;
}

.btn-install {
  padding: 10px 20px;
  background: var(--gradient-primary);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.btn-install:hover {
  opacity: 0.9;
}

.plugin-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.plugin-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  transition: background 0.3s, border-color 0.3s;
}

.plugin-icon {
  font-size: 24px;
  width: 36px;
  text-align: center;
  flex-shrink: 0;
}

.plugin-info {
  flex: 1;
  min-width: 0;
}

.plugin-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
  transition: color 0.3s;
}

.plugin-version {
  font-size: 12px;
  font-weight: 400;
  color: var(--text-muted);
  margin-left: 8px;
}

.plugin-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
  transition: color 0.3s;
}

.plugin-meta {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: var(--text-muted);
  align-items: center;
  transition: color 0.3s;
}

.tag-default {
  background: var(--accent-primary);
  color: white;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 11px;
}

.plugin-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.btn-uninstall {
  padding: 6px 8px;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
  color: var(--text-muted);
}

.btn-uninstall:hover {
  background: rgba(239, 68, 68, 0.1);
  border-color: var(--accent-error);
}

/* Toggle Switch */
.switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0; left: 0; right: 0; bottom: 0;
  background: var(--border-color);
  border-radius: 24px;
  transition: 0.3s;
}

.slider:before {
  content: "";
  position: absolute;
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background: white;
  border-radius: 50%;
  transition: 0.3s;
}

input:checked + .slider {
  background: var(--accent-primary);
}

input:checked + .slider:before {
  transform: translateX(20px);
}

/* Dialog */
.dialog-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 100;
}

.dialog {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 16px;
  padding: 28px;
  width: 480px;
  max-width: 90vw;
}

.dialog h3 {
  margin: 0 0 20px;
  font-size: 18px;
  color: var(--text-primary);
  transition: color 0.3s;
}

.form-group {
  margin-bottom: 14px;
}

.form-group label {
  display: block;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 5px;
  transition: color 0.3s;
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: 9px 12px;
  background: var(--bg-hover);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text-primary);
  transition: all 0.3s;
  box-sizing: border-box;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--accent-primary);
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-row .form-group {
  flex: 1;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

.btn-cancel {
  padding: 9px 18px;
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
}

.btn-confirm {
  padding: 9px 18px;
  background: var(--gradient-primary);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
}
</style>
