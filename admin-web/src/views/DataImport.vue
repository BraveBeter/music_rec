<template>
  <div>
    <h1 class="page-title">数据导入</h1>

    <!-- Current counts -->
    <div class="stats">
      <StatCard v-for="s in stats" :key="s.label" :label="s.label" :value="s.value" />
    </div>

    <!-- Import actions -->
    <section class="panel">
      <h2>数据源</h2>
      <div class="actions">
        <button @click="doImport('jamendo')" :disabled="loading">
          导入 Jamendo 曲目 (完整播放)
        </button>
        <button @click="doImport('deezer')" :disabled="loading">
          导入 Deezer 曲目 (30s 试听)
        </button>
        <button @click="doImport('lastfm')" :disabled="loading">
          生成 LastFM 用户数据 (~800人)
        </button>
        <button @click="doImport('synthetic')" :disabled="loading">
          生成合成用户数据 (60人)
        </button>
      </div>
      <p v-if="msg" :class="['msg', msgType]">{{ msg }}</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import StatCard from '@/components/StatCard.vue'
import { getSystemStatus, generateLastfm, generateSynthetic, importDeezer } from '@/api/admin'

const loading = ref(false)
const msg = ref('')
const msgType = ref('info')

const dataCounts = reactive<Record<string, number>>({ users: 0, tracks: 0, user_interactions: 0 })

const stats = computed(() => [
  { label: '用户数', value: dataCounts.users },
  { label: '曲目数', value: dataCounts.tracks },
  { label: '交互记录', value: dataCounts.user_interactions },
])

async function refreshCounts() {
  try {
    const { data } = await getSystemStatus()
    Object.assign(dataCounts, data.data)
  } catch { /* ignore */ }
}

async function doImport(type: string) {
  loading.value = true
  msg.value = '正在处理，请稍候...'
  msgType.value = 'info'
  try {
    if (type === 'lastfm') {
      const { data } = await generateLastfm()
      msg.value = `LastFM 数据生成已启动 (PID: ${data.pid})`
    } else if (type === 'synthetic') {
      const { data } = await generateSynthetic()
      msg.value = `合成数据生成已启动 (PID: ${data.pid})`
    } else if (type === 'deezer') {
      const { data } = await importDeezer()
      msg.value = `Deezer 导入完成: ${data.inserted} 首`
    } else if (type === 'jamendo') {
      const { data } = await importDeezer(
        ['rock', 'pop', 'hiphop', 'electronic', 'jazz', 'classical', 'rnb', 'latin'], 50
      )
      msg.value = `Jamendo 导入完成: ${data.inserted} 首`
    }
    msgType.value = 'success'
    setTimeout(refreshCounts, 3000)
  } catch (e: any) {
    msg.value = e.response?.data?.detail || '导入失败'
    msgType.value = 'error'
  } finally {
    loading.value = false
  }
}

onMounted(refreshCounts)
</script>

<style scoped>
.page-title { font-size: 1.3rem; color: #e0e0e0; margin: 0 0 1.5rem; }
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}
.panel {
  background: #16213e;
  border-radius: 10px;
  padding: 1.5rem;
}
.panel h2 { font-size: 1.05rem; margin: 0 0 1rem; color: #e0e0e0; }
.actions { display: flex; flex-wrap: wrap; gap: 0.75rem; }
.actions button {
  padding: 0.6rem 1.2rem;
  background: #0f3460;
  border: 1px solid #2a2a4a;
  color: #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.2s;
}
.actions button:hover:not(:disabled) { background: #1a4a8a; border-color: #4a90d9; }
.actions button:disabled { opacity: 0.5; cursor: not-allowed; }
.msg { margin-top: 0.75rem; font-size: 0.9rem; }
.msg.success { color: #4ade80; }
.msg.error { color: #ff6b6b; }
.msg.info { color: #60a5fa; }
</style>
