from api.tests.test_domain import scene
from api.tools import Toolset
from api.config import Settings


def test_verified_refusal_remains_machine_readable_after_validation():
    tools = Toolset(scene([]), 'A', 3)
    result = tools.validate_answer({'answer': '未标定的视频不能给出真实航速。', 'evidence_ids': [],
                                    'rule_ids': [], 'insufficient_evidence': True})
    assert result['insufficient_evidence'] is True
    assert result['citations'] == []


def test_settings_repr_excludes_provider_and_storage_secrets():
    representation = repr(Settings(api_key='private-provider-value', redis_token='private-storage-value'))
    assert 'private-provider-value' not in representation
    assert 'private-storage-value' not in representation
