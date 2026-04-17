<script setup lang="ts">
import { ref, onMounted } from 'vue'
import TrackCard from '@/components/common/TrackCard.vue'
import { recommendationsApi, tracksApi } from '@/api/tracks'
import { usePlayerStore } from '@/stores/player'
import { useAuthStore } from '@/stores/auth'
import type { Track, SourceRecommendationGroup } from '@/types'

const auth = useAuthStore()
const player = usePlayerStore()
const recommendations = ref<Track[]>([])
const popularTracks = ref<Track[]>([])
const similarGroups = ref<SourceRecommendationGroup[]>([])
const loading = ref(true)
const strategy = ref('')

const coverFallback = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%231a1a2e" width="100" height="100"/><text x="50" y="55" text-anchor="middle" fill="%236366f1" font-size="40">♪</text></svg>'

onMounted(async () => {
  const promises: Promise<void>[] = []

  // Load recommendations + popular
  promises.push(
    (async () => {
      try {
        const [recRes, popRes] = await Promise.all([
          recommendationsApi.getFeed({ size: 20 }),
          tracksApi.popular(10),
        ])
        recommendations.value = recRes.data.items
        strategy.value = recRes.data.strategy_matched
        popularTracks.value = popRes.data
      } catch (e) {
        console.error('Failed to load recommendations:', e)
      }
    })()
  )

  // Load similar recommendations (only for logged-in users)
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
  <div class="home-page">
    <header class="page-header animate-fade-in">
      <h1 class="page-title">
        <span v-if="auth.isLoggedIn">你好, </span>
        <span v-if="auth.isLoggedIn" class="gradient-text">{{ auth.user?.username }}</span>
        <span v-else class="gradient-text">发现你的音乐</span>
      </h1>
      <p class="page-subtitle">为你精心推荐的个性化音乐</p>
    </header>

    <!-- Recommendations Section -->
    <section class="section animate-slide-up">
      <div class="section-header">
        <h2 class="section-title">🎯 每日推荐</h2>
        <span class="strategy-tag" v-if="strategy">{{ strategy }}</span>
      </div>

      <div v-if="loading" class="track-grid">
        <div v-for="i in 8" :key="i" class="skeleton-card">
          <div class="skeleton" style="width: 100%; aspect-ratio: 1;"></div>
          <div class="skeleton" style="width: 80%; height: 14px; margin-top: 8px;"></div>
          <div class="skeleton" style="width: 60%; height: 12px; margin-top: 4px;"></div>
        </div>
      </div>

      <div v-else-if="recommendations.length" class="track-grid">
        <div
          v-for="(track, index) in recommendations"
          :key="track.track_id"
          class="track-grid-item animate-slide-up"
          :style="{ animationDelay: `${index * 50}ms` }"
        >
          <TrackCard :track="track" :tracks="recommendations" :show-score="true" />
        </div>
      </div>

      <div v-else class="empty-state">
        <p>暂无推荐，请先浏览一些歌曲</p>
        <router-link to="/discover" class="btn-primary">去发现音乐</router-link>
      </div>
    </section>

    <!-- Similar Recommendations Grid -->
    <section
      v-if="similarGroups.length > 0"
      class="section animate-slide-up"
      style="animation-delay: 150ms"
    >
      <div class="section-header">
        <h2 class="section-title">🎧 猜你喜欢</h2>
        <span class="source-hint">基于你常听的歌曲推荐</span>
      </div>

      <div class="similar-grid-wrapper">
        <div class="similar-grid">
          <div v-for="group in similarGroups" :key="group.source.track_id" class="similar-col">
            <!-- Source track header -->
            <div class="similar-col-header" @click="player.play(group.source, [group.source])">
              <img :src="group.source.cover_url || coverFallback" :alt="group.source.title" class="header-cover" />
              <div class="header-info">
                <div class="header-title">{{ group.source.title }}</div>
                <div class="header-artist">{{ group.source.artist_name || 'Unknown' }}</div>
              </div>
            </div>
            <!-- Similar tracks -->
            <div class="similar-col-tracks">
              <div
                v-for="track in group.similar"
                :key="track.track_id"
                class="similar-cell"
                @click="player.play(track, group.similar)"
              >
                <img :src="track.cover_url || coverFallback" :alt="track.title" class="cell-cover" />
                <div class="cell-info">
                  <div class="cell-title">{{ track.title }}</div>
                  <div class="cell-artist">{{ track.artist_name || 'Unknown' }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Popular Section -->
    <section class="section animate-slide-up" style="animation-delay: 200ms">
      <div class="section-header">
        <h2 class="section-title">🔥 热门排行</h2>
      </div>

      <div class="track-list">
        <div
          v-for="(track, index) in popularTracks"
          :key="track.track_id"
          class="track-list-item"
        >
          <span class="rank-number" :class="{ 'top-3': index < 3 }">{{ index + 1 }}</span>
          <TrackCard :track="track" :tracks="popularTracks" />
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home-page {
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: var(--spacing-2xl);
}

.page-title {
  font-size: var(--font-size-3xl);
  font-weight: 700;
  margin-bottom: var(--spacing-sm);
}

.page-subtitle {
  color: var(--color-text-muted);
  font-size: var(--font-size-base);
}

.section {
  margin-bottom: var(--spacing-2xl);
}

.section-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.section-title {
  font-size: var(--font-size-xl);
  font-weight: 600;
}

.strategy-tag {
  font-size: var(--font-size-xs);
  color: var(--color-accent-primary);
  background: rgba(99, 102, 241, 0.15);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-family: monospace;
}

.source-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.track-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--spacing-sm);
}

.skeleton-card {
  padding: var(--spacing-md);
}

.track-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.track-list-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.rank-number {
  width: 28px;
  text-align: center;
  font-size: var(--font-size-base);
  font-weight: 700;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.rank-number.top-3 {
  color: var(--color-accent-primary);
  font-size: var(--font-size-lg);
}

.empty-state {
  text-align: center;
  padding: var(--spacing-2xl);
  color: var(--color-text-muted);
}

.empty-state p {
  margin-bottom: var(--spacing-lg);
  font-size: var(--font-size-lg);
}

/* ── Similar grid ── */
.similar-grid-wrapper {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: thin;
  padding-bottom: 4px;
}

.similar-grid {
  display: flex;
  gap: 1px;
  min-width: max-content;
  background: var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.similar-col {
  min-width: 260px;
  flex: 1;
  background: var(--color-bg-secondary);
  display: flex;
  flex-direction: column;
}

/* Source track header */
.similar-col-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  background: rgba(139, 92, 246, 0.08);
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.similar-col-header:hover {
  background: rgba(139, 92, 246, 0.14);
}

.header-cover {
  width: 40px;
  height: 40px;
  border-radius: 6px;
  object-fit: cover;
  flex-shrink: 0;
}

.header-info {
  flex: 1;
  min-width: 0;
}

.header-title {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}

.header-artist {
  font-size: 0.68rem;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}

/* Similar track cells */
.similar-col-tracks {
  display: flex;
  flex-direction: column;
}

.similar-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  cursor: pointer;
  transition: background var(--transition-fast);
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
  min-height: 50px;
}

.similar-cell:last-child {
  border-bottom: none;
}

.similar-cell:hover {
  background: var(--color-bg-card-hover);
}

.cell-cover {
  width: 36px;
  height: 36px;
  border-radius: 4px;
  object-fit: cover;
  flex-shrink: 0;
}

.cell-info {
  flex: 1;
  min-width: 0;
}

.cell-title {
  font-size: 0.8rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--color-text-primary);
  line-height: 1.3;
}

.cell-artist {
  font-size: 0.68rem;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}

@media (max-width: 768px) {
  .similar-col {
    min-width: 220px;
  }
}
</style>
