/** Tracks, Recommendations & User API calls */
import apiClient from './client'
import type { Track, TrackListResponse, RecommendationResponse, InteractionCreate, GenreTracksResponse, GroupedSimilarResponse, PlaybackHistoryItem } from '@/types'

export const usersApi = {
  stats() {
    return apiClient.get<{ play_count: number; favorites_count: number; days_registered: number }>('/users/me/stats')
  },
  favoriteIds() {
    return apiClient.get<{ track_ids: string[] }>('/users/me/favorites/ids')
  },
  playbackHistory(limit = 500) {
    return apiClient.get<PlaybackHistoryItem[]>('/users/me/history', { params: { limit } })
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

  genreRandom(perGenre = 5) {
    return apiClient.get<GenreTracksResponse>('/tracks/genre-random', { params: { per_genre: perGenre } })
  },

  genreRanking(topK = 10) {
    return apiClient.get<GenreTracksResponse>('/tracks/genre-ranking', { params: { top_k: topK } })
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
