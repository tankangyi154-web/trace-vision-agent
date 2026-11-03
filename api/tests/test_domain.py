"""Synthetic unit cases only. These fixtures are never released as scene data."""
import pytest
from api.domain import analyze, point_in_polygon


def scene(points):
    return {
        'id': 'unit', 'duration': 8, 'processing': {'sample_fps': 4},
        'zones': [{'id': 'A', 'name': 'A', 'polygon': [[.3,.3],[.7,.3],[.7,.7],[.3,.7]]}],
        'tracks': [{'id': '1', 'label': 'person', 'samples': [
            {'t': t, 'frame': int(t*4), 'bbox': [x-.02,.48,x+.02,.52], 'confidence': .8}
            for t,x in points]}],
        'evidence': [{'id': 'E1', 'track_id': '1', 't': 1.25, 'image_url': '/media/unit/e.jpg', 'description': 'unit'}],
    }


def test_polygon_boundary_is_inside():
    p = [[0,0],[1,0],[1,1],[0,1]]
    assert point_in_polygon((0,.5), p)
    assert not point_in_polygon((1.01,.5), p)


def test_entry_and_dwell_use_observed_pairs():
    data = analyze(scene([(0,.1),(.25,.4),(.5,.4),(.75,.4),(1,.4),(1.25,.9)]), 'A', .5)
    assert data['summary']['entries'] == 1
    assert data['dwell'][0]['observed_seconds'] == .75
    event = next(e for e in data['events'] if e['type']=='dwell')
    assert event['duration'] == .75
    assert event['evidence_ids'] == ['E1']
    assert not event['censored']


def test_initial_inside_is_not_an_entry_and_is_censored():
    data = analyze(scene([(0,.5),(.25,.5),(.5,.5)]), 'A', .5)
    assert data['summary']['entries'] == 0
    assert data['events'][0]['type'] == 'initial_presence'
    assert data['dwell'][0]['intervals'][0]['censored']


def test_missing_observations_are_not_counted_as_dwell_or_crossing():
    data = analyze(scene([(0,.5),(.25,.5),(3,.5),(3.25,.5),(6,.1),(7,.5)]), 'A', .5)
    assert data['dwell'][0]['observed_seconds'] == .5
    assert data['summary']['entries'] == 0
    assert data['summary']['observation_gaps'] == 3
    assert data['summary']['dwell_alerts'] == 0


def test_threshold_only_affects_alerts_not_ranking():
    s = scene([(0,.5),(.25,.5),(.5,.5)])
    assert analyze(s,'A',.25)['dwell'] == analyze(s,'A',3)['dwell']
    assert analyze(s,'A',3)['summary']['dwell_alerts'] == 0


def test_unknown_zone_and_invalid_threshold_are_rejected():
    with pytest.raises(ValueError): analyze(scene([]), 'secret', 3)
    with pytest.raises(ValueError): analyze(scene([]), 'A', -1)


def test_outside_gaps_and_tracks_do_not_become_region_findings():
    result=analyze(scene([(0,.1),(.25,.1),(3,.1),(3.25,.1)]),'A',1)
    assert result['summary']['tracks']==0 and result['summary']['clip_tracks']==1
    assert result['events']==[] and result['summary']['observation_gaps']==0


def test_an_uncertain_region_boundary_is_retained_without_inventing_an_entry():
    result=analyze(scene([(0,.1),(.25,.1),(3,.5),(3.25,.5)]),'A',1)
    assert result['summary']['observation_gaps']==1
    assert result['summary']['entries']==0
    assert result['summary']['tracks']==1


def test_review_scope_binds_rules_threshold_source_region_and_actual_observations():
    from copy import deepcopy
    original=scene([(0,.5),(.25,.5),(.5,.5)])
    scope=analyze(original,'A',3)['review_scope_id']
    assert scope==analyze(original,'A',3.0)['review_scope_id']
    assert scope!=analyze(original,'A',7)['review_scope_id']
    for change in ('source','region','observation','sampling','model'):
        changed=deepcopy(original)
        if change=='source': changed['processing']['output_sha256']='new-source'
        elif change=='region': changed['zones'][0]['polygon'][0][0]=.2
        elif change=='sampling': changed['processing']['sample_fps']=1
        elif change=='model': changed['processing']['model_sha256']='new-model'
        else: changed['tracks'][0]['samples'][0]['confidence']=.7
        assert scope!=analyze(changed,'A',3)['review_scope_id']


def test_shipped_harbor_b_does_not_include_the_gap_after_its_observed_exit():
    from api.catalog import get_scene
    result=analyze(get_scene('harbor'),'B',7)
    assert result['summary']=={'tracks':1,'clip_tracks':2,'entries':0,'dwell_alerts':1,'observation_gaps':0}
    assert result['dwell'][0]['observed_seconds']==9.4
