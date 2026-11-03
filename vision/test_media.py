import pytest
from vision.analyze_media import validated_metadata,label_name


def test_real_input_limits_reject_long_videos_and_oversized_images():
    assert validated_metadata(1920,1080,30,600,'video')==20
    assert validated_metadata(1920,1080,30,1800,'video')==60
    assert validated_metadata(1920,1080,30,3600,'video')==120
    assert validated_metadata(4000,5000)==0
    with pytest.raises(ValueError,match='duration'):validated_metadata(1920,1080,30,3606,'video')
    with pytest.raises(ValueError,match='dimensions'):validated_metadata(6000,4000)
    with pytest.raises(ValueError,match='decode'):validated_metadata(960,540,0,100,'video')
    assert label_name('traffic light')=='交通灯'


def test_up_to_three_known_classes_are_validated_before_inference():
    from vision.analyze_media import validate_classes,class_choices
    assert validate_classes([0,2,16])==[0,2,16]
    assert len(class_choices())==80 and class_choices()[2]['name']=='汽车'
    for value in (None,[],[0,1,2,3],[2,2],[-1],[80],[True],['2'],'car'):
        with pytest.raises(ValueError):validate_classes(value)
