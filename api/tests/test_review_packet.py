import base64
import json
import re
import pytest
from evals.build_review_packet import embedded_image,make_packet
from evals.review_media_answers import summarize_review


def test_packet_ignores_prefilled_ai_ratings_and_escapes_embedded_instructions():
    malicious='</script><script>window.ESCAPE=true</script>'
    html=make_packet([{'id':'case','question':malicious,'answer':'answer','ai_ratings':{'fact_accuracy':'pass'}}])
    assert malicious not in html
    payload=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',html,re.S)[1])
    assert payload['cases'][0]['question']==malicious and 'ai_ratings' not in payload['cases'][0]
    assert 'textContent=c.question' in html


def test_non_raster_evidence_and_ai_review_cannot_masquerade_as_human(tmp_path):
    image=tmp_path/'fake.jpg';image.write_text('<svg onload="alert(1)"/>')
    with pytest.raises(ValueError):embedded_image(image)
    with pytest.raises(ValueError):summarize_review({'schema':'trace-ai-evidence-review-v1','cases':[]},{'case'})


def test_real_raster_is_embedded_without_its_private_path(tmp_path):
    path=tmp_path/'private-capability-do-not-export.png'
    path.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6xuoAAAAASUVORK5CYII='))
    html=make_packet([{'id':'case','question':'question','answer':'answer','image_paths':[str(path)]}])
    assert 'private-capability-do-not-export' not in html and 'data:image/png;base64,' in html


def test_review_scores_cannot_be_reused_after_the_material_or_answer_changes():
    row={'id':'case','question':'question','answer':'old','source_sha256':'source',
        'ratings':dict.fromkeys(('question_coverage','fact_accuracy','citation_alignment','unnecessary_refusal','unsupported_inference'),'pass')}
    data={'schema':'trace-independent-review-v1','reviewer':{'id':'declared-reviewer','kind':'human','independent':True},'cases':[row]}
    expected=[{**row,'answer':'new'}]
    with pytest.raises(ValueError,match='不一致'):summarize_review(data,{'case'},expected)
