<template>
  <div class="login-page">
    <div class="login-container">
      <div class="login-header">
        <div class="logo">
          <span class="logo-icon">🤖</span>
          <h1>Jarvis AI</h1>
        </div>
        <p class="subtitle">智能助手，开启您的AI之旅</p>
      </div>

      <div class="login-form">
        <div v-if="!showRegister" class="form-card">
          <h2>登录</h2>
          <div class="form-group">
            <label>用户名</label>
            <input type="text" v-model="form.username" placeholder="请输入用户名" />
          </div>
          <div class="form-group">
            <label>密码</label>
            <input type="password" v-model="form.password" placeholder="请输入密码" />
          </div>
          <button class="btn-primary" @click="handleLogin" :disabled="isLoading">
            <span v-if="isLoading">登录中...</span>
            <span v-else>登录</span>
          </button>
          <p class="form-link" @click="showRegister = true">
            还没有账号？立即注册
          </p>
          <p v-if="error" class="error-message">{{ error }}</p>
        </div>

        <div v-else class="form-card">
          <h2>注册</h2>
          <div class="form-group">
            <label>用户名</label>
            <input type="text" v-model="form.username" placeholder="请输入用户名" />
          </div>
          <div class="form-group">
            <label>邮箱</label>
            <input type="email" v-model="form.email" placeholder="请输入邮箱" />
          </div>
          <div class="form-group">
            <label>密码</label>
            <input type="password" v-model="form.password" placeholder="请输入密码" />
          </div>
          <button class="btn-primary" @click="handleRegister" :disabled="isLoading">
            <span v-if="isLoading">注册中...</span>
            <span v-else>注册</span>
          </button>
          <p class="form-link" @click="showRegister = false">
            已有账号？立即登录
          </p>
          <p v-if="error" class="error-message">{{ error }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import axios from 'axios'

const emit = defineEmits(['login-success'])

const showRegister = ref(false)
const isLoading = ref(false)
const error = ref('')

const form = reactive({
  username: '',
  email: '',
  password: ''
})

const handleLogin = async () => {
  if (!form.username || !form.password) {
    error.value = '请填写用户名和密码'
    return
  }

  isLoading.value = true
  error.value = ''

  try {
    const response = await axios.post('/api/auth/login', {
      username: form.username,
      password: form.password
    })

    if (response.data.success) {
      localStorage.setItem('jarvis-token', response.data.access_token)
      localStorage.setItem('jarvis-username', response.data.username)
      emit('login-success', response.data)
    } else {
      error.value = response.data.error || '登录失败'
    }
  } catch (e) {
    error.value = e.response?.data?.error || '登录失败，请稍后重试'
  } finally {
    isLoading.value = false
  }
}

const handleRegister = async () => {
  if (!form.username || !form.email || !form.password) {
    error.value = '请填写完整信息'
    return
  }

  isLoading.value = true
  error.value = ''

  try {
    const response = await axios.post('/api/auth/register', {
      username: form.username,
      email: form.email,
      password: form.password
    })

    if (response.data.success) {
      showRegister.value = false
      form.username = ''
      form.email = ''
      form.password = ''
    } else {
      error.value = response.data.error || '注册失败'
    }
  } catch (e) {
    error.value = e.response?.data?.error || '注册失败，请稍后重试'
  } finally {
    isLoading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
}

.login-container {
  width: 100%;
  max-width: 400px;
  padding: 20px;
}

.login-header {
  text-align: center;
  margin-bottom: 40px;
}

.logo {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-bottom: 12px;
}

.logo-icon {
  font-size: 48px;
}

.login-header h1 {
  font-size: 32px;
  font-weight: 700;
  color: #fff;
  margin: 0;
}

.subtitle {
  color: #94a3b8;
  font-size: 14px;
  margin: 0;
}

.form-card {
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(10px);
  border-radius: 16px;
  padding: 32px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.form-card h2 {
  color: #fff;
  font-size: 24px;
  margin: 0 0 24px 0;
  text-align: center;
}

.form-group {
  margin-bottom: 20px;
}

.form-group label {
  display: block;
  color: #cbd5e1;
  font-size: 14px;
  margin-bottom: 8px;
}

.form-group input {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.2);
  color: #fff;
  font-size: 14px;
  outline: none;
  transition: border-color 0.3s;
  box-sizing: border-box;
}

.form-group input:focus {
  border-color: #3b82f6;
}

.form-group input::placeholder {
  color: #64748b;
}

.btn-primary {
  width: 100%;
  padding: 14px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.3s;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.form-link {
  text-align: center;
  color: #3b82f6;
  font-size: 14px;
  margin: 20px 0 0 0;
  cursor: pointer;
}

.form-link:hover {
  text-decoration: underline;
}

.error-message {
  color: #ef4444;
  font-size: 14px;
  text-align: center;
  margin: 16px 0 0 0;
}
</style>
