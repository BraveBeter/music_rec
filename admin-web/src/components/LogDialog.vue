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

        <!-- Tabs when report data is provided -->
        <div class="dialog-tabs" v-if="reportRows.length > 0">
          <button :class="['tab', activeTab === 'log' && 'active']" @click="activeTab = 'log'">日志</button>
          <button :class="['tab', activeTab === 'result' && 'active']" @click="activeTab = 'result'">结果</button>
        </div>

        <div class="dialog-body">
          <!-- Results table -->
          <div v-if="activeTab === 'result' && reportRows.length > 0" class="result-section">
            <div class="table-wrapper">
              <table class="result-table">
                <thead>
                  <tr>
                    <th>模型</th>
                    <th v-for="col in reportColumns" :key="col">{{ col }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in reportRows" :key="row.model">
                    <td class="model-cell">{{ modelLabels[row.model] || row.model }}</td>
                    <td v-for="col in reportColumns" :key="col">
                      <span v-if="row[col] !== undefined" class="metric-val">
                        {{ typeof row[col] === 'number' ? row[col].toFixed(4) : row[col] }}
                      </span>
                      <span v-else class="metric-na">-</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Log panel -->
          <div v-if="activeTab === 'log'">
            <LogPanel :lines="lines" />
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import LogPanel from './LogPanel.vue'
import StatusBadge from './StatusBadge.vue'

const props = defineProps<{
  title: string
  lines: string[]
  status?: string
  report?: any[]  // evaluation results array from per-task report JSON
}>()

const emit = defineEmits<{ close: [] }>()
function close() { emit('close') }

const activeTab = ref<'log' | 'result'>(
  props.report && props.report.length > 0 ? 'result' : 'log'
)

const modelLabels: Record<string, string> = {
  itemcf: 'ItemCF',
  item_cf: 'ItemCF',
  deepfm: 'DeepFM',
  sasrec: 'SASRec',
  multi_recall_funnel: 'Multi-recall Funnel',
}

// Extract unique metric keys from report rows
const reportColumns = computed(() => {
  if (!props.report || props.report.length === 0) return []
  const keys = new Set<string>()
  for (const row of props.report) {
    for (const k of Object.keys(row)) {
      if (k !== 'model' && typeof row[k] === 'number') keys.add(k)
    }
  }
  return Array.from(keys)
})

// Flatten report rows for the table
const reportRows = computed(() => {
  if (!props.report) return []
  return props.report.map(r => ({ model: r.model, ...r }))
})
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
  max-width: 900px;
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

/* Tabs */
.dialog-tabs {
  display: flex;
  border-bottom: 1px solid #2a2a4a;
  padding: 0 1.25rem;
}
.tab {
  background: none;
  border: none;
  color: #a0a0b0;
  padding: 0.6rem 1rem;
  cursor: pointer;
  font-size: 0.88rem;
  border-bottom: 2px solid transparent;
}
.tab:hover { color: #e0e0e0; }
.tab.active {
  color: #60a5fa;
  border-bottom-color: #60a5fa;
}

.dialog-body {
  padding: 1rem 1.25rem;
  overflow-y: auto;
  flex: 1;
}

/* Result table */
.result-section { margin-bottom: 0.5rem; }
.table-wrapper { overflow-x: auto; }
.result-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
.result-table th {
  text-align: left;
  padding: 0.45rem 0.5rem;
  color: #a0a0b0;
  border-bottom: 1px solid #2a2a4a;
  white-space: nowrap;
}
.result-table td {
  padding: 0.45rem 0.5rem;
  border-bottom: 1px solid #1a1a3e;
  white-space: nowrap;
}
.model-cell { font-weight: 600; color: #e0e0e0; }
.metric-val { color: #60a5fa; font-variant-numeric: tabular-nums; }
.metric-na { color: #4a4a6a; }
</style>
