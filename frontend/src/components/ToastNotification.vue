<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  toasts: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['remove'])

const removeToast = (id) => {
  emit('remove', id)
}
</script>

<template>
  <div class="toast-container">
    <TransitionGroup name="toast">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        :class="['toast', `toast-${toast.type || 'info'}`]"
      >
        <span class="toast-icon">
          <template v-if="toast.type === 'error'">❌</template>
          <template v-else-if="toast.type === 'success'">✅</template>
          <template v-else-if="toast.type === 'warning'">⚠️</template>
          <template v-else>ℹ️</template>
        </span>
        <span class="toast-message">{{ toast.message }}</span>
        <button class="toast-close" @click="removeToast(toast.id)">×</button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-container {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 10000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 400px;
}

.toast {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 10px;
  background: var(--bg-card, #1e293b);
  border: 1px solid var(--border-color, #334155);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  animation: toastIn 0.3s ease-out;
  font-size: 13px;
  color: var(--text-primary, #e2e8f0);
}

.toast-error {
  border-left: 3px solid #ef4444;
}

.toast-success {
  border-left: 3px solid #22c55e;
}

.toast-warning {
  border-left: 3px solid #f59e0b;
}

.toast-info {
  border-left: 3px solid #3b82f6;
}

.toast-icon {
  flex-shrink: 0;
  font-size: 14px;
}

.toast-message {
  flex: 1;
  line-height: 1.4;
}

.toast-close {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text-muted, #64748b);
  font-size: 18px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}

.toast-close:hover {
  color: var(--text-primary, #e2e8f0);
}

@keyframes toastIn {
  from {
    opacity: 0;
    transform: translateX(100%);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.toast-enter-active {
  animation: toastIn 0.3s ease-out;
}

.toast-leave-active {
  animation: toastIn 0.3s ease-in reverse;
}
</style>
