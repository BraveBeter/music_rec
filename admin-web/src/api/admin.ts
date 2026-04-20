import adminClient from './client'

// Auth
export const login = (username: string, password: string) =>
  adminClient.post('/admin/auth/login', { username, password })

// Status
export const getSystemStatus = () => adminClient.get('/admin/status')

// Data generation
export const generateLastfm = () => adminClient.post('/admin/data/generate-lastfm')
export const generateSynthetic = () => adminClient.post('/admin/data/generate-synthetic')

// Track import
export const importDeezer = (genres?: string[], limitPerGenre?: number) =>
  adminClient.post('/admin/tracks/deezer-import', { genres, limit_per_genre: limitPerGenre })

// Training — trigger
export const runPreprocess = () => adminClient.post('/admin/training/preprocess')
export const runFeatureEngineering = () => adminClient.post('/admin/training/feature-engineering')
export const trainBaseline = () => adminClient.post('/admin/training/train-baseline')
export const trainSasrec = () => adminClient.post('/admin/training/train-sasrec')
export const trainDeepfm = () => adminClient.post('/admin/training/train-deepfm')
export const trainAll = () => adminClient.post('/admin/training/train-all')
export const runEvaluation = () => adminClient.post('/admin/training/evaluate')

// Training — progress & history
export const listTrainingProgress = () => adminClient.get('/admin/training/progress')
export const getTrainingProgress = (taskId: string) => adminClient.get(`/admin/training/progress/${taskId}`)
export const getTrainingHistory = (limit?: number) => adminClient.get('/admin/training/history', { params: { limit } })
export const cancelTraining = (taskId: string) => adminClient.post(`/admin/training/cancel/${taskId}`)

// Evaluation — progress & history
export const listEvalProgress = () => adminClient.get('/admin/training/eval-progress')
export const getEvalHistory = (limit?: number) => adminClient.get('/admin/training/eval-history', { params: { limit } })
export const getEvalReport = (taskId: string) => adminClient.get(`/admin/training/eval-report/${taskId}`)

// Training — SSE stream URL (use native EventSource, not axios)
export const trainingStreamUrl = (taskId: string, token: string) =>
  `/admin/training/progress/${taskId}/stream?token=${encodeURIComponent(token)}`

// Scheduler
export const getSchedules = () => adminClient.get('/admin/scheduler/schedules')
export const createSchedule = (data: any) => adminClient.post('/admin/scheduler/schedules', data)
export const updateSchedule = (id: number, data: any) => adminClient.put(`/admin/scheduler/schedules/${id}`, data)
export const deleteSchedule = (id: number) => adminClient.delete(`/admin/scheduler/schedules/${id}`)
export const toggleSchedule = (id: number) => adminClient.post(`/admin/scheduler/schedules/${id}/toggle`)
export const getThreshold = () => adminClient.get('/admin/scheduler/threshold')
export const updateThreshold = (lastTrainingCount: number) =>
  adminClient.put('/admin/scheduler/threshold', { last_training_count: lastTrainingCount })
export const checkThresholdNow = () => adminClient.post('/admin/scheduler/check-threshold')
