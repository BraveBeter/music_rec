import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getSchedules, createSchedule as apiCreate, updateSchedule as apiUpdate,
  deleteSchedule as apiDelete, toggleSchedule as apiToggle,
  getThreshold, updateThreshold as apiUpdateThreshold,
} from '@/api/admin'

export interface Schedule {
  schedule_id: number
  name: string
  task_type: string
  schedule_type: string
  cron_expr: string | null
  interval_minutes: number | null
  threshold_interactions: number | null
  is_enabled: boolean
  last_run_at: string | null
  next_run_at: string | null
  created_at: string | null
}

export interface ThresholdState {
  last_training_count: number
  current_interaction_count: number
}

export const useSchedulerStore = defineStore('scheduler', () => {
  const schedules = ref<Schedule[]>([])
  const threshold = ref<ThresholdState>({ last_training_count: 0, current_interaction_count: 0 })

  async function fetchSchedules() {
    try {
      const { data } = await getSchedules()
      schedules.value = data.schedules || []
    } catch { /* ignore */ }
  }

  async function createSchedule(formData: any) {
    const { data } = await apiCreate(formData)
    await fetchSchedules()
    return data
  }

  async function updateSchedule(id: number, formData: any) {
    const { data } = await apiUpdate(id, formData)
    await fetchSchedules()
    return data
  }

  async function deleteSchedule(id: number) {
    await apiDelete(id)
    await fetchSchedules()
  }

  async function toggleSchedule(id: number) {
    const { data } = await apiToggle(id)
    await fetchSchedules()
    return data
  }

  async function fetchThreshold() {
    try {
      const { data } = await getThreshold()
      threshold.value = data
    } catch { /* ignore */ }
  }

  async function updateThresholdValue(count: number) {
    await apiUpdateThreshold(count)
    await fetchThreshold()
  }

  return {
    schedules, threshold,
    fetchSchedules, createSchedule, updateSchedule,
    deleteSchedule, toggleSchedule,
    fetchThreshold, updateThresholdValue,
  }
})
