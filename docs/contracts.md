# Contract v1

All timestamps are seconds relative to the served clip (not source video), boxes/points normalized 0..1. IDs are strings. API JSON uses snake_case. No synthetic results in release data.

## On-disk scene: data/scenes/{id}.json

```ts
type Point = [number, number]
type Sample = { frame: number; t: number; bbox: [number,number,number,number]; confidence: number }
type Track = { id: string; label: string; samples: Sample[] }
type Evidence = { id: string; track_id: string; t: number; image_url: string; description: string }
type Zone = { id: string; name: string; polygon: Point[] }
type Scene = {
  id: string; title: string; subtitle: string; focus: string;
  duration: number; fps: number; width: number; height: number;
  original_url: string; annotated_url: string; poster_url: string;
  data_kind: 'real_detection' | 'development_fixture';
  zones: Zone[]; default_zone_id: string; default_dwell_seconds: number;
  tracks: Track[]; evidence: Evidence[];
  source: { title:string; url:string; author:string; license:string; license_url:string; modifications:string };
  processing: { model:string; tracker:string; confidence:number; iou:number; imgsz:number; sample_fps:number; versions:Record<string,string>; [key:string]:unknown };
  notes: string[]
}
```

Media lives in web/public/media/{scene_id}/ (original.mp4, annotated.mp4, poster.jpg, evidence/*.jpg); served URLs begin /media/. Scene id uses lower-case ASCII/hyphens. Small scene files ship server-side; public summary can be generated for offline fallback. Track ID unique within scene. Evidence ID unique within scene. Need a screenshot near each event interval boundary and periodic coverage; API selects nearest real screenshot and records its actual time, never pretends it's exact event frame.

## Derived analysis

```ts
type Event = {
  id:string; type:'enter'|'exit'|'dwell'|'initial_presence'|'observation_gap';
  track_id:string; label:string; zone_id:string; start:number; end:number;
  duration:number; evidence_ids:string[]; description:string; censored:boolean
}
type Dwell = { track_id:string; label:string; observed_seconds:number; intervals:{start:number;end:number;censored:boolean}[]; evidence_ids:string[] }
type Analysis = { scene_id:string; zone_id:string; dwell_seconds:number; review_scope_id:string; events:Event[]; dwell:Dwell[]; evidence:Evidence[]; summary:{tracks:number;clip_tracks:number;entries:number;dwell_alerts:number;observation_gaps:number}; rules_version:string }
```

Anchor is bbox center. Inside/on-edge is inside. Gap tolerance = max(0.5, 2/sample_fps) seconds. Count only consecutive observed in-zone pairs whose gap <= tolerance. Missing samples never provide geometry. `observation_gap` means detector/tracker observation interrupted, not proven physical occlusion. Scene-initial presence is distinct from entry. Dwell threshold affects alerts; all observed durations remain available. End-of-clip intervals censored.

`zones-v2-scoped`: `summary.tracks` counts marks observed in the selected region, while `clip_tracks` counts all marks in the clip; neither is a unique real-world object count. A gap belongs to the selected-region event list only when its before/after observation has at least one in-region endpoint. Both-outside gaps provide no evidence of relevance and are excluded without interpolating movement. `evidence` retains the full clip index for track lookup; the review workspace selects target-bound nearby frames and labels their actual times.

`review_scope_id` is a SHA256 of the source version, actual track observations, selected region, sampling configuration, model/tracker versions, duration, threshold and rule version. Browser human-review records bind this exact scope and episode ID. A review does not overwrite the computed observation or become an Agent-verified fact. See `docs/patrol-workflow.md` for persistence, portable HTML and evaluation limits.

## HTTP API

- GET /api/health → {status, live_agent:boolean, mode, reason:string|null, limits:{session_questions,daily_questions}, model:string, version:string}
- GET /api/scenes → {scenes: Scene[]} (samples omitted in list; use detail for full data)
- GET /api/scenes/{id} → Scene
- GET /api/scenes/{id}/analysis?zone_id=A&dwell_seconds=3 → Analysis
- GET /api/evaluation → evaluation JSON generated from evals/results.json; disclose pending if not measured
- GET /api/scenes/{id}/report?zone_id=A&dwell_seconds=3&format=markdown|json|html → deterministic report download (explicitly labelled computed report, not LLM)
- POST /api/sessions → {session_id:string, remaining:number, live_agent:boolean, reason:string|null}
- POST /api/chat → {request_id:string, session_id:string, scene_id:string, question:string, zone_id:string, dwell_seconds:number}
- GET /api/requests/{id} with X-Session-ID header → ChatResult

ChatResult: {request_id, status:'queued'|'running'|'complete'|'failed', stage:string, answer:string|null, citations:{evidence_id:string,track_id:string,t:number,image_url:string}[], rule_citations:{id:string,text:string}[], tool_calls:{name:string,arguments:object,summary:string,duration_ms:number}[], usage:{input_tokens:number,output_tokens:number,model_calls:number,tool_calls:number}, remaining:number, error:{code:string,message:string}|null}

Chat response may be complete synchronously; request polling only reports real recorded execution stages. Server stores history, never trusts client-provided tool/assistant messages. Frontend retains session ID in localStorage; new request UUID per question, reused for retry. Error shape {detail:{code,message}}. Unknown IDs 404, invalid params 422, budget 429, missing config 503. Model unavailability never converted to a simulated LLM answer.
