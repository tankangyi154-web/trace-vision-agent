from vision.annotation import annotation_text,class_color,label_positions,overlap

def test_crowded_labels_are_inside_frame_and_do_not_cover_each_other():
    boxes=[{'id':str(i),'label':'person','bbox':[.4+i*.018,.2,.42+i*.018,.4]} for i in range(8)]
    labels=label_positions(boxes,600,480,lambda b:50)
    for i,item in enumerate(labels):
        x,y,right,bottom=item['label_rect']
        assert 0<=x<right<=600 and 0<=y<bottom<=480
        assert all(overlap(item['label_rect'],p['label_rect'])==0 for p in labels[:i])
    assert {item['color'] for item in labels}=={class_color('person')}
    assert class_color('person')!=class_color('car')
    assert annotation_text({'id':'37','label':'car'},lambda label:'汽车')=='汽车 #37'

def test_confidence_subsets_keep_their_original_detection_indices():
    from vision.media_tracking import source_indices
    rows=[[1,1,5,8,.9,0],[9,2,12,6,.15,0],[15,2,20,8,.8,2]]
    assert source_indices(rows,[rows[0],rows[2]])==[0,2]
    assert source_indices(rows,[rows[1]])==[1]
