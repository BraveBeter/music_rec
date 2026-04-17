import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  listTrainingProgress, getTrainingProgress, getTrainingHistory,
  cancelTraining as apiCancelTraining,
  runPreprocess, trainBaseline, trainSasrec, trainDeepfm, trainAll,
  trainingStreamUrl,
} from '@/api/admin'
import { useAuthStore } from '@/stores/auth'

export interface TaskProgress {
  task_id: string
  task_type: string
  status: string
  started_at: string | null
  current_epoch: number
  total_epochs: number
  current_phase: string
  phase_index: number
  total_phases: number
  train_loss: number | null
  val_loss: number | null
  best_val_loss: number | null
  metrics: Record<string, any>
  log_lines: string[]
  completed_at: string | null
  error: string | null
}

export const useTrainingStore = defineStore('training', () => {
  const activeTasks = ref<Record<string, TaskProgress>>({})
  const history = ref<TaskProgress[]>([])
  const eventSources = ref<Record<string, EventSource>>({})

  const triggerMap: Record<string, () => Promise<any>> = {
    preprocess: runPreprocess,
    train_baseline: trainBaseline,
    train_sasrec: trainSasrec,
    train_deepfm: trainDeepfm,
  }

  async function startTraining(taskType: string): Promise<string | null> {
    const fn = triggerMap[taskType]
    if (!fn) return null
    try {
      const { data } = await fn()
      const taskId = data.task_id
      if (taskId) {
        subscribeToTask(taskId)
      }
      return taskId
    } catch {
      return null
    }
  }

  async function startTrainAll(): Promise<string[]> {
    const { data } = await trainAll()
    const taskIds: string[] = []
    if (data.tasks) {
      for (const t of data.tasks) {
        if (t.task_id) {
          subscribeToTask(t.task_id)
          taskIds.push(t.task_id)
        }
      }
    }
    return taskIds
  }

  function subscribeToTask(taskId: string) {
    // Close existing connection if any
    unsubscribeFromTask(taskId)

    const auth = useAuthStore()
    const url = trainingStreamUrl(taskId, auth.token)
    const es = new EventSource(url)

    es.onmessage = (event) => {
      try {
        const progress: TaskProgress = JSON.parse(event.data)
        activeTasks.value[taskId] = progress

        if (['completed', 'error', 'interrupted', 'cancelled'].includes(progress.status)) {
          unsubscribeFromTask(taskId)
        }
      } catch { /* ignore parse errors */ }
    }

    es.onerror = () => {
      // Auto-close on error; component can re-subscribe
      es.close()
      delete eventSources.value[taskId]
    }

    eventSources.value[taskId] = es
  }

  function unsubscribeFromTask(taskId: string) {
    const es = eventSources.value[taskId]
    if (es) {
      es.close()
      delete eventSources.value[taskId]
    }
  }

  async function cancelTask(taskId: string) {
    await apiCancelTraining(taskId)
    unsubscribeFromTask(taskId)
    delete activeTasks.value[taskId]
  }

  async function fetchHistory(limit = 50) {
    try {
      const { data } = await getTrainingHistory(limit)
      history.value = data.history || []
    } catch { /* ignore */ }
  }

  async function fetchActiveTasks() {
    try {
      const { data } = await listTrainingProgress()
      const active = (data.progress || []).filter((t: TaskProgress) => t.status === 'running')
      for (const t of active) {
        activeTasks.value[t.task_id] = t
        if (!eventSources.value[t.task_id]) {
          subscribeToTask(t.task_id)
        }
      }
    } catch { /* ignore */ }
  }

  function cleanup() {
    for (const id of Object.keys(eventSources.value)) {
      eventSources.value[id].close()
    }
    eventSources.value = {}
  }

  return {
    activeTasks, history, eventSources,
    startTraining, startTrainAll,
    subscribeToTask, unsubscribeFromTask,
    cancelTask, fetchHistory, fetchActiveTasks, cleanup,
  }
})
