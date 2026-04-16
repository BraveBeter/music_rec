<template>
  <span class="badge" :class="status">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status: 'running' | 'completed' | 'error' | 'idle' | 'disabled' | 'cancelled' | 'interrupted'
  label?: string
}>()

const labelMap: Record<string, string> = {
  running: '运行中',
  completed: '已完成',
  error: '出错',
  idle: '待执行',
  disabled: '已禁用',
  cancelled: '已取消',
  interrupted: '已中断',
}

const label = computed(() => props.label || labelMap[props.status] || props.status)
</script>

<style scoped>
.badge {
  display: inline-block;
  padding: 0.15rem 0.55rem;
  border-radius: 10px;
  font-size: 0.75rem;
  font-weight: 600;
  border: 1px solid transparent;
}
.badge.running { color: #60a5fa; border-color: #60a5fa33; background: #60a5fa11; }
.badge.completed { color: #4ade80; border-color: #4ade8033; background: #4ade8011; }
.badge.error { color: #ff6b6b; border-color: #ff6b6b33; background: #ff6b6b11; }
.badge.idle { color: #a0a0b0; border-color: #a0a0b033; background: #a0a0b011; }
.badge.disabled { color: #666; border-color: #666333; background: #666311; }
.badge.cancelled { color: #fbbf24; border-color: #fbbf2433; background: #fbbf2411; }
.badge.interrupted { color: #f97316; border-color: #f9731633; background: #f9731611; }
</style>
