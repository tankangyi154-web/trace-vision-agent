import type { MediaTarget } from './mediaAnnotations'
export type GalleryItem = { id: string; title: string; focus?: string; subtitle: string; poster_url: string; class_names?: string[]; duration?: number }
export type DemoProof = { id: string; t: number; image_url: string; description: string; track_id: string }
export type PreparedDemo = GalleryItem & {
  duration: number; version: string; analysis_mode: 'precomputed'; featured_target_id: string | null
  source: { title: string; author: string; url: string; license: string; license_url: string }
  guides: { id: string; question: string; answer: string; target_id?: string; citations: DemoProof[] }[]
  result: { kind: 'video'; media_url: string; annotation_source_url: string; poster_url: string; duration: number; width: number; height: number; sample_fps: number; targets: MediaTarget[]; counts: { label: string; name: string; count: number; max_simultaneous: number }[]; quality?: { low_resolution: boolean; note: string }; processing?: { tracking_policy?: string }; highlights: DemoProof[] }
}
