# Local evidence-review contract v1

Case id: harbor-T001-gap. Bound to Scene original mp4 SHA256 48acaf2024ca892a133c31b238742f8f76d6cef76188e33dc01904e15a600376. Model SHA in vision/model.lock.json, baseline scene JSON SHA computed at runtime. All times clip-relative. Review only frames124..130 (12.4..13.0 at10fps), never synthetic samples. No original data mutation.

## Vision worker

`work/vision-env/Scripts/python.exe vision/review_gap.py --output <absolute job directory>`
stdout JSONL stages `{stage:string,completed_frames:int,total_frames:7}` only small values; final writes result.json atomically, exits0. Errors stderr/no keys. Job directory chosen by API under work/reviews/{uuid}. Worker does not choose model/source/ROI from user paths or URLs. All source paths internal, no key/API access. API serves artifacts under /review-media/{uuid}/.

```ts
type ReviewFrame = {
  frame:number;t:number;original_image:string;crop_image:string;overlay_image:string;
  roi:[number,number,number,number]; // normalized full image
  detections:{bbox:[number,number,number,number];confidence:number;label:string;iou_before:number;iou_after:number;inside_zone:boolean}[];
  accepted:boolean; selected_index:number|null; reason:string; inference_ms:number
}
type WorkerResult = {
  case_id:'harbor-T001-gap';strategy_id:'roi-recheck-v1';
  source_sha256:string;scene_sha256:string;model_sha256:string;
  config:{imgsz:960;confidence:.25;iou:.5;classes:[8];device:'cpu';frames:number[];roi:number[];association_iou:.2;ambiguity_margin:.1;max_frames:7;[key:string]:unknown};
  frames:ReviewFrame[];
  observations:{frame:number;t:number;bbox:number[];confidence:number;source:'review';association:'geometric_candidate'}[];
  summary:{reviewed_frames:number;accepted_frames:number;detected_frames:number;unresolved_frames:number};
  elapsed_ms:number;limitations:string[]
}
```

Worker artifact paths are relative filenames (original-0124.jpg/crop-0124.jpg/overlay-0124.jpg). API translates to safe served URLs; never returns absolute source paths. Every frame gets original/crop/overlay even with no detections. ROI = union of baseline boxes at frame123 and131 + .05 on each side, clip0..1. Fixed strategy conf.25,iou.5,imgsz960,boat8,CPU4threads. Map cropped coordinates back to original; no lower-threshold rescue. Acceptance requires IoU>=.2 with EACH side box, candidate center insideA. Rank by min IoU, if top two scores within.1 reject as ambiguous. Accepted boxes remain geometric hypotheses, not identity proof.

## Coverage/metrics (API-generated)

```ts
type Facts = {
  observed_seconds:number;longest_interval_seconds:number;span_seconds:number;
  intervals:{start:number;end:number;censored:boolean;duration:number}[];
  longest_interval:{start:number;end:number;censored:boolean;duration:number}|null;
  gaps:{start:number;end:number;duration:number}[];
  verdict:'supported_by_observations'|'insufficient_evidence';
  threshold_seconds:number;description:string;
  evidence_ids:string[]; // baseline evidence OR accepted review frame IDs
}
type Case = {
 id:string;scene_id:'harbor';track_id:'T001';zone_id:'A';title:string;question:string;
 source_version:string;scene_version:string;baseline:Facts;gap:{start:12.3;end:13.1;duration:.8;frame_start:124;frame_end:130};
 original_url:string;playback_url?:string;poster_url:string;region_polygon:number[][];fps:10;duration:16.9;
 model_status:{live_agent:boolean;reason:string|null;model:string};
 review_available:boolean;review_reason:string|null;latest_review_id:string|null;limits:object
}
type ReviewJob = {
 review_id:string;case_id:string;status:'queued'|'running'|'complete'|'failed';stage:string;
 completed_frames:number;total_frames:7;created_at:string;finished_at:string|null;
 result:WorkerResult|null;baseline:Facts;after:Facts|null;
 verification:{status:string;checks:{name:string;passed:boolean;detail:string}[];limitations:string[]}|null;
 error:{code:string;message:string}|null
}
```

Facts baseline derived from existing analyze, not naive bad algorithm. after merges ONLY accepted actual detections in separate scene copy, uses SAME existing algorithm. Separately show reviewed/accepted/unresolved frame counts and assumptions. Never let recomputed interval length alone hide remaining unresolved frames. Physical continuity/identity remains unproven; verdict describes observation support. If missing review frames or ambiguous association affect gap, say insufficient even if tolerance could bridge sparse points.

## HTTP (local only for new vision work)

- GET /api/investigation?threshold=5 → Case
- POST /api/investigation/reviews `{request_id:UUID}` → ReviewJob; local background job, idempotent ID, at most1active worker. Repeated new job while active returns existing job, with a durable request→job alias preserved after terminal state/restart. Actual stage only, no fake percentages.
- GET /api/investigation/reviews/{id}?threshold=5 → ReviewJob
- GET /api/investigation/report?review_id={uuid}&threshold=5 → standalone JSON audit download
- POST /api/chat existing fields + optional investigation_id:'harbor-T001-gap', review_id:UUID|null. Same quota/session flow. Review context part of history/idempotency scope.

ChatResult adds `public_plan:string[]`, `verification:{claims:{metric:string;value:number|null;expected:number|null;passed:boolean;description:string}[];status:'passed'|'rejected'|'insufficient_evidence'}`. These are explicit output fields and real checks, not chain of thought. tool_calls adds optional `result:object` for compact real returned evidence.
New tool review_gap {track_id:'T001'} executes/reads actual local review; model may choose it. calculate_dwell/get_track include baseline facts/gap; compare_threshold {threshold_seconds:number} returns program comparison of baseline and actual review at new threshold (same bounded tool budget). Tools can call3models/5tools total. Final structured model claims recomputed by verifier; invalid numeric/unsupported continuous claims rejected, no silent correction into fabricated certainty. Text model never receives/understands frames; only detections/geometry/time/uncertainty and human-viewable image links.

UI entry #investigation (default new landing), old #experience retained. Disabled real model clearly shown, but active button ‘仅运行本地视觉复核’ executes real algorithm, and threshold3/5 actually recomputes. Key-only local configuration, no Redis/cloud requirement. Worker and validator receive an explicit minimal OS environment; application credentials are not inherited. Playback rendition is optional and never replaces the original evidence source.
