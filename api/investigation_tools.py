"""Investigation tools expose actual local review results to a text-only agent."""
from api.catalog import get_scene
from api.tools import Toolset,TOOL_SCHEMAS,schema
from api.investigation import TRACK_ID,baseline_facts,merge_review,review_facts,validate_claims
from api.domain import analyze

REVIEW_SCHEMAS=[
    schema('review_gap','实际调用本地YOLO11n，在T001疑点缺口7帧上做固定ROI视觉复检，返回真实候选、关联门控、未解帧和前后复算。文本模型本身不看图片。',
           {'track_id':{'type':'string','enum':['T001']}},['track_id']),
    schema('compare_threshold','按新阈值重算原始/已复核观测的结论差异，不重跑视觉模型。',
           {'threshold_seconds':{'type':'number','minimum':.5,'maximum':60}},['threshold_seconds']),
]


class InvestigationTools(Toolset):
    schemas=TOOL_SCHEMAS+REVIEW_SCHEMAS

    def __init__(self,scene,zone_id,dwell_seconds,review_service,review_id=None,on_stage=None):
        if scene['id']!='harbor' or zone_id!='A': raise ValueError('Investigation is bound to harbor zone A')
        super().__init__(scene,zone_id,dwell_seconds)
        self.original=scene; self.threshold=dwell_seconds; self.before=baseline_facts(scene,dwell_seconds)
        self.after=None; self.review_service=review_service; self.review_id=review_id; self.on_stage=on_stage

    def execute(self,name,args):
        if name not in ('review_gap','compare_threshold'):
            result=super().execute(name,args)
            if name in ('calculate_dwell','get_track'):
                result={**result,'baseline_facts':self.before,'review_facts':self.after,
                        'available_review_id':self.review_id,
                        'investigation_note':'缺口12.3—13.1秒；需要主动取证才能更新观测。已有正确连续计算不能替代复核。'}
                self._collect(result)
            return result
        if not isinstance(args,dict): raise ValueError('Invalid arguments')
        if name=='review_gap':
            if args!={'track_id':TRACK_ID}: raise ValueError('Only the fixed T001 gap can be reviewed')
            reused=self.review_id is not None
            job=self.review_service.wait(self.review_id,self.on_stage)
            self.review_id=job['review_id']
            self.scene=merge_review(self.original,job['result'],self.review_id)
            self.after=review_facts(self.scene,job['result'],self.threshold)
            self.analysis=analyze(self.scene,'A',self.threshold)
            evidence_ids=[f"review-{self.review_id}-f{f['frame']:04d}" for f in job['result']['frames']]
            result={'review_id':self.review_id,'strategy':job['result']['strategy_id'],'source_sha256':job['result']['source_sha256'],
                    'execution':'read_version_bound_review' if reused else 'run_or_join_local_review',
                    'review_created_at':job.get('created_at'),'worker_elapsed_ms':job['result'].get('elapsed_ms'),
                    'summary':job['result']['summary'],'baseline_facts':self.before,'review_facts':self.after,
                    'frames':[{'frame':f['frame'],'t':f['t'],'accepted':f['accepted'],'reason':f['reason'],
                               'detections':[{'confidence':round(d['confidence'],4),'iou_before':round(d['iou_before'],4),
                                              'iou_after':round(d['iou_after'],4),'inside_zone':d['inside_zone']} for d in f['detections']]} for f in job['result']['frames']],
                    'evidence_ids':evidence_ids,'limitations':job['result']['limitations']}
        else:
            threshold=args.get('threshold_seconds')
            if set(args)!={'threshold_seconds'} or type(threshold) not in (int,float) or not .5<=threshold<=60:
                raise ValueError('Threshold must be between 0.5 and 60 seconds')
            previous=self.threshold; self.threshold=threshold
            self.before=baseline_facts(self.original,threshold)
            if self.review_id:
                saved=self.review_service.get(self.review_id)
                if saved['status']=='complete':
                    self.scene=merge_review(self.original,saved['result'],self.review_id)
                    self.after=review_facts(self.scene,saved['result'],threshold)
            self.analysis=analyze(self.scene,'A',threshold)
            result={'previous_threshold':previous,'threshold_seconds':threshold,'baseline_facts':self.before,'review_facts':self.after,
                    'review_id':self.review_id if self.after is not None else None,
                    'evidence_ids':[f"review-{self.review_id}-f{f['frame']:04d}" for f in saved['result']['frames']] if self.after is not None else self.before['evidence_ids'],
                    'note':'这是同一证据版本的规则重算，不是重新检测，也不证明物理连续。'}
        self._collect(result)
        return result

    def verify(self,obj):
        result=validate_claims(obj,self.before,self.after)
        if self.after is None and obj.get('basis')=='review': result['status']='rejected'
        return result
