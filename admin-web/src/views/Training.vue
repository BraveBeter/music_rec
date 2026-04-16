<template>
  <div>
    <h1 class="page-title">模型训练</h1>

    <!-- Training Controls -->
    <section class="panel">
      <h2>训练控制</h2>
      <div class="controls">
        <button v-for="s in steps" :key="s.action"
          @click="startOne(s.action)"
          :disabled="isAnyRunning || s.running"
          class="btn-step"
        >
          {{ s.name }}
        </button>
        <button @click="startAll" :disabled="isAnyRunning" class="btn-all">
          一键全流程训练
        </button>
      </div>
    </section>

    <!-- Active Training -->
    <section class="panel" v-if="activeList.length > 0">
      <h2>训练进度</h2>
      <div class="active-list">
        <div class="task-card" v-for="task in activeList" :key="task.task_id">
          <div class="task-header">
            <span class="task-type">{{ formatType(task.task_type) }}</span>
            <StatusBadge :status="task.status as any" />
            <button @click="store.cancelTask(task.task_id)" class="btn-cancel" v-if="task.status === 'running'">取消</button>
          </div>
          <template v-if="task.total_epochs > 0">
            <ProgressBar :current="task.current_epoch" :total="task.total_epochs" :status="task.status as any" />
            <div class="epoch-text">Epoch {{ task.current_epoch }} / {{ task.total_epochs }}</div>
          </template>
          <template v-else-if="task.total_phases > 0">
            <ProgressBar :current="task.phase_index" :total="task.total_phases" :status="task.status as any" />
            <div class="phase-text">{{ task.current_phase || '准备中...' }} ({{ task.phase_index }}/{{ task.total_phases }})</div>
          </template>
          <div class="metrics" v-if="task.train_loss !== null">
            <span>Train Loss: {{ task.train_loss?.toFixed(4) }}</span>
            <span v-if="task.val_loss !== null"> | Val Loss: {{ task.val_loss?.toFixed(4) }}</span>
            <span v-if="task.best_val_loss !== null"> | Best: {{ task.best_val_loss?.toFixed(4) }}</span>
          </div>
        </div>
      </div>

      <!-- Log Panel (first active task) -->
      <div class="log-section" v-if="firstActive">
        <h3>训练日志</h3>
        <LogPanel :lines="firstActive.log_lines || []" />
      </div>
    </section>

    <!-- Training History -->
    <section class="panel">
      <h2>训练历史</h2>
      <div v-if="store.history.length === 0" class="empty">暂无历史记录</div>
      <table v-else class="history-table">
        <thead>
          <tr>
            <th>任务类型</th>
            <th>开始时间</th>
            <th>耗时</th>
            <th>Epoch</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="h in store.history" :key="h.task_id">
            <td>{{ formatType(h.task_type) }}</td>
            <td>{{ formatTime(h.started_at) }}</td>
            <td>{{ duration(h.started_at, h.completed_at) }}</td>
            <td>{{ h.current_epoch || h.phase_index || '-' }}</td>
            <td><StatusBadge :status="h.status as any" /></td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import ProgressBar from '@/components/ProgressBar.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import LogPanel from '@/components/LogPanel.vue'
import { useTrainingStore } from '@/stores/training'

const store = useTrainingStore()

const steps = [
  { action: 'preprocess', name: '数据预处理', running: false },
  { action: 'train_baseline', name: 'ItemCF + SVD', running: false },
  { action: 'train_sasrec', name: 'SASRec', running: false },
  { action: 'train_deepfm', name: 'DeepFM', running: false },
]

const activeList = computed(() => Object.values(store.activeTasks))
const firstActive = computed(() => activeList.value[0] || null)
const isAnyRunning = computed(() => activeList.value.some(t => t.status === 'running'))

function formatType(t: string) {
  const map: Record<string, string> = {
    preprocess: '数据预处理',
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

function duration(start: string | null, end: string | null) {
  if (!start) return '-'
  const s = new Date(start).getTime()
  const e = end ? new Date(end).getTime() : Date.now()
  const sec = Math.round((e - s) / 1000)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  return `${min}m ${sec % 60}s`
}

async function startOne(action: string) {
  await store.startTraining(action)
}

async function startAll() {
  await store.startTrainAll()
}

onMounted(() => {
  store.fetchActiveTasks()
  store.fetchHistory()
})

onUnmounted(() => {
  store.cleanup()
})
</script>

<style scoped>
.page-title { font-size: 1.3rem; color: #e0e0e0; margin: 0 0 1.5rem; }
.panel {
  background: #16213e;
  border-radius: 10px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}
.panel h2 { font-size: 1.05rem; margin: 0 0 1rem; color: #e0e0e0; }
.panel h3 { font-size: 0.95rem; margin: 1rem 0 0.5rem; color: #a0a0b0; }

.controls { display: flex; flex-wrap: wrap; gap: 0.75rem; }
.btn-step {
  padding: 0.55rem 1.1rem;
  background: #0f3460;
  border: 1px solid #2a2a4a;
  color: #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: all 0.2s;
}
.btn-step:hover:not(:disabled) { background: #1a4a8a; border-color: #4a90d9; }
.btn-step:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-all {
  padding: 0.55rem 1.5rem;
  background: #e94560;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 600;
}
.btn-all:hover:not(:disabled) { background: #c73652; }
.btn-all:disabled { opacity: 0.5; cursor: not-allowed; }

.active-list { display: flex; flex-direction: column; gap: 1rem; }
.task-card {
  background: #0f3460;
  border-radius: 8px;
  padding: 1rem;
}
.task-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}
.task-type { font-weight: 600; flex: 1; }
.btn-cancel {
  background: none;
  border: 1px solid #ff6b6b;
  color: #ff6b6b;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.75rem;
}
.btn-cancel:hover { background: #ff6b6b22; }
.epoch-text, .phase-text { font-size: 0.8rem; color: #a0a0b0; margin-top: 0.3rem; }
.metrics { font-size: 0.8rem; color: #60a5fa; margin-top: 0.3rem; }

.log-section { margin-top: 1rem; }
.empty { color: #4a4a6a; font-size: 0.9rem; padding: 0.5rem 0; }

.history-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.history-table th {
  text-align: left;
  padding: 0.5rem;
  color: #a0a0b0;
  border-bottom: 1px solid #2a2a4a;
}
.history-table td {
  padding: 0.5rem;
  border-bottom: 1px solid #1a1a3e;
}
</style>
