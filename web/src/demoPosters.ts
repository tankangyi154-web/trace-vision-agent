import harbor from './assets/demo-covers/harbor.jpg'
import crossing from './assets/demo-covers/crossing.jpg'
import night from './assets/demo-covers/night.jpg'

// Vite gives each imported cover a content hash, so changed pixels get a new URL.
const covers: Record<string, string> = { harbor, crossing, night }
export function demoPoster(sceneId: string, fallback = ''): string {
  return covers[sceneId] || fallback
}
