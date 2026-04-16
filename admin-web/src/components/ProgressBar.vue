<template>
  <div class="progress-bar">
    <div class="progress-header">
      <span class="progress-text" v-if="total > 0">{{ current }} / {{ total }}</span>
      <span class="progress-pct">{{ pct }}%</span>
    </div>
    <div class="progress-track">
      <div
        class="progress-fill"
        :class="status"
        :style="{ width: pct + '%' }"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  current: number
  total: number
  status?: 'running' | 'completed' | 'error' | 'idle'
}>()

const pct = computed(() => {
  if (props.total <= 0) return 0
  return Math.min(100, Math.round((props.current / props.total) * 100))
})
</script>

<style scoped>
.progress-bar { width: 100%; }
.progress-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
  font-size: 0.8rem;
  color: #a0a0b0;
}
.progress-track {
  width: 100%;
  height: 8px;
  background: #0f3460;
  border-radius: 4px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
  background: #60a5fa;
}
.progress-fill.completed { background: #4ade80; }
.progress-fill.error { background: #ff6b6b; }
.progress-fill.idle { background: #4a4a6a; }
</style>
