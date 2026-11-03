"""Validate the development case set, or explicitly run a bounded paid live smoke test."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_cases():
    document = json.loads((ROOT / 'evals/agent-cases.json').read_text(encoding='utf-8'))
    cases = document['cases']
    seen = set()
    from api.catalog import get_scene
    for case in cases:
        assert case['id'] not in seen and case['id'], 'Duplicate or empty case ID'
        seen.add(case['id'])
        assert 0 < len(case['question']) <= 600
        scene = get_scene(case['scene_id'])
        assert any(zone['id'] == case['zone_id'] for zone in scene['zones'])
        assert .5 <= case['dwell_seconds'] <= 60
        for pattern in case.get('forbid_patterns', []):
            re.compile(pattern)
    return document, cases


async def run(cases, args):
    from api.agent import AgentError, run_agent
    from api.catalog import get_scene
    from api.config import Settings
    settings = Settings.load()
    if not settings.api_key:
        raise SystemExit('Configure the provider key in ignored .env.local before using --live.')
    recorded_at = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    records = []
    for case in cases:
        started = time.perf_counter()
        record = {'id': case['id'], 'question': case['question'], 'scene_id': case['scene_id'],
                  'source_kind': 'live_provider', 'answer': '', 'tool_names': [], 'citations': [], 'usage': {}}
        try:
            result = await asyncio.wait_for(run_agent(
                get_scene(case['scene_id']), case['zone_id'], case['dwell_seconds'], case['question'],
                [], settings, lambda _: None), timeout=settings.agent_timeout)
            if settings.api_key in json.dumps(result, ensure_ascii=False):
                raise RuntimeError('Secret detected; result was not saved.')
            names = [tool['name'] for tool in result['tool_calls']]
            checks = {
                'model_budget': 0 < result['usage']['model_calls'] <= 3,
                'tool_budget': len(names) <= 5,
                'required_tool': not case.get('required_tool_any') or bool(set(names) & set(case['required_tool_any'])),
                'required_citations': not case.get('requires_citations') or bool(result['citations']),
                'required_refusal': not case.get('must_be_insufficient') or result.get('insufficient_evidence') is True,
                'forbidden_claims_absent': not any(re.search(pattern, result['answer']) for pattern in case.get('forbid_patterns', [])),
            }
            record.update(answer=result['answer'], tool_names=names,
                          citations=[{key: citation[key] for key in ('evidence_id', 'track_id', 't')} for citation in result['citations']],
                          usage=result['usage'], insufficient_evidence=result.get('insufficient_evidence'), checks=checks,
                          status='passed' if all(checks.values()) else 'failed')
        except AgentError as error:
            record.update(status='failed', error_code=error.code, usage=error.partial.get('usage', {}),
                          tool_names=[tool['name'] for tool in error.partial.get('tool_calls', [])],
                          validation_reason=error.partial.get('validation_reason'))
        except asyncio.TimeoutError:
            record.update(status='failed', error_code='agent_timeout')
        record['elapsed_ms'] = round((time.perf_counter() - started) * 1000)
        records.append(record)
        print(f"{case['id']}: {record['status']} | model calls={record['usage'].get('model_calls', 0)} | tools={','.join(record['tool_names'])}", flush=True)
    report = {'recorded_at': recorded_at, 'provider': settings.provider, 'model': settings.model,
              'protocol': 'Development contract checks; no independent semantic accuracy claim.', 'records': records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    passed = all(record['status'] == 'passed' for record in records)
    if args.replay_output and passed:
        args.replay_output.parent.mkdir(parents=True, exist_ok=True)
        args.replay_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Live cases passed: {sum(r["status"] == "passed" for r in records)}/{len(records)}')
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate', action='store_true', help='Validate case definitions without calling a model.')
    parser.add_argument('--live', action='store_true', help='Explicitly allow paid provider calls; no automatic retries.')
    parser.add_argument('--case', action='append', dest='case_ids', help='Select case ID; may be repeated.')
    parser.add_argument('--limit', type=int, default=3, help='Maximum live cases, default 3; each permits 3 model calls.')
    parser.add_argument('--output', type=Path, default=ROOT / 'work/agent-eval/results.json')
    parser.add_argument('--replay-output', type=Path, help='Write a sanitized replay only when every selected case passes.')
    args = parser.parse_args()
    document, cases = load_cases()
    if not args.live:
        print(f'Validated {len(cases)} development cases. Provider calls: 0. Independent review: {document["independent_review"]}.')
        return 0
    if not 1 <= args.limit <= 30:
        parser.error('--limit must be 1..30')
    if args.case_ids:
        unknown = set(args.case_ids) - {case['id'] for case in cases}
        if unknown:
            parser.error('Unknown case IDs: ' + ', '.join(sorted(unknown)))
        cases = [case for case in cases if case['id'] in args.case_ids]
    return asyncio.run(run(cases[:args.limit], args))


if __name__ == '__main__':
    raise SystemExit(main())
