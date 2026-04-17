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
            <span class="model-name">{{ name }}</span>
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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { getSystemStatus } from '@/api/admin'

interface ModelInfo {
  available: boolean
  meta: Record<string, any> | null
  report: Record<string, any> | null
}

const modelDetails = reactive<Record<string, ModelInfo>>({})

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

onMounted(refresh)
</script>

<style scoped>
.page-title { font-size: 1.3rem; color: #e0e0e0; margin: 0 0 1.5rem; }
.panel {
  background: #16213e;
  border-radius: 10px;
  padding: 1.5rem;
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
</style>
