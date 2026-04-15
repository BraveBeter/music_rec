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

// Training
export const runPreprocess = () => adminClient.post('/admin/training/preprocess')
export const trainBaseline = () => adminClient.post('/admin/training/train-baseline')
export const trainSasrec = () => adminClient.post('/admin/training/train-sasrec')
export const trainDeepfm = () => adminClient.post('/admin/training/train-deepfm')
