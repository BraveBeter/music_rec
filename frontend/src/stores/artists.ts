/** Artist favorites store */
import { defineStore } from 'pinia'
import { artistsApi, type ArtistItem } from '@/api/artists'
import { useAuthStore } from './auth'

export const useArtistFavoritesStore = defineStore('artistFavorites', {
  state: () => ({
    loaded: false,
    favoriteNames: new Set<string>(),
  }),

  actions: {
    async loadFavorites() {
      const auth = useAuthStore()
      if (!auth.isLoggedIn) return
      try {
        const { data } = await artistsApi.favoriteIds()
        this.favoriteNames = new Set(data.artist_names)
        this.loaded = true
      } catch (e) {
        console.error('Failed to load artist favorites:', e)
      }
    },

    async toggleFavorite(artistName: string): Promise<boolean> {
      const auth = useAuthStore()
      if (!auth.isLoggedIn) return false

      const isFav = this.favoriteNames.has(artistName)
      try {
        if (isFav) {
          await artistsApi.removeFavorite(artistName)
          this.favoriteNames.delete(artistName)
        } else {
          await artistsApi.addFavorite(artistName)
          this.favoriteNames.add(artistName)
        }
        return !isFav
      } catch (e) {
        console.error('Failed to toggle artist favorite:', e)
        return isFav
      }
    },

    isFavorited(artistName: string): boolean {
      return this.favoriteNames.has(artistName)
    },
  },
})
