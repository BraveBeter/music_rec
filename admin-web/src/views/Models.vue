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
        <div class="eval-actions">
          <select v-model="evalTarget" class="eval-select" :disabled="evaluating">
            <option value="">全部生产模型</option>
            <option value="funnel">多路召回管线 (Funnel)</option>
            <optgroup v-for="(versions, model) in versionOptions" :key="model" :label="modelLabels[model] || model">
              <option v-for="v in versions" :key="v.version_id" :value="v.value">
                {{ v.label }}
              </option>
            </optgroup>
          </select>
          <button @click="startEvaluation" :disabled="evaluating" class="btn-eval">
            {{ evaluating ? '评测中...' : '开始评测' }}
          </button>
        </div>
      </div>

      <!-- Progress panel when evaluating -->
      <div v-if="evaluating && evalProgress" class="eval-progress">
        <div class="progress-header">
          <span class="progress-phase">{{ evalProgress.current_phase || '正在评测...' }}</span>
          <StatusBadge :status="evalProgress.status === 'running' ? 'running' : 'completed'" />
          <button @click="openEvalLog(evalProgress)" class="btn-log">日志</button>
        </div>
        <div v-if="evalProgress.error" class="eval-error">{{ evalProgress.error }}</div>
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

    <!-- Model Versions -->
    <section class="panel">
      <h2>模型版本</h2>
      <div v-if="!hasVersions" class="empty">暂无版本记录</div>
      <template v-else>
        <div v-for="(modelInfo, modelName) in versionData" :key="modelName" class="version-group">
          <h3 class="version-group-title">{{ modelLabels[modelName] || modelName }}</h3>
          <table class="history-table">
            <thead>
              <tr>
                <th>版本 ID</th>
                <th>状态</th>
                <th>保存时间</th>
                <th>NDCG@10</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(v, vid) in modelInfo.versions" :key="String(vid)" class="clickable-row">
                <td class="version-id-cell">{{ vid }}</td>
                <td><StatusBadge :status="versionStatusMap[v.status] || v.status" /></td>
                <td>{{ formatTime(v.saved_at) }}</td>
                <td>
                  <span v-if="v.metrics?.['ndcg@10'] !== undefined" class="metric-val">
                    {{ v.metrics['ndcg@10'].toFixed(4) }}
                  </span>
                  <span v-else class="metric-na">-</span>
                </td>
                <td>
                  <button v-if="v.status !== 'active'" @click="promoteVersion(modelName, String(vid))"
                          class="btn-promote">晋升</button>
                  <span v-else class="active-tag">当前生产</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </section>

    <!-- Evaluation History -->
    <section class="panel">
      <h2>评测历史</h2>
      <div v-if="evalHistory.length === 0" class="empty">暂无评测记录</div>
      <table v-else class="history-table">
        <thead>
          <tr>
            <th>状态</th>
            <th>开始时间</th>
            <th>耗时</th>
            <th>阶段</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="h in evalHistory" :key="h.task_id" class="clickable-row" @click="openEvalLog(h)">
            <td><StatusBadge :status="h.status as any" /></td>
            <td>{{ formatTime(h.started_at) }}</td>
            <td>{{ duration(h.started_at, h.completed_at) }}</td>
            <td>{{ h.current_phase || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <LogDialog
      v-if="logVisible"
      :title="logTitle"
      :lines="logLines"
      :status="logStatus"
      :report="logReport"
      @close="logVisible = false"
    />
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted, onUnmounted } from 'vue'
import StatusBadge from '@/components/StatusBadge.vue'
import LogDialog from '@/components/LogDialog.vue'
import { getSystemStatus, runEvaluation, trainingStreamUrl, getEvalHistory, listEvalProgress, getEvalReport, getModelVersions, promoteModelVersion } from '@/api/admin'
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
const evalHistory = ref<any[]>([])
const evalTarget = ref('')
const versionData = ref<Record<string, any>>({})
let eventSource: EventSource | null = null

const modelLabels: Record<string, string> = {
  item_cf: 'ItemCF',
  svd: 'SVD',
  deepfm: 'DeepFM',
  sasrec: 'SASRec',
  multi_recall_funnel: 'Multi-recall Funnel',
}

const versionStatusMap: Record<string, string> = {
  active: 'completed',
  superseded: 'idle',
  rejected: 'error',
  pending: 'running',
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
const hasVersions = computed(() => Object.keys(versionData.value).length > 0)

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

const versionOptions = computed(() => {
  const options: Record<string, { version_id: string; label: string; value: string }[]> = {}
  for (const [modelName, modelInfo] of Object.entries(versionData.value)) {
    const versions: { version_id: string; label: string; value: string }[] = []
    for (const [vid, v] of Object.entries((modelInfo as any).versions || {})) {
      const ndcg = (v as any).metrics?.['ndcg@10']
      const ndcgStr = ndcg !== undefined ? ` NDCG@10: ${ndcg.toFixed(4)}` : ''
      const statusTag = (v as any).status === 'active' ? ' [生产]' : (v as any).status === 'rejected' ? ' [已拒绝]' : ' [已淘汰]'
      versions.push({
        version_id: vid,
        label: `${vid}${statusTag}${ndcgStr}`,
        value: `${modelName}:${vid}`,
      })
    }
    if (versions.length > 0) {
      options[modelName] = versions
    }
  }
  return options
})

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

async function fetchEvalHistory() {
  try {
    const { data } = await getEvalHistory()
    evalHistory.value = data.history || []
  } catch { /* ignore */ }
}

async function fetchVersions() {
  try {
    const { data } = await getModelVersions()
    versionData.value = data.models || {}
  } catch { /* ignore */ }
}

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

  fetchEvalHistory()
  fetchVersions()
  reconnectEvalSSE()
}

function reconnectEvalSSE() {
  listEvalProgress().then(({ data }) => {
    const running = (data.progress || []).find((t: any) => t.status === 'running')
    if (running) {
      evaluating.value = true
      evalProgress.value = running
      subscribeEvalSSE(running.task_id)
    }
  }).catch(() => { /* ignore */ })
}

function subscribeEvalSSE(taskId: string) {
  closeEventSource()
  const url = trainingStreamUrl(taskId, auth.token)
  eventSource = new EventSource(url)
  let gotData = false

  eventSource.onmessage = (event) => {
    try {
      const progress = JSON.parse(event.data)
      gotData = true
      evalProgress.value = progress

      if (progress.status === 'not_found') {
        closeEventSource()
        evaluating.value = false
        return
      }

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
    if (!gotData) {
      evaluating.value = false
      refresh()
    }
  }
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

  let model: string | undefined
  let versionId: string | undefined

  if (evalTarget.value) {
    const parts = evalTarget.value.split(':')
    model = parts[0]
    versionId = parts[1]
  }

  try {
    const { data } = await runEvaluation(model, versionId)
    const taskId = data.task_id
    if (!taskId || data.status === 'already_running') {
      evaluating.value = false
      return
    }

    subscribeEvalSSE(taskId)
  } catch {
    evaluating.value = false
  }
}

async function promoteVersion(modelName: string, versionId: string) {
  try {
    await promoteModelVersion(modelName, versionId)
    fetchVersions()
  } catch { /* ignore */ }
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

// Log dialog
const logVisible = ref(false)
const logTitle = ref('')
const logLines = ref<string[]>([])
const logStatus = ref<string | undefined>()
const logReport = ref<any[]>([])

async function openEvalLog(task: any) {
  logTitle.value = '模型评测 — 日志'
  logLines.value = task.log_lines || []
  logStatus.value = task.status
  logReport.value = []

  if (['completed'].includes(task.status) && task.task_id) {
    try {
      const { data } = await getEvalReport(task.task_id)
      if (data.results) {
        logReport.value = data.results
        logTitle.value = '模型评测'
      }
    } catch { /* ignore */ }
  }

  logVisible.value = true
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
.eval-actions { display: flex; gap: 0.5rem; align-items: center; }
.eval-select {
  padding: 0.4rem 0.6rem;
  background: #0f3460;
  color: #e0e0e0;
  border: 1px solid #2a2a4a;
  border-radius: 6px;
  font-size: 0.85rem;
  max-width: 320px;
}
.eval-select:disabled { opacity: 0.6; }
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
.btn-log {
  background: none;
  border: 1px solid #60a5fa;
  color: #60a5fa;
  padding: 0.2rem 0.5rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.75rem;
}
.btn-log:hover { background: #60a5fa22; }
.progress-phase { font-size: 0.9rem; color: #e0e0e0; }
.eval-error {
  color: #ff6b6b;
  font-size: 0.85rem;
  padding: 0.4rem 0;
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

/* Version table */
.version-group { margin-bottom: 1rem; }
.version-group:last-child { margin-bottom: 0; }
.version-group-title {
  font-size: 0.9rem;
  color: #a0a0b0;
  margin: 0 0 0.5rem;
  padding-bottom: 0.3rem;
  border-bottom: 1px solid #1a1a3e;
}
.version-id-cell {
  font-family: monospace;
  font-size: 0.8rem;
  color: #8a8aaa;
}
.btn-promote {
  padding: 0.2rem 0.5rem;
  background: none;
  border: 1px solid #4ade80;
  color: #4ade80;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.75rem;
}
.btn-promote:hover { background: #4ade8022; }
.active-tag {
  color: #4ade80;
  font-size: 0.8rem;
}

/* History table */
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
.clickable-row { cursor: pointer; }
.clickable-row:hover { background: #1a2a4e; }
</style>
