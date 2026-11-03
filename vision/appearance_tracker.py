# Association loop adapted from Ultralytics 8.3.231 byte_tracker.py (AGPL-3.0).
# https://github.com/ultralytics/ultralytics/blob/v8.3.231/ultralytics/trackers/byte_tracker.py
# Both high- and low-confidence stages call the appearance gate.
from __future__ import annotations
import numpy as np
from ultralytics.trackers.byte_tracker import BYTETracker,STrack,TrackState
from ultralytics.trackers.utils import matching
from vision.media_tracking import source_indices

def _update_with_appearance(self, results, img: np.ndarray | None = None, feats: np.ndarray | None = None) -> np.ndarray:
    """Update the tracker with new detections and return the current list of tracked objects."""
    self.frame_id += 1
    activated_stracks = []
    refind_stracks = []
    lost_stracks = []
    removed_stracks = []

    scores = results.conf
    remain_inds = scores >= self.args.track_high_thresh
    inds_low = scores > self.args.track_low_thresh
    inds_high = scores < self.args.track_high_thresh

    inds_second = inds_low & inds_high
    results_second = results[inds_second]
    results = results[remain_inds]
    feats_keep = feats_second = img
    if feats is not None and len(feats):
        feats_keep = feats[remain_inds]
        feats_second = feats[inds_second]

    detections = self.init_track(results, feats_keep)
    # Add newly detected tracklets to tracked_stracks
    unconfirmed = []
    tracked_stracks = []  # type: list[STrack]
    for track in self.tracked_stracks:
        if not track.is_activated:
            unconfirmed.append(track)
        else:
            tracked_stracks.append(track)
    # Step 2: First association, with high score detection boxes
    strack_pool = self.joint_stracks(tracked_stracks, self.lost_stracks)
    # Predict the current location with KF
    self.multi_predict(strack_pool)
    if hasattr(self, "gmc") and img is not None:
        # use try-except here to bypass errors from gmc module
        try:
            warp = self.gmc.apply(img, results.xyxy)
        except Exception:
            warp = np.eye(2, 3)
        STrack.multi_gmc(strack_pool, warp)
        STrack.multi_gmc(unconfirmed, warp)

    dists = self.get_dists(strack_pool, detections)
    matches, u_track, u_detection = matching.linear_assignment(dists, thresh=self.args.match_thresh)

    for itracked, idet in matches:
        track = strack_pool[itracked]
        det = detections[idet]
        if track.state == TrackState.Tracked:
            track.update(det, self.frame_id)
            activated_stracks.append(track)
        else:
            track.re_activate(det, self.frame_id, new_id=False)
            refind_stracks.append(track)
    # Step 3: Second association, with low score detection boxes association the untrack to the low score detections
    detections_second = self.init_track(results_second, feats_second)
    r_tracked_stracks = [strack_pool[i] for i in u_track if strack_pool[i].state == TrackState.Tracked]
    # TODO
    dists = self.get_dists(r_tracked_stracks, detections_second, low=True)
    matches, u_track, _u_detection_second = matching.linear_assignment(dists, thresh=0.5)
    for itracked, idet in matches:
        track = r_tracked_stracks[itracked]
        det = detections_second[idet]
        if track.state == TrackState.Tracked:
            track.update(det, self.frame_id)
            activated_stracks.append(track)
        else:
            track.re_activate(det, self.frame_id, new_id=False)
            refind_stracks.append(track)

    for it in u_track:
        track = r_tracked_stracks[it]
        if track.state != TrackState.Lost:
            track.mark_lost()
            lost_stracks.append(track)
    # Deal with unconfirmed tracks, usually tracks with only one beginning frame
    detections = [detections[i] for i in u_detection]
    dists = self.get_dists(unconfirmed, detections)
    matches, u_unconfirmed, u_detection = matching.linear_assignment(dists, thresh=0.7)
    for itracked, idet in matches:
        unconfirmed[itracked].update(detections[idet], self.frame_id)
        activated_stracks.append(unconfirmed[itracked])
    for it in u_unconfirmed:
        track = unconfirmed[it]
        track.mark_removed()
        removed_stracks.append(track)
    # Step 4: Init new stracks
    for inew in u_detection:
        track = detections[inew]
        if track.score < self.args.new_track_thresh:
            continue
        track.activate(self.kalman_filter, self.frame_id)
        activated_stracks.append(track)
    # Step 5: Update state
    for track in self.lost_stracks:
        if self.frame_id - track.end_frame > self.max_time_lost:
            track.mark_removed()
            removed_stracks.append(track)

    self.tracked_stracks = [t for t in self.tracked_stracks if t.state == TrackState.Tracked]
    self.tracked_stracks = self.joint_stracks(self.tracked_stracks, activated_stracks)
    self.tracked_stracks = self.joint_stracks(self.tracked_stracks, refind_stracks)
    self.lost_stracks = self.sub_stracks(self.lost_stracks, self.tracked_stracks)
    self.lost_stracks.extend(lost_stracks)
    self.lost_stracks = self.sub_stracks(self.lost_stracks, self.removed_stracks)
    self.tracked_stracks, self.lost_stracks = self.remove_duplicate_stracks(self.tracked_stracks, self.lost_stracks)
    self.removed_stracks.extend(removed_stracks)
    if len(self.removed_stracks) > 1000:
        self.removed_stracks = self.removed_stracks[-999:]  # clip remove stracks to 1000 maximum

    return np.asarray([x.result for x in self.tracked_stracks if x.is_activated], dtype=np.float32)


