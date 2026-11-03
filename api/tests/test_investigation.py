from copy import deepcopy
import pytest
from api.catalog import get_scene
from api.investigation import baseline_facts, merge_review, review_facts, validate_claims


def test_real_case_preserves_existing_baseline_and_threshold_semantics():
    s=get_scene('harbor')
    facts=baseline_facts(s,5)
    assert facts['observed_seconds']==5.7
    assert facts['longest_interval_seconds']==3.7
    assert facts['span_seconds']==6.5
    assert facts['gaps'][0]['duration']==.8
    assert facts['verdict']=='insufficient_evidence'
    assert baseline_facts(s,3)['verdict']=='supported_by_observations'


def review_fixture(frames):
    # Geometry-only unit inputs; not exported or served as real review results.
    return {'frames':[{'frame':i,'t':i/10,'accepted':i in frames,'overlay_image':f'/unit/{i}.jpg','reason':'unit','detections':[]} for i in range(124,131)],
            'observations':[{'frame':i,'t':i/10,'bbox':[.1,.35,.9,.8],'confidence':.8,'source':'review','association':'geometric_candidate'} for i in frames],
            'summary':{'reviewed_frames':7,'accepted_frames':len(frames),'unresolved_frames':7-len(frames)}}


def test_sparse_recheck_does_not_hide_unresolved_evidence_even_if_tolerance_bridges():
    s=get_scene('harbor'); original=deepcopy(s)
    r=review_fixture([127])
    updated=merge_review(s,r,'unit')
    after=review_facts(updated,r,5)
    assert after['longest_interval_seconds']==6.5
    assert after['verdict']=='insufficient_evidence'
    assert 126 in after['unknown_frames']
    assert s==original
    assert review_facts(updated,r,3)['verdict']=='supported_by_observations'


def test_review_rejects_nonactual_or_duplicate_observations():
    r=review_fixture([127]); r['observations'][0]['t']=12.8
    with pytest.raises(ValueError): merge_review(get_scene('harbor'),r,'unit')
    r=review_fixture([127]); r['observations'].append(dict(r['observations'][0]))
    with pytest.raises(ValueError): merge_review(get_scene('harbor'),r,'unit')


def test_claim_verifier_rejects_wrong_metric_and_false_confirmation():
    before=baseline_facts(get_scene('harbor'),5)
    bad={'claims':[{'metric':'longest_interval_seconds','basis':'baseline','value':5.7}],
         'conclusion':'supported_by_observations'}
    result=validate_claims(bad,before,None)
    assert result['status']=='rejected'
    assert result['claims'][0]['expected']==3.7
    good={'claims':[{'metric':'longest_interval_seconds','basis':'baseline','value':3.7}],
          'conclusion':'insufficient_evidence'}
    assert validate_claims(good,before,None)['status']=='insufficient_evidence'


def test_two_basis_comparison_accepts_all_twelve_valid_numeric_claims():
    s=get_scene('harbor'); before=baseline_facts(s,5)
    r=review_fixture([124,125,127,128,129,130])
    after=review_facts(merge_review(s,r,'unit'),r,5)
    keys=['observed_seconds','longest_interval_seconds','span_seconds','gap_seconds','threshold_seconds']
    claims=[{'metric':k,'basis':'baseline','value':before[k]} for k in keys]
    claims += [{'metric':k,'basis':'review','value':after[k]} for k in keys+['accepted_frames','unresolved_frames']]
    assert validate_claims({'claims':claims,'basis':'review','conclusion':'insufficient_evidence'},before,after)['status']=='insufficient_evidence'


def test_threshold_tool_reads_bound_review_and_keeps_analysis_consistent():
    from api.investigation_tools import InvestigationTools
    r=review_fixture([124,125,127,128,129,130])
    class Service:
        def get(self,rid): return {'status':'complete','result':r}
    tools=InvestigationTools(get_scene('harbor'),'A',5,Service(),'saved')
    result=tools.execute('compare_threshold',{'threshold_seconds':3})
    assert result['review_facts']['verdict']=='supported_by_observations'
    assert result['review_id']=='saved'
    assert 'review-saved-f0126' in tools.allowed_evidence
    assert tools.execute('calculate_dwell',{'track_id':'T001'})['threshold_seconds']==3


def test_explicit_text_duration_cannot_reference_a_different_length_interval():
    before=baseline_facts(get_scene('harbor'),5)
    obj={'answer':'最长3.7秒（10.3—12.3秒）。','claims':[{'metric':'longest_interval_seconds','basis':'baseline','value':3.7}],
         'basis':'baseline','conclusion':'insufficient_evidence'}
    assert validate_claims(obj,before,None)['status']=='rejected'
    obj['answer']='最长3.7秒（13.1—16.8秒）。'
    assert validate_claims(obj,before,None)['status']=='insufficient_evidence'
    assert before['longest_interval']['start']==13.1
