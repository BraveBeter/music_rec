/** Tracks, Recommendations & User API calls */
import apiClient from './client'
import type { Track, TrackListResponse, RecommendationResponse, GroupedSimilarResponse, InteractionCreate } from '@/types'

export const usersApi = {
  stats() {
    return apiClient.get<{ play_count: number; favorites_count: number; days_registered: number }>('/users/me/stats')
  },
  favoriteIds() {
    return apiClient.get<{ track_ids: string[] }>('/users/me/favorites/ids')
  },
}

export const tracksApi = {
  list(params?: { query?: string; page?: number; page_size?: number }) {
    return apiClient.get<TrackListResponse>('/tracks', { params })
  },

  getById(trackId: string) {
    return apiClient.get<Track>(`/tracks/${trackId}`)
  },

  popular(limit = 20) {
    return apiClient.get<Track[]>('/tracks/popular', { params: { limit } })
  },
}

export const recommendationsApi = {
  getFeed(params?: { size?: number; scene?: string; current_track_id?: string }) {
    return apiClient.get<RecommendationResponse>('/recommendations/feed', { params })
  },

  getSimilar() {
    return apiClient.get<GroupedSimilarResponse>('/recommendations/similar')
  },
}

export const interactionsApi = {
  log(data: InteractionCreate) {
    return apiClient.post('/interactions', data)
  },

  /** sendBeacon fallback for page unload */
  logBeacon(data: InteractionCreate) {
    const blob = new Blob([JSON.stringify(data)], { type: 'application/json' })
    navigator.sendBeacon('/api/v1/interactions', blob)
  },

  history(limit = 50) {
    return apiClient.get('/interactions/history', { params: { limit } })
  },
}

export const favoritesApi = {
  list() {
    return apiClient.get<Track[]>('/favorites')
  },

  add(trackId: string) {
    return apiClient.post(`/favorites/${trackId}`)
  },

  remove(trackId: string) {
    return apiClient.delete(`/favorites/${trackId}`)
  },
}
