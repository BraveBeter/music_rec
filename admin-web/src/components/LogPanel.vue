<template>
  <div class="log-panel" ref="panelRef">
    <div class="log-line" v-for="(line, i) in lines" :key="i">{{ line }}</div>
    <div v-if="!lines.length" class="log-empty">暂无日志</div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'

const props = withDefaults(defineProps<{
  lines: string[]
  autoScroll?: boolean
}>(), { autoScroll: true })

const panelRef = ref<HTMLElement | null>(null)

watch(() => props.lines.length, async () => {
  if (props.autoScroll) {
    await nextTick()
    if (panelRef.value) {
      panelRef.value.scrollTop = panelRef.value.scrollHeight
    }
  }
})
</script>

<style scoped>
.log-panel {
  background: #0a0a1a;
  border: 1px solid #1a1a3e;
  border-radius: 6px;
  padding: 0.75rem;
  max-height: 300px;
  overflow-y: auto;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 0.78rem;
  line-height: 1.5;
  color: #a0a0b0;
}
.log-line {
  white-space: pre-wrap;
  word-break: break-all;
}
.log-empty {
  color: #4a4a6a;
  font-style: italic;
}
</style>
