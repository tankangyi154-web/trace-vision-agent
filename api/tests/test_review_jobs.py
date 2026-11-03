from uuid import uuid4
import pytest
from api.review_service import ReviewService,vision_environment


class NoWorker(ReviewService):
    @property
    def reason(self): return None
    def _run(self,rid): pass
    def get(self,rid,threshold=5): return self._read(self._resolve(rid))


@pytest.mark.parametrize('terminal',['complete','failed'])
def test_joined_request_stays_bound_after_lost_response_and_restart(tmp_path,terminal):
    s=NoWorker(directory=tmp_path)
    b=str(uuid4()); a=str(uuid4())
    assert s.start(b)['review_id']==b
    assert s.start(a)['review_id']==b
    s._update(b,{'status':terminal})
    reloaded=NoWorker(directory=tmp_path)
    assert reloaded.start(a)['review_id']==b
    assert not (tmp_path/a/'job.json').exists()


def test_vision_subprocess_environment_never_inherits_application_secrets(monkeypatch):
    for key in ('DEEPSEEK_API_KEY','DASHSCOPE_API_KEY','UPSTASH_REDIS_REST_TOKEN','UNKNOWN_CUSTOM_SECRET'):
        monkeypatch.setenv(key,'unit-private-not-real')
    env=vision_environment()
    assert not any('unit-private' in value for value in env.values())
    assert env['PYTHONIOENCODING']=='utf-8'
    assert env['YOLO_OFFLINE']=='true'
