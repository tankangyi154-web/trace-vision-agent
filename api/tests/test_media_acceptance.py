from copy import deepcopy
import pytest
from evals.review_media_answers import review_template,summarize_review,summarize_height,DIMENSIONS


def template():
    return review_template({'cases':[{'id':'case','question':'问法','answer':'旧回答','source_sha256':'source'}],
        'rechecks':[{'id':'case','answer':'修复后回答'}]})


def test_review_uses_latest_recheck_and_does_not_invent_an_empty_set_score():
    data=template();assert data['cases'][0]['answer']=='修复后回答'
    result=summarize_review(data,{'case'})
    assert result['status']=='pending' and result['reviewed_cases']==0
    assert all(metric['pass_rate'] is None for metric in result['metrics'].values())


def test_model_self_ratings_are_not_counted_as_independent_human_review():
    data=template();data['reviewer']={'id':'automated','kind':'model','independent':True}
    data['cases'][0]['ratings']=dict.fromkeys(DIMENSIONS,'pass')
    assert summarize_review(data,{'case'})['reviewed_cases']==0


def test_review_can_record_failures_without_turning_a_completed_review_into_a_pass():
    data=template();data['reviewer']={'id':'declared-reviewer','kind':'human','independent':True}
    data['cases'][0]['ratings']=dict.fromkeys(DIMENSIONS,'pass')
    data['cases'][0]['ratings']['fact_accuracy']='fail'
    result=summarize_review(data,{'case'})
    assert result['status']=='complete' and result['metrics']['fact_accuracy']['pass_rate']==0
    data['cases'].append(deepcopy(data['cases'][0]))
    with pytest.raises(ValueError):summarize_review(data,{'case'})


def test_height_without_actual_measurements_or_with_only_abstentions_has_no_error_score():
    assert summarize_height({'schema':'trace-measured-height-v1','cases':[]})['midpoint_mae_cm'] is None
    row={'measurement_verified':True,'measurement_source':'Synthetic test fixture only; not real measurement',
         'measured_height_cm':175,'measured_reference_cm':90,'predicted_range_cm':None}
    result=summarize_height({'schema':'trace-measured-height-v1','cases':[row]})
    assert result['verified_measurements']==1 and result['numeric_estimates']==0 and result['midpoint_mae_cm'] is None


def test_height_statistics_distinguish_midpoint_error_from_interval_coverage():
    row={'measurement_verified':True,'measurement_source':'Synthetic unit-test fixture, not real measurement',
         'measured_height_cm':180,'measured_reference_cm':90,'predicted_range_cm':[160,180]}
    result=summarize_height({'schema':'trace-measured-height-v1','cases':[row]})
    assert result['midpoint_mae_cm']==10 and result['interval_coverage']==1
    row['measured_reference_cm']=float('nan')
    with pytest.raises(ValueError):summarize_height({'schema':'trace-measured-height-v1','cases':[row]})


def test_calibrated_point_errors_are_not_reported_as_prediction_interval_coverage():
    row={'measurement_verified':True,'measurement_source':'Synthetic unit-test fixture, not a real measurement',
         'measured_height_cm':180,'measured_reference_cm':174.5,'predicted_height_cm':175}
    result=summarize_height({'schema':'trace-measured-height-v1','cases':[row]})
    assert result['point_estimates']==1 and result['mae_cm']==5
    assert result['midpoint_mae_cm'] is None and result['interval_coverage'] is None
