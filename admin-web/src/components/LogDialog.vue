<template>
  <Teleport to="body">
    <div class="dialog-overlay" @click.self="close">
      <div class="dialog-box">
        <div class="dialog-header">
          <span class="dialog-title">{{ title }}</span>
          <div class="dialog-header-right">
            <StatusBadge v-if="status" :status="status" />
            <button class="btn-close" @click="close">&times;</button>
          </div>
        </div>
        <div class="dialog-body">
          <div v-if="metrics && Object.keys(metrics).length" class="metrics-section">
            <div class="metric-item" v-for="(val, key) in metrics" :key="key">
              <span class="metric-key">{{ key }}</span>
              <span class="metric-val">{{ typeof val === 'number' ? val.toFixed(4) : val }}</span>
            </div>
          </div>
          <LogPanel :lines="lines" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import LogPanel from './LogPanel.vue'
import StatusBadge from './StatusBadge.vue'

defineProps<{
  title: string
  lines: string[]
  status?: string
  metrics?: Record<string, any>
}>()

const emit = defineEmits<{ close: [] }>()
function close() { emit('close') }
</script>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.dialog-box {
  background: #1a1a2e;
  border: 1px solid #2a2a4a;
  border-radius: 12px;
  width: 90%;
  max-width: 800px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}
.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid #2a2a4a;
}
.dialog-title {
  font-weight: 600;
  font-size: 0.95rem;
  color: #e0e0e0;
}
.dialog-header-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.btn-close {
  background: none;
  border: none;
  color: #a0a0b0;
  font-size: 1.5rem;
  cursor: pointer;
  line-height: 1;
  padding: 0;
}
.btn-close:hover { color: #e0e0e0; }
.dialog-body {
  padding: 1rem 1.25rem;
  overflow-y: auto;
  flex: 1;
}
.metrics-section {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1.5rem;
  margin-bottom: 1rem;
  padding: 0.75rem;
  background: #0f3460;
  border-radius: 8px;
}
.metric-item { font-size: 0.82rem; }
.metric-key { color: #a0a0b0; margin-right: 0.4rem; }
.metric-val { color: #60a5fa; font-variant-numeric: tabular-nums; }
</style>
