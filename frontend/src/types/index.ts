/** Shared TypeScript type definitions */

export interface Track {
  track_id: string
  title: string
  artist_name: string | null
  album_name: string | null
  release_year: number | null
  duration_ms: number | null
  play_count: number
  preview_url: string | null
  cover_url: string | null
  score?: number | null
}

export interface User {
  user_id: number
  username: string
  role: string
  age: number | null
  gender: number | null
  country: string | null
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user_id: number
  username: string
  role: string
}

export interface RecommendationResponse {
  strategy_matched: string
  is_fallback: boolean
  items: Track[]
}

export interface SourceRecommendationGroup {
  source: Track
  similar: Track[]
}

export interface GroupedSimilarResponse {
  groups: SourceRecommendationGroup[]
}

export interface TrackListResponse {
  items: Track[]
  total: number
  page: number
  page_size: number
}

export interface InteractionCreate {
  track_id: string
  interaction_type: number
  rating?: number
  play_duration?: number
  client_timestamp?: number
}

// Genre browsing
export interface GenreTracksItem {
  genre: string
  tracks: Track[]
}

export interface GenreTracksResponse {
  genres: GenreTracksItem[]
}
