export type Page = 'showcase' | 'assistant' | 'demo' | 'investigation' | 'experience' | 'evaluation' | 'implementation' | 'source'
const pages: readonly string[] = ['showcase', 'assistant', 'demo', 'investigation', 'experience', 'evaluation', 'implementation', 'source']

export function readRoute(hash: string): { page: Page; sceneId: string | null } {
  const [path = '', query = ''] = hash.replace(/^#/, '').split('?', 2)
  const page: Page = pages.includes(path) ? path as Page : 'showcase'
  const requested = new URLSearchParams(query).get('scene')
  const sceneId = ['experience','demo'].includes(page) && requested && /^[a-z0-9][a-z0-9-]{0,63}$/.test(requested) ? requested : null
  return { page, sceneId }
}

export function sceneHref(id: string): string { return `#experience?scene=${encodeURIComponent(id)}` }
export function demoHref(id: string): string { return `#demo?scene=${encodeURIComponent(id)}` }

export function resolveSceneId(scenes: readonly { id: string }[], requested: string | null, current = ''): string | undefined {
  return scenes.find(scene => scene.id === requested)?.id
    || scenes.find(scene => scene.id === current)?.id
    || scenes[0]?.id
}
