<template>
  <div class="dashboard">
    <h1 class="page-title">Dashboard</h1>

    <!-- Stats -->
    <div class="stats">
      <StatCard v-for="s in stats" :key="s.label" :label="s.label" :value="s.value" />
    </div>

    <!-- Quick Model Status -->
    <section class="panel">
      <h2>模型状态</h2>
      <div class="model-grid">
        <div class="model-item" v-for="(available, name) in models" :key="name">
          <span :class="['dot', available ? 'green' : 'red']"></span>
          <span class="model-name">{{ name }}</span>
          <StatusBadge :status="available ? 'completed' : 'idle'" />
        </div>
      </div>
    </section>

    <!-- Recent Training -->
    <section class="panel">
      <h2>训练记录</h2>
      <div v-if="recentTraining.length === 0" class="empty">暂无训练记录</div>
      <div v-else class="task-list">
        <div class="task-row" v-for="t in recentTraining" :key="t.task_id">
          <div class="task-info">
            <span class="task-type">{{ formatType(t.task_type) }}</span>
            <span class="task-time">{{ formatTime(t.started_at) }}</span>
          </div>
          <StatusBadge :status="t.status as any" />
        </div>
      </div>
      <router-link to="/training" class="link">查看全部训练 &rarr;</router-link>
    </section>

    <!-- Recent Evaluations -->
    <section class="panel">
      <h2>评测记录</h2>
      <div v-if="recentEval.length === 0" class="empty">暂无评测记录</div>
      <div v-else class="task-list">
        <div class="task-row" v-for="t in recentEval" :key="t.task_id">
          <div class="task-info">
            <span class="task-type">模型评测</span>
            <span class="task-time">{{ formatTime(t.started_at) }}</span>
          </div>
          <StatusBadge :status="t.status as any" />
        </div>
      </div>
      <router-link to="/models" class="link">查看模型状态 &rarr;</router-link>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import StatCard from '@/components/StatCard.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { getSystemStatus, listTrainingProgress, getEvalHistory } from '@/api/admin'

const dataCounts = reactive<Record<string, number>>({ users: 0, tracks: 0, user_interactions: 0, track_features: 0, tags: 0 })
const models = reactive<Record<string, boolean>>({})
const recentTraining = ref<any[]>([])
const recentEval = ref<any[]>([])

const stats = computed(() => [
  { label: '用户数', value: dataCounts.users },
  { label: '曲目数', value: dataCounts.tracks },
  { label: '交互记录', value: dataCounts.user_interactions },
  { label: '曲目特征', value: dataCounts.track_features },
  { label: '曲风标签', value: dataCounts.tags },
])

function formatType(t: string) {
  const map: Record<string, string> = {
    preprocess: '数据预处理',
    feature_engineering: '特征工程',
    train_baseline: 'ItemCF + SVD',
    train_sasrec: 'SASRec',
    train_deepfm: 'DeepFM',
  }
  return map[t] || t
}

function formatTime(t: string | null) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN')
}

async function refresh() {
  try {
    const { data } = await getSystemStatus()
    Object.assign(dataCounts, data.data)
    Object.assign(models, data.models)
  } catch { /* ignore */ }

  try {
    const { data } = await listTrainingProgress()
    recentTraining.value = (data.progress || []).slice(0, 5)
  } catch { /* ignore */ }

  try {
    const { data } = await getEvalHistory()
    recentEval.value = (data.history || []).slice(0, 5)
  } catch { /* ignore */ }
}

onMounted(refresh)
</script>

<style scoped>
.page-title {
  font-size: 1.3rem;
  color: #e0e0e0;
  margin: 0 0 1.5rem;
}
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
  margin-bottom: 1.5rem;
}
.panel h2 {
  font-size: 1.05rem;
  margin: 0 0 1rem;
  color: #e0e0e0;
}
.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0.75rem;
}
.model-item {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.6rem 0.8rem;
  background: #0f3460;
  border-radius: 8px;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot.green { background: #4ade80; }
.dot.red { background: #ff6b6b; }
.model-name { flex: 1; }
.empty { color: #4a4a6a; font-size: 0.9rem; padding: 0.5rem 0; }
.task-list { display: flex; flex-direction: column; gap: 0.5rem; }
.task-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0.6rem;
  background: #0f3460;
  border-radius: 6px;
}
.task-info { display: flex; flex-direction: column; gap: 2px; }
.task-type { font-weight: 600; font-size: 0.9rem; }
.task-time { font-size: 0.78rem; color: #a0a0b0; }
.link {
  display: inline-block;
  margin-top: 0.75rem;
  color: #60a5fa;
  text-decoration: none;
  font-size: 0.85rem;
}
.link:hover { text-decoration: underline; }
</style>
