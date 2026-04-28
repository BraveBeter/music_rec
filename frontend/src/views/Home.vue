<script setup lang="ts">
import { ref, onMounted } from 'vue'
import TrackCard from '@/components/common/TrackCard.vue'
import { recommendationsApi } from '@/api/tracks'
import { usePlayerStore } from '@/stores/player'
import { useAuthStore } from '@/stores/auth'
import type { Track, SourceRecommendationGroup } from '@/types'

const auth = useAuthStore()
const player = usePlayerStore()
const recommendations = ref<Track[]>([])
const similarGroups = ref<SourceRecommendationGroup[]>([])
const loading = ref(true)
const strategy = ref('')

const coverFallback = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%23121212" width="100" height="100"/><text x="50" y="56" text-anchor="middle" fill="%231ed760" font-size="38">♪</text></svg>'

onMounted(async () => {
  const promises: Promise<void>[] = []

  promises.push(
    (async () => {
      try {
        const recRes = await recommendationsApi.getFeed({ size: 20 })
        recommendations.value = recRes.data.items
        strategy.value = recRes.data.strategy_matched
      } catch (e) {
        console.error('Failed to load recommendations:', e)
      }
    })()
  )

  if (auth.isLoggedIn) {
    promises.push(
      (async () => {
        try {
          const res = await recommendationsApi.getSimilar()
          similarGroups.value = res.data.groups.filter(g => g.similar.length > 0)
        } catch (e) {
          console.debug('Similar recommendations not available:', e)
        }
      })()
    )
  }

  await Promise.all(promises)
  loading.value = false
})
</script>

<template>
  <div class="home-page page-shell">
    <header class="page-hero animate-fade-in">
      <div class="page-hero-copy">
        <span class="page-kicker">Made For You</span>
        <h1 class="page-title">
          {{ auth.isLoggedIn ? `你好，${auth.user?.username}` : '发现你的音乐' }}
        </h1>
        <p class="page-subtitle">
          用更沉浸的播放器体验浏览推荐、延续播放，并把注意力留给音乐本身。
        </p>
      </div>

      <div class="page-actions">
        <span v-if="strategy" class="pill-tag pill-tag--accent">{{ strategy }}</span>
        <router-link to="/discover" class="btn-primary">去发现</router-link>
      </div>
    </header>

    <section class="section-block animate-slide-up">
      <div class="section-top">
        <div>
          <h2 class="section-heading">每日推荐</h2>
          <p class="section-copy">根据近期行为实时生成，适合直接开始播放。</p>
        </div>
        <span v-if="recommendations.length" class="pill-tag">{{ recommendations.length }} Tracks</span>
      </div>

      <div v-if="loading" class="recommendation-grid">
        <div v-for="i in 6" :key="i" class="recommendation-skeleton content-panel">
          <div class="skeleton skeleton-cover"></div>
          <div class="skeleton skeleton-line"></div>
          <div class="skeleton skeleton-subline"></div>
        </div>
      </div>

      <div v-else-if="recommendations.length" class="recommendation-grid">
        <TrackCard
          v-for="track in recommendations"
          :key="track.track_id"
          :track="track"
          :tracks="recommendations"
          :show-score="true"
        />
      </div>

      <div v-else class="empty-state">
        <p>暂无推荐，请先浏览一些歌曲。</p>
        <router-link to="/discover" class="btn-primary">去发现音乐</router-link>
      </div>
    </section>

    <section
      v-if="similarGroups.length > 0"
      class="section-block animate-slide-up"
      style="animation-delay: 120ms"
    >
      <div class="section-top">
        <div>
          <h2 class="section-heading">猜你喜欢</h2>
          <p class="section-copy">从你常听的歌曲出发，延伸到相邻的听感区域。</p>
        </div>
        <span class="pill-tag">From Your History</span>
      </div>

      <div class="similar-grid">
        <article v-for="group in similarGroups" :key="group.source.track_id" class="similar-column">
          <button class="source-card" type="button" @click="player.play(group.source, [group.source])">
            <img :src="group.source.cover_url || coverFallback" :alt="group.source.title" class="source-cover" />
            <div class="source-copy">
              <span class="source-label">Source Track</span>
              <strong class="source-title">{{ group.source.title }}</strong>
              <router-link
                v-if="group.source.artist_name"
                :to="`/artist/${encodeURIComponent(group.source.artist_name)}`"
                class="source-artist"
                @click.stop
              >
                {{ group.source.artist_name }}
              </router-link>
              <span v-else class="source-artist">Unknown Artist</span>
            </div>
          </button>

          <div class="similar-track-list">
            <button
              v-for="track in group.similar"
              :key="track.track_id"
              class="similar-track"
              type="button"
              @click="player.play(track, group.similar)"
            >
              <img :src="track.cover_url || coverFallback" :alt="track.title" class="similar-track-cover" />
              <div class="similar-track-copy">
                <strong class="similar-track-title">{{ track.title }}</strong>
                <router-link
                  v-if="track.artist_name"
                  :to="`/artist/${encodeURIComponent(track.artist_name)}`"
                  class="similar-track-artist"
                  @click.stop
                >
                  {{ track.artist_name }}
                </router-link>
                <span v-else class="similar-track-artist">Unknown Artist</span>
              </div>
            </button>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.recommendation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 0.875rem;
}

.recommendation-skeleton {
  padding: 1rem;
}

.skeleton-cover {
  width: 100%;
  aspect-ratio: 1.4;
  margin-bottom: 0.875rem;
}

.skeleton-line {
  height: 16px;
  margin-bottom: 0.5rem;
}

.skeleton-subline {
  width: 62%;
  height: 12px;
}

.similar-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1rem;
}

.similar-column {
  padding: 1rem;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(37, 37, 37, 0.98), rgba(24, 24, 24, 0.98));
  box-shadow: var(--shadow-heavy);
}

.source-card {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.875rem;
  text-align: left;
  padding: 0.875rem;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(51, 51, 51, 0.98), rgba(31, 31, 31, 0.98));
}

.source-cover {
  width: 68px;
  height: 68px;
  border-radius: 10px;
  object-fit: cover;
  flex-shrink: 0;
}

.source-copy,
.similar-track-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.source-label {
  color: var(--color-text-secondary);
  font-size: var(--font-size-badge);
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.source-title,
.similar-track-title {
  color: var(--color-text-base);
  font-size: var(--font-size-sm);
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.source-artist,
.similar-track-artist {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.source-artist:hover,
.similar-track-artist:hover {
  color: var(--color-text-base);
}

.similar-track-list {
  margin-top: 0.875rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.similar-track {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  padding: 0.75rem;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  text-align: left;
  transition:
    background-color var(--transition-fast),
    transform var(--transition-fast);
}

.similar-track:hover {
  background: rgba(255, 255, 255, 0.06);
  transform: translateY(-1px);
}

.similar-track-cover {
  width: 46px;
  height: 46px;
  border-radius: var(--radius-lg);
  object-fit: cover;
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .recommendation-grid,
  .similar-grid {
    grid-template-columns: 1fr;
  }
}
</style>
