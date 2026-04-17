<template>
  <div>
    <h1 class="page-title">模型状态</h1>

    <!-- Model Grid -->
    <section class="panel">
      <h2>模型可用性</h2>
      <div class="model-grid">
        <div class="model-card" v-for="(info, name) in modelDetails" :key="name">
          <div class="model-header">
            <span :class="['dot', info.available ? 'green' : 'red']"></span>
            <span class="model-name">{{ modelLabels[name] || name }}</span>
            <StatusBadge :status="info.available ? 'completed' : 'idle'" />
          </div>
          <div class="model-detail" v-if="info.available">
            <div class="detail-row" v-if="info.meta">
              <span class="detail-label">参数</span>
              <span class="detail-value">{{ formatMeta(info.meta) }}</span>
            </div>
            <div class="detail-row" v-if="info.report">
              <span class="detail-label">指标</span>
              <span class="detail-value">{{ formatReport(info.report) }}</span>
            </div>
          </div>
          <div class="model-empty" v-else>模型未训练</div>
        </div>
      </div>
    </section>

    <!-- Evaluation -->
    <section class="panel">
      <div class="panel-header">
        <h2>评测指标对比</h2>
        <button @click="startEvaluation" :disabled="evaluating" class="btn-eval">
          {{ evaluating ? '评测中...' : '开始评测' }}
        </button>
      </div>

      <!-- Progress panel when evaluating -->
      <div v-if="evaluating && evalProgress" class="eval-progress">
        <div class="progress-header">
          <span class="progress-phase">{{ evalProgress.current_phase || '正在评测...' }}</span>
          <StatusBadge :status="evalProgress.status === 'running' ? 'running' : 'completed'" />
        </div>
        <div v-if="evalProgress.log_lines && evalProgress.log_lines.length" class="log-panel">
          <div v-for="(line, i) in evalProgress.log_lines.slice(-15)" :key="i" class="log-line">{{ line }}</div>
        </div>
      </div>

      <!-- Results table -->
      <div v-if="hasReports">
        <p class="desc" v-if="evalUsers">基于 {{ evalUsers }} 位用户的测试集评测结果</p>
        <div class="table-wrapper">
          <table class="eval-table">
            <thead>
              <tr>
                <th>模型</th>
                <th v-for="col in metricColumns" :key="col.key">{{ col.label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in tableRows" :key="row.model">
                <td class="model-cell">{{ row.label }}</td>
                <td v-for="col in metricColumns" :key="col.key">
                  <span v-if="row.metrics[col.key] !== undefined" class="metric-val">
                    {{ row.metrics[col.key].toFixed(4) }}
                  </span>
                  <span v-else class="metric-na">-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-else-if="!evaluating" class="empty-eval">
        <p>暂无评测数据。点击「开始评测」对已训练模型进行评测。</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted, onUnmounted } from 'vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { getSystemStatus, runEvaluation, trainingStreamUrl } from '@/api/admin'
import { useAuthStore } from '@/stores/auth'

interface ModelInfo {
  available: boolean
  meta: Record<string, any> | null
  report: Record<string, any> | null
}

const auth = useAuthStore()
const modelDetails = reactive<Record<string, ModelInfo>>({})
const evalReports = reactive<Record<string, { eval_users: number; metrics: Record<string, number> }>>({})
const evaluating = ref(false)
const evalProgress = ref<Record<string, any> | null>(null)
let eventSource: EventSource | null = null

const modelLabels: Record<string, string> = {
  item_cf: 'ItemCF',
  svd: 'SVD',
  deepfm: 'DeepFM',
  sasrec: 'SASRec',
  multi_recall_funnel: 'Multi-recall Funnel',
}

const metricColumns = [
  { key: 'precision@5', label: 'P@5' },
  { key: 'recall@5', label: 'R@5' },
  { key: 'hr@5', label: 'HR@5' },
  { key: 'ndcg@5', label: 'NDCG@5' },
  { key: 'precision@10', label: 'P@10' },
  { key: 'recall@10', label: 'R@10' },
  { key: 'hr@10', label: 'HR@10' },
  { key: 'ndcg@10', label: 'NDCG@10' },
  { key: 'coverage', label: 'Coverage' },
]

const hasReports = computed(() => Object.keys(evalReports).length > 0)

const evalUsers = computed(() => {
  const users = Object.values(evalReports).map(r => r.eval_users)
  return users.length > 0 ? Math.max(...users) : 0
})

const tableRows = computed(() => {
  const order = ['itemcf', 'deepfm', 'sasrec', 'multi_recall_funnel']
  return order
    .filter(key => evalReports[key])
    .map(key => ({
      model: key,
      label: modelLabels[key] || key,
      metrics: evalReports[key].metrics,
    }))
})

async function refresh() {
  try {
    const { data } = await getSystemStatus()
    const models = data.models || {}
    const reports = data.reports || {}

    for (const [name, available] of Object.entries(models)) {
      modelDetails[name] = {
        available: !!available,
        meta: null,
        report: null,
      }
    }

    for (const [key, val] of Object.entries(reports)) {
      if (val && typeof val === 'object' && 'metrics' in val) {
        evalReports[key] = val as any
      }
    }
  } catch { /* ignore */ }
}

function closeEventSource() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

async function startEvaluation() {
  evaluating.value = true
  evalProgress.value = null

  try {
    const { data } = await runEvaluation()
    const taskId = data.task_id
    if (!taskId) {
      evaluating.value = false
      return
    }

    // Subscribe to SSE for real-time progress
    const url = trainingStreamUrl(taskId, auth.token)
    eventSource = new EventSource(url)

    eventSource.onmessage = (event) => {
      try {
        const progress = JSON.parse(event.data)
        evalProgress.value = progress

        if (['completed', 'error', 'interrupted', 'cancelled'].includes(progress.status)) {
          closeEventSource()
          evaluating.value = false
          if (progress.status === 'completed') {
            refresh()
          }
        }
      } catch { /* ignore parse errors */ }
    }

    eventSource.onerror = () => {
      closeEventSource()
      evaluating.value = false
      refresh()
    }
  } catch {
    evaluating.value = false
  }
}

function formatMeta(meta: Record<string, any>) {
  return Object.entries(meta)
    .filter(([k]) => !['sparse_features', 'dense_features', 'sparse_dims'].includes(k))
    .map(([k, v]) => `${k}=${v}`)
    .join(', ')
}

function formatReport(report: Record<string, any>) {
  return Object.entries(report)
    .filter(([k, v]) => typeof v === 'number')
    .map(([k, v]) => `${k}=${typeof v === 'number' ? v.toFixed(4) : v}`)
    .join(', ')
}

onMounted(refresh)
onUnmounted(closeEventSource)
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
.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1rem;
}
.model-card {
  background: #0f3460;
  border-radius: 8px;
  padding: 1rem;
}
.model-header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 0.5rem;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot.green { background: #4ade80; }
.dot.red { background: #ff6b6b; }
.model-name { flex: 1; font-weight: 600; }
.model-detail {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid #1a1a3e;
}
.detail-row { font-size: 0.82rem; }
.detail-label { color: #a0a0b0; margin-right: 0.5rem; }
.detail-value { color: #60a5fa; }
.model-empty { color: #4a4a6a; font-size: 0.85rem; margin-top: 0.5rem; }

.desc { color: #a0a0b0; font-size: 0.85rem; margin: 0 0 0.75rem; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
.panel-header h2 { margin: 0; }
.btn-eval {
  padding: 0.4rem 0.8rem;
  background: #e94560;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
}
.btn-eval:hover:not(:disabled) { background: #c73652; }
.btn-eval:disabled { opacity: 0.6; cursor: not-allowed; }
.empty-eval { color: #4a4a6a; font-size: 0.9rem; }

/* Evaluation progress */
.eval-progress { margin-bottom: 1rem; }
.progress-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}
.progress-phase { font-size: 0.9rem; color: #e0e0e0; }
.log-panel {
  background: #0a0a1a;
  border-radius: 6px;
  padding: 0.6rem 0.8rem;
  max-height: 240px;
  overflow-y: auto;
  font-family: monospace;
  font-size: 0.78rem;
}
.log-line {
  color: #8a8aaa;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}

/* Evaluation table */
.table-wrapper { overflow-x: auto; }
.eval-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.eval-table th {
  text-align: left;
  padding: 0.5rem 0.6rem;
  color: #a0a0b0;
  border-bottom: 1px solid #2a2a4a;
  white-space: nowrap;
}
.eval-table td {
  padding: 0.5rem 0.6rem;
  border-bottom: 1px solid #1a1a3e;
  white-space: nowrap;
}
.model-cell { font-weight: 600; color: #e0e0e0; }
.metric-val { color: #60a5fa; font-variant-numeric: tabular-nums; }
.metric-na { color: #4a4a6a; }
</style>
