/** Artist API calls */
import apiClient from './client'
import type { TrackListResponse } from '@/types'

export interface ArtistItem {
  artist_name: string
  track_count: number
  cover_url: string | null
}

export interface ArtistListResponse {
  items: ArtistItem[]
  total: number
}

export const artistsApi = {
  search(query: string, limit = 20) {
    return apiClient.get<ArtistListResponse>('/artists/search', {
      params: { q: query, limit },
    })
  },

  tracks(artistName: string, page = 1, pageSize = 20) {
    return apiClient.get<TrackListResponse>(
      `/artists/${encodeURIComponent(artistName)}/tracks`,
      { params: { page, page_size: pageSize } },
    )
  },

  favorites() {
    return apiClient.get<ArtistListResponse>('/artists/favorites')
  },

  favoriteIds() {
    return apiClient.get<{ artist_names: string[] }>('/artists/me/favorites/ids')
  },

  addFavorite(artistName: string) {
    return apiClient.post(`/artists/favorites/${encodeURIComponent(artistName)}`)
  },

  removeFavorite(artistName: string) {
    return apiClient.delete(`/artists/favorites/${encodeURIComponent(artistName)}`)
  },
}