class AppearanceTrack(STrack):
    def __init__(self,xywh,score,cls,meta,policy):
        super().__init__(xywh,score,cls)
        self.policy=policy;self.profile=None;self.color=None;self.gallery=[];self.clean_updates=0
        # A crowded first sighting often has no clean enrollment frame. Keep
        # its measured appearance only for a strict consecutive-frame match;
        # it must never become a long-gap re-identification profile.
        self.last_feature=meta['feature'];self.last_color=meta['color']
        self.last_occluded=meta['occluded'];self.detection_meta=meta
        self.learn(meta,score)

    def feature_distance(self,other):
        feature=other.detection_meta['feature']
        if feature is None or self.profile is None:return None
        return float(max(0,min(2,min(1-float(p@feature) for p in [self.profile,*self.gallery]))))

    def color_distance(self,other):
        color=other.detection_meta['color']
        if self.color is None or color is None:return None
        return float(np.sqrt(max(0,1-np.sqrt(self.color*color).sum())))

    def learn(self,meta,score):
        self.last_occluded=meta['occluded']
        if meta['occluded'] or score<self.policy['profile_min_confidence'] or meta['feature'] is None:return
        feature=meta['feature']
        if self.profile is None:self.profile=feature.copy();self.color=meta['color'].copy();self.gallery=[feature.copy()]
        else:
            distance=1-float(self.profile@feature)
            if distance>self.policy['profile_max_update_distance']:return
            alpha=self.policy['profile_update_rate']
            self.profile=(1-alpha)*self.profile+alpha*feature
            self.profile/=max(float(np.linalg.norm(self.profile)),1e-8)
            self.color=(1-alpha)*self.color+alpha*meta['color']
            self.color/=max(float(self.color.sum()),1e-8)
            if self.clean_updates%8==0:self.gallery=[self.gallery[0],*self.gallery[-2:],feature.copy()]
        self.clean_updates+=1

    def update(self,new_track,frame_id):
        super().update(new_track,frame_id);self.learn(new_track.detection_meta,new_track.score)
        self.last_feature=new_track.detection_meta['feature'];self.last_color=new_track.detection_meta['color']

    def re_activate(self,new_track,frame_id,new_id=False):
        super().re_activate(new_track,frame_id,new_id);self.learn(new_track.detection_meta,new_track.score)


