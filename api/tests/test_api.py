from fastapi.testclient import TestClient
from api.index import create_app
from api.config import Settings
from api.store import SQLiteStore


def test_missing_model_fails_closed_but_health_and_evaluation_work(tmp_path):
    client=TestClient(create_app(Settings(),SQLiteStore(tmp_path/'s.db')))
    health=client.get('/api/health').json()
    assert health['live_agent'] is False
    session=client.post('/api/sessions').json()
    result=client.post('/api/chat',json={'request_id':'550e8400-e29b-41d4-a716-446655440000','session_id':session['session_id'],
            'scene_id':'unit','zone_id':'A','dwell_seconds':3,'question':'哪一个驻留最久'})
    assert result.status_code==503
    assert 'DASHSCOPE' not in result.text
    assert client.get('/api/evaluation').status_code==200


def test_production_never_falls_back_to_sqlite():
    settings=Settings(api_key='test-not-real',production=True)
    assert settings.store() is None
    client=TestClient(create_app(settings))
    assert not client.get('/api/health').json()['live_agent']
    assert client.post('/api/sessions').status_code==503


def test_invalid_requests_and_paths_cannot_reach_files(tmp_path):
    client=TestClient(create_app(Settings(),SQLiteStore(tmp_path/'s.db')))
    assert client.get('/api/scenes/not-real').status_code==404
    assert client.post('/api/chat',json={'question':'x'*601}).status_code==422
    assert client.get('/api/scenes/not-real/analysis?dwell_seconds=-1').status_code==422


def test_manual_catalogue_exposes_real_class_aliases_and_example_creation_is_removed(tmp_path):
    client=TestClient(create_app(Settings(),SQLiteStore(tmp_path/'s.db')))
    classes=client.get('/api/object-classes').json()['classes']
    assert len(classes)==80
    car=next(c for c in classes if c['label']=='car')
    assert car['id']==2 and '轿车' in car['aliases']
    assert client.post('/api/uploads/example',json={'classes':[2]}).status_code in (404,405)
