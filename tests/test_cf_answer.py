"""deploy/cf_answer.py: reads the Cloudflare answers the two curl steps write, printing none of them.
Requirement: The upload token stays out of the log; The Cloudflare token reaches two curl calls only."""
import json
import os
import stat
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'deploy', 'cf_answer.py')
JWT = 'eyJhbGciOiJIUzI1NiJ9.payload-part.sig_part-1'


def run(*args):
    return subprocess.run([sys.executable, '-I', SCRIPT, *args], capture_output=True, text=True)


def answer(tmp_path, doc):
    p = tmp_path / 'cf-answer'
    p.write_text(json.dumps(doc))
    return str(p)


def test_the_jwt_is_masked_then_written_to_a_private_file(tmp_path):
    out = tmp_path / 'pages-jwt'
    r = run('jwt', answer(tmp_path, {'success': True, 'result': {'jwt': JWT}}), str(out))
    assert r.returncode == 0
    lines = r.stdout.splitlines()
    assert lines == [f'::add-mask::{JWT}']
    assert JWT not in r.stderr
    assert out.read_text() == JWT
    assert stat.S_IMODE(os.stat(out).st_mode) == 0o600


@pytest.mark.parametrize('doc', [{'success': False, 'errors': [{'message': 'SECRET-BODY'}]}, {'success': True, 'result': {}},
                                 {'success': True, 'result': {'jwt': 'has space'}}, [], 'x'])
def test_a_bad_answer_fails_without_printing_it(tmp_path, doc):
    out = tmp_path / 'pages-jwt'
    r = run('jwt', answer(tmp_path, doc), str(out))
    assert r.returncode != 0 and not out.exists()
    assert 'SECRET-BODY' not in r.stdout + r.stderr and 'has space' not in r.stdout + r.stderr


def test_an_answer_that_is_not_json_fails_without_printing_it(tmp_path):
    p = tmp_path / 'cf-answer'
    p.write_text('<html>SECRET-BODY</html>')
    r = run('jwt', str(p), str(tmp_path / 'pages-jwt'))
    assert r.returncode != 0 and 'SECRET-BODY' not in r.stdout + r.stderr


def test_the_jwt_file_is_never_overwritten(tmp_path):
    out = tmp_path / 'pages-jwt'
    out.write_text('old')
    r = run('jwt', answer(tmp_path, {'success': True, 'result': {'jwt': JWT}}), str(out))
    assert r.returncode != 0 and out.read_text() == 'old'


def test_the_deployment_answer_prints_only_its_id_and_url(tmp_path):
    r = run('deployment', answer(tmp_path, {'success': True, 'result': {
        'id': 'abc-123', 'url': 'https://abc.slope-extracts.pages.dev', 'other': 'SECRET-BODY'}}))
    assert r.returncode == 0
    assert r.stdout.strip() == 'Deployed abc-123 at https://abc.slope-extracts.pages.dev'
    r = run('deployment', answer(tmp_path, {'success': False}))
    assert r.returncode != 0
