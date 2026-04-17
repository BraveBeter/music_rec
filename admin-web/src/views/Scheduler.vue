<template>
  <div>
    <h1 class="page-title">定时任务</h1>

    <!-- Threshold Config -->
    <section class="panel">
      <h2>阈值自动训练</h2>
      <p class="desc">当交互记录增长超过阈值时，自动触发训练。</p>
      <div class="threshold-row">
        <span>当前交互数: <strong>{{ threshold.current_interaction_count }}</strong></span>
        <span>上次训练时: <strong>{{ threshold.last_training_count }}</strong></span>
        <span>增量: <strong>{{ threshold.current_interaction_count - threshold.last_training_count }}</strong></span>
      </div>
    </section>

    <!-- Schedule List -->
    <section class="panel">
      <div class="panel-header">
        <h2>调度任务</h2>
        <button @click="showForm = true" class="btn-add">新建任务</button>
      </div>

      <div v-if="store.schedules.length === 0" class="empty">暂无调度任务</div>
      <table v-else class="sched-table">
        <thead>
          <tr>
            <th>名称</th>
            <th>任务类型</th>
            <th>调度方式</th>
            <th>配置</th>
            <th>上次运行</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in store.schedules" :key="s.schedule_id">
            <td>{{ s.name }}</td>
            <td>{{ formatTaskType(s.task_type) }}</td>
            <td>{{ formatScheduleType(s.schedule_type) }}</td>
            <td>{{ formatConfig(s) }}</td>
            <td>{{ s.last_run_at ? new Date(s.last_run_at).toLocaleString('zh-CN') : '-' }}</td>
            <td><StatusBadge :status="s.is_enabled ? 'completed' : 'disabled'" :label="s.is_enabled ? '已启用' : '已禁用'" /></td>
            <td class="actions">
              <button @click="store.toggleSchedule(s.schedule_id)" class="btn-sm">
                {{ s.is_enabled ? '禁用' : '启用' }}
              </button>
              <button @click="removeSchedule(s.schedule_id)" class="btn-sm btn-danger">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- Add/Edit Form -->
    <section class="panel" v-if="showForm">
      <h2>新建调度任务</h2>
      <div class="form">
        <div class="form-row">
          <label>任务名称</label>
          <input v-model="form.name" placeholder="例: 每日重训练" />
        </div>
        <div class="form-row">
          <label>任务类型</label>
          <select v-model="form.task_type">
            <option value="preprocess">数据预处理</option>
            <option value="train_baseline">ItemCF + SVD</option>
            <option value="train_sasrec">SASRec</option>
            <option value="train_deepfm">DeepFM</option>
            <option value="train_all">全流程训练</option>
          </select>
        </div>
        <div class="form-row">
          <label>调度方式</label>
          <select v-model="form.schedule_type">
            <option value="cron">Cron 表达式</option>
            <option value="interval">固定间隔</option>
            <option value="threshold">阈值触发</option>
          </select>
        </div>
        <div class="form-row" v-if="form.schedule_type === 'cron'">
          <label>Cron 表达式</label>
          <input v-model="form.cron_expr" placeholder="分 时 日 月 周  例: 0 3 * * *" />
          <span class="hint">格式: 分 时 日 月 周 (UTC)</span>
        </div>
        <div class="form-row" v-if="form.schedule_type === 'interval'">
          <label>间隔 (分钟)</label>
          <input v-model.number="form.interval_minutes" type="number" placeholder="60" />
        </div>
        <div class="form-row" v-if="form.schedule_type === 'threshold'">
          <label>交互增量阈值</label>
          <input v-model.number="form.threshold_interactions" type="number" placeholder="1000" />
          <span class="hint">交互数增长超过此值时自动训练</span>
        </div>
        <div class="form-actions">
          <button @click="submitForm" class="btn-primary">创建</button>
          <button @click="showForm = false" class="btn-cancel">取消</button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useSchedulerStore } from '@/stores/scheduler'

