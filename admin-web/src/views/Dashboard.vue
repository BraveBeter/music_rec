<template>
  <div class="dashboard">
    <header>
      <h1>MusicRec 管理面板</h1>
      <div class="header-right">
        <span>{{ auth.username }}</span>
        <button @click="auth.logout()" class="btn-logout">退出</button>
      </div>
    </header>

    <!-- Stats Cards -->
    <section class="stats">
      <div class="stat-card" v-for="s in stats" :key="s.label">
        <div class="stat-value">{{ s.value }}</div>
        <div class="stat-label">{{ s.label }}</div>
      </div>
    </section>

    <!-- Data Import -->
    <section class="panel">
      <h2>数据导入</h2>
      <div class="actions">
        <button @click="doImport('jamendo')" :disabled="taskLoading">
          导入 Jamendo 曲目 (完整播放)
        </button>
        <button @click="doImport('deezer')" :disabled="taskLoading">
          导入 Deezer 曲目 (30s 试听)
        </button>
        <button @click="doImport('lastfm')" :disabled="taskLoading">
          生成 LastFM 用户数据 (~800人)
        </button>
        <button @click="doImport('synthetic')" :disabled="taskLoading">
          生成合成用户数据 (60人)
        </button>
      </div>
      <p v-if="taskMsg" :class="['task-msg', taskMsgType]">{{ taskMsg }}</p>
    </section>

    <!-- Training -->
    <section class="panel">
      <h2>模型训练</h2>
      <div class="training-flow">
        <div class="step" v-for="(step, i) in trainingSteps" :key="i">
          <div class="step-num">{{ i + 1 }}</div>
          <div class="step-info">
            <span class="step-name">{{ step.name }}</span>
            <span class="step-desc">{{ step.desc }}</span>
          </div>
          <button
            @click="doTrain(step.action)"
            :disabled="step.loading"
            :class="['btn-train', step.status]"
          >
            <template v-if="step.loading">执行中...</template>
            <template v-else-if="step.status === 'done'">完成</template>
            <template v-else>执行</template>
          </button>
        </div>
      </div>
      <div class="train-all">
        <button @click="trainAll" :disabled="trainAllLoading" class="btn-primary">
          {{ trainAllLoading ? '一键训练中...' : '一键全流程训练' }}
        </button>
      </div>
    </section>

    <!-- Model Status -->
    <section class="panel">
      <h2>模型状态</h2>
      <div class="model-grid">
        <div class="model-item" v-for="(available, name) in models" :key="name">
          <span :class="['model-dot', available ? 'green' : 'red']"></span>
          <span>{{ name }}</span>
          <span class="model-status">{{ available ? '已训练' : '未训练' }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import {
  getSystemStatus, generateLastfm, generateSynthetic,
  importDeezer, runPreprocess, trainBaseline, trainSasrec, trainDeepfm,
} from '@/api/admin'

const auth = useAuthStore()

// System status
const dataCounts = reactive<Record<string, number>>({ users: 0, tracks: 0, user_interactions: 0, track_features: 0, tags: 0 })
const models = reactive<Record<string, boolean>>({})

const stats = computed(() => [
  { label: '用户数', value: dataCounts.users },
  { label: '曲目数', value: dataCounts.tracks },
  { label: '交互记录', value: dataCounts.user_interactions },
  { label: '曲目特征', value: dataCounts.track_features },
  { label: '曲风标签', value: dataCounts.tags },
])

async function refreshStatus() {
  try {
    const { data } = await getSystemStatus()
    Object.assign(dataCounts, data.data)
    Object.assign(models, data.models)
  } catch { /* ignore */ }
}

onMounted(() => { refreshStatus() })

// Data import
const taskLoading = ref(false)
const taskMsg = ref('')
const taskMsgType = ref('info')

async function doImport(type: string) {
  taskLoading.value = true
  taskMsg.value = '正在导入，请稍候...'
  taskMsgType.value = 'info'
  try {
    if (type === 'lastfm') {
      const { data } = await generateLastfm()
      taskMsg.value = `LastFM 数据生成已启动 (PID: ${data.pid})`
    } else if (type === 'synthetic') {
      const { data } = await generateSynthetic()
      taskMsg.value = `合成数据生成已启动 (PID: ${data.pid})`
    } else if (type === 'deezer') {
      const { data } = await importDeezer()
      taskMsg.value = `Deezer 导入完成: ${data.inserted} 首`
    } else if (type === 'jamendo') {
      const { data } = await importDeezer(
        ['rock', 'pop', 'hiphop', 'electronic', 'jazz', 'classical', 'rnb', 'latin'], 50
      )
      taskMsg.value = `Jamendo 导入完成: ${data.inserted} 首`
    }
    taskMsgType.value = 'success'
    setTimeout(refreshStatus, 3000)
  } catch (e: any) {
    taskMsg.value = e.response?.data?.detail || '导入失败'
    taskMsgType.value = 'error'
  } finally {
    taskLoading.value = false
  }
}

// Training
const trainingSteps = reactive([
  { name: '数据预处理', desc: '清洗交互数据，生成训练集', action: 'preprocess', loading: false, status: '' },
  { name: 'ItemCF 训练', desc: '协同过滤基线模型', action: 'baseline', loading: false, status: '' },
  { name: 'SASRec 训练', desc: '自注意力序列模型', action: 'sasrec', loading: false, status: '' },
  { name: 'DeepFM 训练', desc: '深度特征交叉排序模型', action: 'deepfm', loading: false, status: '' },
])

const actionMap: Record<string, () => Promise<any>> = {
  preprocess: runPreprocess,
  baseline: trainBaseline,
  sasrec: trainSasrec,
  deepfm: trainDeepfm,
}

async function doTrain(action: string) {
  const step = trainingSteps.find(s => s.action === action)
  if (!step) return
  step.loading = true
  step.status = ''
  try {
    await actionMap[action]()
    step.status = 'done'
    refreshStatus()
  } catch (e: any) {
    step.status = 'error'
    alert(e.response?.data?.detail || '训练失败')
  } finally {
    step.loading = false
  }
}

const trainAllLoading = ref(false)

async function trainAll() {
  trainAllLoading.value = true
  for (const step of trainingSteps) {
    step.status = ''
  }
  for (const step of trainingSteps) {
    step.loading = true
    try {
      await actionMap[step.action]()
      step.status = 'done'
    } catch {
      step.status = 'error'
      break
    } finally {
      step.loading = false
    }
  }
  trainAllLoading.value = false
  refreshStatus()
}
</script>

<style scoped>
.dashboard {
  max-width: 960px;
  margin: 0 auto;
  padding: 1.5rem;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  color: #e0e0e0;
  background: #1a1a2e;
  min-height: 100vh;
}

header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #2a2a4a;
}
header h1 { font-size: 1.3rem; color: #e94560; margin: 0; }
.header-right { display: flex; align-items: center; gap: 1rem; }
.header-right span { color: #a0a0b0; font-size: 0.9rem; }
.btn-logout {
  background: none;
  border: 1px solid #e94560;
  color: #e94560;
  padding: 0.3rem 0.8rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
}
.btn-logout:hover { background: #e94560; color: white; }

/* Stats */
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}
.stat-card {
  background: #16213e;
  border-radius: 10px;
  padding: 1.2rem;
  text-align: center;
}
.stat-value { font-size: 1.8rem; font-weight: 700; color: #e94560; }
.stat-label { font-size: 0.85rem; color: #a0a0b0; margin-top: 0.3rem; }

/* Panels */
.panel {
  background: #16213e;
  border-radius: 10px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}
.panel h2 {
  font-size: 1.1rem;
  margin: 0 0 1rem;
  color: #e0e0e0;
}

/* Actions */
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}
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

.task-msg { margin-top: 0.75rem; font-size: 0.9rem; }
.task-msg.success { color: #4ade80; }
.task-msg.error { color: #ff6b6b; }
.task-msg.info { color: #60a5fa; }

/* Training Flow */
.training-flow {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.step {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  background: #0f3460;
  border-radius: 8px;
}
.step-num {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #e94560;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.85rem;
  font-weight: 700;
  flex-shrink: 0;
}
.step-info { flex: 1; display: flex; flex-direction: column; }
.step-name { font-weight: 600; }
.step-desc { font-size: 0.8rem; color: #a0a0b0; }

.btn-train {
  padding: 0.4rem 1rem;
  border: 1px solid #2a2a4a;
  background: #16213e;
  color: #e0e0e0;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  min-width: 70px;
}
.btn-train:hover:not(:disabled) { background: #1a4a8a; }
.btn-train:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-train.done { border-color: #4ade80; color: #4ade80; }
.btn-train.error { border-color: #ff6b6b; color: #ff6b6b; }

.train-all { margin-top: 1rem; text-align: center; }
.btn-primary {
  padding: 0.7rem 2rem;
  background: #e94560;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1rem;
  font-weight: 600;
}
.btn-primary:hover:not(:disabled) { background: #c73652; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }

/* Models */
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
.model-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.model-dot.green { background: #4ade80; }
.model-dot.red { background: #ff6b6b; }
.model-status { font-size: 0.8rem; color: #a0a0b0; margin-left: auto; }
</style>
