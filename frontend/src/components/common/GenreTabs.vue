<script setup lang="ts">
defineProps<{
  genres: string[]
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<template>
  <div class="genre-tabs">
    <button
      v-for="genre in genres"
      :key="genre"
      :class="['genre-tab', { active: genre === modelValue }]"
      @click="emit('update:modelValue', genre)"
    >
      {{ genre }}
    </button>
  </div>
</template>

<style scoped>
.genre-tabs {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
  margin-bottom: var(--spacing-lg);
}

.genre-tab {
  padding: 6px 16px;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.genre-tab:hover {
  border-color: var(--color-accent-primary);
  color: var(--color-accent-primary);
  background: rgba(99, 102, 241, 0.08);
}

.genre-tab.active {
  border-color: var(--color-accent-primary);
  background: rgba(99, 102, 241, 0.15);
  color: var(--color-accent-primary);
}
</style>