const store = useSchedulerStore()
const showForm = ref(false)

const threshold = computed(() => store.threshold)

const form = reactive({
  name: '',
  task_type: 'train_all',
  schedule_type: 'cron',
  cron_expr: '',
  interval_minutes: 60,
  threshold_interactions: 1000,
})

function formatTaskType(t: string) {
  const map: Record<string, string> = {
    preprocess: '预处理',
    train_baseline: 'ItemCF+SVD',
    train_sasrec: 'SASRec',
    train_deepfm: 'DeepFM',
    train_all: '全流程',
  }
  return map[t] || t
}

function formatScheduleType(t: string) {
  const map: Record<string, string> = { cron: 'Cron', interval: '间隔', threshold: '阈值' }
  return map[t] || t
}

function formatConfig(s: any) {
  if (s.schedule_type === 'cron') return s.cron_expr || '-'
  if (s.schedule_type === 'interval') return `${s.interval_minutes} 分钟`
  if (s.schedule_type === 'threshold') return `${s.threshold_interactions} 条`
  return '-'
}

async function submitForm() {
  if (!form.name) return
  await store.createSchedule({
    name: form.name,
    task_type: form.task_type,
    schedule_type: form.schedule_type,
    cron_expr: form.schedule_type === 'cron' ? form.cron_expr : null,
    interval_minutes: form.schedule_type === 'interval' ? form.interval_minutes : null,
    threshold_interactions: form.schedule_type === 'threshold' ? form.threshold_interactions : null,
  })
  showForm.value = false
  form.name = ''
  form.cron_expr = ''
}

async function removeSchedule(id: number) {
  if (confirm('确定删除此调度任务？')) {
    await store.deleteSchedule(id)
  }
}

onMounted(() => {
  store.fetchSchedules()
  store.fetchThreshold()
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
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
.panel-header h2 { margin: 0; }
.desc { color: #a0a0b0; font-size: 0.85rem; margin: 0 0 0.75rem; }
.threshold-row { display: flex; gap: 2rem; font-size: 0.9rem; color: #a0a0b0; }
.threshold-row strong { color: #e0e0e0; }

.btn-add {
  padding: 0.4rem 0.8rem;
  background: #e94560;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
}
.btn-add:hover { background: #c73652; }

.empty { color: #4a4a6a; font-size: 0.9rem; padding: 0.5rem 0; }

.sched-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.sched-table th {
  text-align: left;
  padding: 0.5rem;
  color: #a0a0b0;
  border-bottom: 1px solid #2a2a4a;
}
.sched-table td {
  padding: 0.5rem;
  border-bottom: 1px solid #1a1a3e;
}
.actions { display: flex; gap: 0.4rem; }
.btn-sm {
  padding: 0.2rem 0.5rem;
  background: #0f3460;
  border: 1px solid #2a2a4a;
  color: #e0e0e0;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.75rem;
}
.btn-sm:hover { background: #1a4a8a; }
.btn-danger { border-color: #ff6b6b55; color: #ff6b6b; }
.btn-danger:hover { background: #ff6b6b22; }

.form { display: flex; flex-direction: column; gap: 0.75rem; }
.form-row { display: flex; flex-direction: column; gap: 0.25rem; }
.form-row label { font-size: 0.85rem; color: #a0a0b0; }
.form-row input, .form-row select {
  padding: 0.45rem 0.6rem;
  background: #0f3460;
  border: 1px solid #2a2a4a;
  color: #e0e0e0;
  border-radius: 6px;
  font-size: 0.9rem;
  max-width: 400px;
}
.form-row select { max-width: 200px; }
.hint { font-size: 0.75rem; color: #666; }
.form-actions { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
.btn-primary {
  padding: 0.45rem 1.2rem;
  background: #e94560;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9rem;
}
.btn-primary:hover { background: #c73652; }
.btn-cancel {
  padding: 0.45rem 1rem;
  background: none;
  border: 1px solid #3a3a5a;
  color: #a0a0b0;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9rem;
}
</style>