class AppearanceTracker(BYTETracker):
    def __init__(self,args,encoder,policy):
        super().__init__(args,frame_rate=30);self.encoder=encoder;self.policy=policy
        self.diagnostics={'appearance_veto_pairs':0,'ambiguous_pairs':0,'occluded_samples':0,'provisional_candidate_pairs':0}

    def update(self,results,img=None,feats=None):
        self.source_rows=results.data.tolist()
        meta=self.encoder(img,results.xyxy.tolist())
        self.diagnostics['occluded_samples']+=sum(m['occluded'] for m in meta)
        return _update_with_appearance(self,results,img,np.asarray(meta,dtype=object))

    def init_track(self,results,img=None):
        if not len(results):return []
        indices=source_indices(self.source_rows,results.data.tolist())
        boxes=np.concatenate([results.xywh,np.asarray(indices)[:,None]],axis=1)
        return [AppearanceTrack(box,score,cls,meta,self.policy) for box,score,cls,meta in zip(boxes,results.conf,results.cls,img)]

    def get_dists(self,tracks,detections,low=False):
        geometry=matching.iou_distance(tracks,detections)
        for j,det in enumerate(detections):
            # A detector may produce one combined box instead of two boxes.
            # Two recent predicted people inside it are also an occlusion cue.
            recent=[track for track in tracks if track.state==TrackState.Tracked and self.frame_id-track.frame_id<=2]
            inside=sum(det.xyxy[0] <= (t.xyxy[0]+t.xyxy[2])/2 <= det.xyxy[2] and det.xyxy[1] <= (t.xyxy[1]+t.xyxy[3])/2 <= det.xyxy[3] for t in recent)
            if inside>1 and not det.last_occluded:
                det.last_occluded=True;det.detection_meta['occluded']=True
                det.profile=None;det.color=None;det.gallery=[];det.clean_updates=0
                self.diagnostics['occluded_samples']+=1
        costs=geometry.copy()
        if not low and self.args.fuse_score:costs=matching.fuse_score(costs,detections)
        for i,track in enumerate(tracks):
            for j,det in enumerate(detections):
                a,b=track.xyxy,det.xyxy
                height=max(8,(a[3]-a[1]+b[3]-b[1])/2)
                shift=float(np.linalg.norm((a[:2]+a[2:]-b[:2]-b[2:])/2))/height
                gap=max(1,self.frame_id-track.frame_id)
                if shift>min(2.5,.8+.3*gap):costs[i,j]=1e6;continue
                distance=track.feature_distance(det);color=track.color_distance(det)
                provisional=track.profile is None
                if provisional and track.last_feature is not None and det.detection_meta['feature'] is not None:
                    # Confirm a visible but overlapping person instead of
                    # suppressing it forever. Never bridge a missing sample,
                    # accept a weak detection, or relax the clean-profile gate.
                    if gap!=1 or geometry[i,j]>.5 or det.score<self.args.track_high_thresh:
                        costs[i,j]=1e6;continue
                    distance=max(0,1-float(track.last_feature@det.detection_meta['feature']))
                    if track.last_color is not None and det.detection_meta['color'] is not None:
                        color=float(np.sqrt(max(0,1-np.sqrt(track.last_color*det.detection_meta['color']).sum())))
                    self.diagnostics['provisional_candidate_pairs']+=1
                if distance is None:
                    if det.last_occluded or track.last_occluded or gap>2:costs[i,j]=1e6
                    continue
                bad=distance>(self.policy['provisional_max_feature_distance'] if provisional else self.policy['max_feature_distance'])
                bad|=color is not None and color>self.policy['color_distance_gate'] and distance>self.policy['color_feature_gate']
                if bad:
                    costs[i,j]=1e6;self.diagnostics['appearance_veto_pairs']+=1;continue
                weight=self.policy['appearance_weight']
                costs[i,j]=(1-weight)*costs[i,j]+weight*distance
        # A close tie at an occlusion is insufficient evidence to reuse an ID.
        limit=.5 if low else .8;original=costs.copy();reject=set()
        for i,row in enumerate(original):
            order=np.argsort(row)
            if len(order)>1 and row[order[1]]<limit and row[order[1]]-row[order[0]]<self.policy['ambiguity_margin']:
                if any(detections[j].last_occluded for j in order[:2]):reject.update((i,int(j)) for j in order[:2])
        for j,column in enumerate(original.T):
            order=np.argsort(column)
            if len(order)>1 and column[order[1]]<limit and column[order[1]]-column[order[0]]<self.policy['ambiguity_margin']:
                if detections[j].last_occluded:reject.update((int(i),j) for i in order[:2])
        for pair in reject:costs[pair]=1e6
        self.diagnostics['ambiguous_pairs']+=len(reject)
        return costs

    @staticmethod
    def remove_duplicate_stracks(a,b):
        distances=matching.iou_distance(a,b);remove_a=set();remove_b=set()
        for i,j in zip(*np.where(distances<.15)):
            # Different-looking people must not be deduplicated just because
            # they overlap. Compare only trustworthy, clean stored profiles.
            if a[i].profile is None or b[j].profile is None:continue
            if 1-float(a[i].profile@b[j].profile)>.18:continue
            if a[i].frame_id-a[i].start_frame>b[j].frame_id-b[j].start_frame:remove_b.add(j)
            else:remove_a.add(i)
        return [t for i,t in enumerate(a) if i not in remove_a],[t for j,t in enumerate(b) if j not in remove_b]
