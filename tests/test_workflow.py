"""The build workflow's security properties, read from its text (no YAML library needed)."""
import json
import pathlib
import re

from slope_extracts import site

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / '.github/workflows/build.yml').read_text()
ALLOWED_ACTIONS = {'actions/checkout', 'actions/upload-artifact', 'actions/download-artifact'}


def top_level_on():
    m = re.search(r'^on:\n((?:  .*\n|\n)+)', WORKFLOW, re.M)
    return re.findall(r'^  ([a-z_]+):', m.group(1), re.M)


def jobs():
    body = WORKFLOW.split('\njobs:\n', 1)[1]
    parts = re.split(r'^  ([a-z]+):\n', body, flags=re.M)
    return dict(zip(parts[1::2], parts[2::2]))


def test_triggers_are_schedule_and_dispatch_only():
    assert top_level_on() == ['schedule', 'workflow_dispatch']
    assert not re.search(r'^\s+inputs:', WORKFLOW, re.M)


def test_every_job_reads_only():
    assert re.search(r'^permissions:\n  contents: read\n', WORKFLOW, re.M)
    assert ': write' not in WORKFLOW
    for name, body in jobs().items():
        assert 'permissions:\n      contents: read\n' in body, name
        assert body.count('contents:') == 1, name


def test_only_deploy_uses_the_environment_and_secrets():
    for name, body in jobs().items():
        if name == 'deploy':
            assert 'environment: pages-production\n' in body
        else:
            assert 'environment:' not in body and 'secrets.' not in body, name


def test_secrets_only_in_the_wrangler_step():
    deploy = jobs()['deploy']
    steps = re.split(r'\n      - ', deploy)
    with_secrets = [st for st in steps if 'secrets.' in st]
    assert len(with_secrets) == 1
    step = with_secrets[0]
    assert step.startswith('name: Deploy to Pages')
    assert 'run: ./node_modules/.bin/wrangler pages deploy ../_site --project-name=slope-extracts --branch=main' in step
    assert set(re.findall(r'secrets\.([A-Z_]+)', WORKFLOW)) == {'CLOUDFLARE_API_TOKEN', 'CLOUDFLARE_ACCOUNT_ID'}
    # it runs after the step that checks the artifacts and the install, which holds no secret
    assert deploy.index('slope_extracts.publish assemble') < deploy.index('npm ci --ignore-scripts') < deploy.index('name: Deploy to Pages')


def test_wrangler_comes_from_the_lockfile_without_install_scripts():
    pkg = json.loads((ROOT / 'deploy/package.json').read_text())
    assert pkg['dependencies'] == {'wrangler': '3.114.17'} and 'scripts' not in pkg
    lock = json.loads((ROOT / 'deploy/package-lock.json').read_text())
    assert lock['packages']['node_modules/wrangler']['version'] == '3.114.17'
    assert all('integrity' in v for k, v in lock['packages'].items() if k)
    assert 'npm ci --ignore-scripts --no-audit --no-fund' in WORKFLOW
    assert 'npm install' not in WORKFLOW and 'npx' not in WORKFLOW


def test_no_wrangler_config_anywhere():
    found = [p for p in ROOT.rglob('wrangler.*') if 'node_modules' not in p.parts]
    assert found == []


def test_deploy_gets_the_plan_through_env():
    deploy = jobs()['deploy']
    assert 'PLAN_JOBS: ${{ needs.plan.outputs.jobs }}' in deploy
    assert 'PLAN_HAD_MANIFEST: ${{ needs.plan.outputs.had_manifest }}' in deploy


def test_actions_are_githubs_own_pinned_by_sha():
    uses = re.findall(r'uses: ([^@\s]+)@(\S+)', WORKFLOW)
    assert uses
    for action, ref in uses:
        assert action in ALLOWED_ACTIONS
        assert re.fullmatch(r'[0-9a-f]{40}', ref)


def test_no_expression_inside_run():
    for block in re.findall(r'run: \|\n((?:          .*\n)+)|run: (.*)\n', WORKFLOW):
        assert '${{' not in ''.join(block)
    assert 'actions/setup-python' not in WORKFLOW
    assert 'pull_request_target' not in WORKFLOW


def test_checkouts_keep_no_credential():
    assert WORKFLOW.count('actions/checkout@') == WORKFLOW.count('persist-credentials: false')


def test_download_artifact_gets_no_token():
    dl = WORKFLOW.split('actions/download-artifact@', 1)[1].split('- name:', 1)[0]
    assert 'github-token' not in dl


def test_packages_are_hash_pinned():
    assert '--require-hashes' in WORKFLOW
    req = (ROOT / 'requirements.txt').read_text()
    names = re.findall(r'^([a-z0-9-]+)==\S+ \\\n    --hash=sha256:[0-9a-f]{64}$', req, re.M)
    assert {'numpy', 'rasterio', 'shapely'} <= set(names)


def test_regions_list_is_valid():
    site.validate_regions(json.loads((ROOT / 'regions.json').read_text()))
