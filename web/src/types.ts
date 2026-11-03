export type Point = [number, number]
export interface Sample { frame: number; t: number; bbox: [number, number, number, number]; confidence: number }
export interface Track { id: string; label: string; samples: Sample[] }
export interface Evidence { id: string; track_id: string; t: number; image_url: string; description: string }
export interface Zone { id: string; name: string; polygon: Point[] }
export interface Scene {
  id: string; title: string; subtitle: string; focus: string
  duration: number; fps: number; width: number; height: number
  original_url: string; annotated_url: string; poster_url: string
  data_kind: 'real_detection' | 'development_fixture'
  zones: Zone[]; default_zone_id: string; default_dwell_seconds: number
  tracks: Track[]; evidence: Evidence[]
  source: { title: string; url: string; author: string; license: string; license_url: string; modifications: string }
  processing: { model: string; tracker: string; confidence: number; iou: number; imgsz: number; sample_fps: number; versions: Record<string, string>; [key: string]: unknown }
  notes: string[]
}
export interface VideoEvent {
  id: string; type: 'enter' | 'exit' | 'dwell' | 'initial_presence' | 'observation_gap'
  track_id: string; label: string; zone_id: string; start: number; end: number
  duration: number; evidence_ids: string[]; description: string; censored: boolean
}
export interface Dwell {
  track_id: string; label: string; observed_seconds: number
  intervals: { start: number; end: number; censored: boolean }[]; evidence_ids: string[]
}
export interface Analysis {
  scene_id: string; zone_id: string; dwell_seconds: number; events: VideoEvent[]
  dwell: Dwell[]; evidence: Evidence[]
  summary: { tracks: number; clip_tracks?: number; entries: number; dwell_alerts: number; observation_gaps: number }
  review_scope_id?: string
  rules_version: string
}
export interface Health {
  status: string; live_agent: boolean; mode: string; reason: string | null
  limits: { session_questions: number; daily_questions: number }; model: string; version: string
  capabilities?: { local_uploads: boolean; image_analysis: boolean; video_analysis: boolean; model_verified: boolean; missing: string[] }
}
export interface Session { session_id: string; remaining: number; live_agent: boolean; reason: string | null }
export interface ChatContext { scene_id: string; zone_id: string; dwell_seconds: number; investigation_id?: string; review_id?: string | null; selected_target_id?: string | null }
export interface ChatRequest extends ChatContext { request_id: string; session_id: string; question: string }
export interface Citation { evidence_id: string; track_id: string; t: number; image_url: string }
export interface ChatResult {
  request_id: string; status: 'queued' | 'running' | 'complete' | 'failed'; stage: string
  answer: string | null; citations: Citation[]; rule_citations: { id: string; text: string }[]
  insufficient_evidence?: boolean
  visual_frame_count?: number
  answer_details?: string
  answer_parts?: { key: string; text: string; details?: string; subject_id: string | null; status: 'confirmed' | 'interpretation' | 'insufficient'; evidence_ids: string[] }[]
  answer_state?: 'answered' | 'partial'
  cache_hit?: boolean
  tool_calls: { name: string; arguments: Record<string, unknown>; summary: string; duration_ms: number; result?: Record<string, unknown> }[]
  public_plan?: string[]
  review_id?: string | null
  verification?: { status: 'passed' | 'rejected' | 'insufficient_evidence'; claims: { metric: string; value: number | null; expected: number | null; passed: boolean; description: string }[] }
  usage: { input_tokens: number; output_tokens: number; model_calls: number; tool_calls: number; usage_complete?: boolean }
  remaining: number; error: { code: string; message: string } | null
}
export interface ChatMessage { id: string; question: string; result?: ChatResult; error?: string }

export interface ReviewFacts {
  observed_seconds: number; longest_interval_seconds: number; span_seconds: number
  intervals: { start: number; end: number; censored: boolean }[]
  gaps: { start: number; end: number; duration: number }[]
  verdict: 'supported_by_observations' | 'insufficient_evidence'; threshold_seconds: number
  description: string; evidence_ids: string[]
  unknown_frames?: number[]; missing_evidence_times?: number[]
}
export interface InvestigationCase {
  id: string; scene_id: 'harbor'; track_id: 'T001'; zone_id: 'A'; title: string; question: string
  source_version: string; scene_version: string; baseline: ReviewFacts
  gap: { start: number; end: number; duration: number; frame_start: number; frame_end: number }
  original_url: string; playback_url?: string; poster_url: string; region_polygon: number[][]; fps: number; duration: number
  model_status: { live_agent: boolean; reason: string | null; model: string }
  review_available: boolean; review_reason: string | null; latest_review_id: string | null; limits: Record<string, unknown>
}
export interface ReviewFrame {
  frame: number; t: number; original_image: string; crop_image: string; overlay_image: string
  roi: number[]; accepted: boolean; selected_index: number | null; reason: string; inference_ms: number
  detections: { bbox: number[]; confidence: number; label: string; iou_before: number; iou_after: number; inside_zone: boolean }[]
}
export interface ReviewWorkerResult {
  case_id: 'harbor-T001-gap'; strategy_id: string; source_sha256: string; scene_sha256: string; model_sha256: string
  config: { imgsz: number; confidence: number; iou: number; classes: number[]; device: string; frames: number[]; roi: number[]; association_iou: number; ambiguity_margin: number; max_frames: number; [key: string]: unknown }
  frames: ReviewFrame[]
  observations: { frame: number; t: number; bbox: number[]; confidence: number; source: 'review'; association: 'geometric_candidate' }[]
  summary: { reviewed_frames: number; accepted_frames: number; detected_frames: number; unresolved_frames: number }
  elapsed_ms: number; limitations: string[]
}
export interface ReviewJob {
  review_id: string; case_id: string; status: 'queued' | 'running' | 'complete' | 'failed'; stage: string
  completed_frames: number; total_frames: number; created_at: string; finished_at: string | null
  result: ReviewWorkerResult | null; baseline: ReviewFacts; after: ReviewFacts | null
  verification: { status: string; checks: { name: string; passed: boolean; detail: string }[]; limitations: string[] } | null
  error: { code: string; message: string } | null
}
