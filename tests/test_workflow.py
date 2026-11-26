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


def deploy_steps():
    return {st.split('\n', 1)[0].removeprefix('name: '): st for st in re.split(r'\n      - ', jobs()['deploy'])}


TOKEN_STEPS = ('Get an upload token', 'Create the deployment')


# Requirement: The Cloudflare token reaches two curl calls only ("Reading the deploy job")
def test_secrets_only_in_the_two_curl_steps():
    steps = deploy_steps()
    with_secrets = [name for name, st in steps.items() if 'secrets.' in st]
    assert with_secrets == list(TOKEN_STEPS)
    assert set(re.findall(r'secrets\.([A-Z_]+)', WORKFLOW)) == {'CLOUDFLARE_API_TOKEN', 'CLOUDFLARE_ACCOUNT_ID'}
    deploy = jobs()['deploy']
    order = [deploy.index(x) for x in ('slope_extracts.publish assemble', 'npm ci --ignore-scripts', 'pages.mjs hash',
                                       'name: Get an upload token', 'pages.mjs upload', 'name: Create the deployment')]
    assert order == sorted(order)
    for name in TOKEN_STEPS:
        run = steps[name].split('run: |\n', 1)[1]
        programs = [line.split()[0] for line in run.splitlines() if line.strip()]
        # curl is the only program that talks to Cloudflare, and only api.cloudflare.com is named
        assert programs.count('curl') == 1, name
        assert set(re.findall(r'https://([^/"\s]+)', run)) == {'api.cloudflare.com'}, name
    assert 'wrangler' not in WORKFLOW.split('\njobs:\n', 1)[1]


# Requirement: The Cloudflare token reaches two curl calls only ("Reading a token step")
def test_the_token_reaches_curl_only_through_files():
    builtins = {'umask', 'trap', 'printf', 'unset'}
    for name in TOKEN_STEPS:
        run = deploy_steps()[name].split('run: |\n', 1)[1]
        lines = [line.strip() for line in run.splitlines() if line.strip()]
        joined = ' '.join(lines).replace('\\ ', '')
        uses = [i for i, line in enumerate(lines) if '$CLOUDFLARE_API_TOKEN' in line or '$CLOUDFLARE_ACCOUNT_ID' in line]
        # the secrets are read only by printf, into the header and config files
        assert [lines[i].split()[0] for i in uses] == ['printf', 'printf'], name
        assert '> "$RUNNER_TEMP/cf-auth"' in lines[uses[0]] and '> "$RUNNER_TEMP/cf-curl"' in lines[uses[1]], name
        unset = lines.index('unset CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID')
        # nothing but builtins runs before the unset
        assert all(line.split()[0] in builtins for line in lines[:unset]), name
        assert lines[0] == 'umask 077' and lines[1].startswith("trap 'rm -f \"$RUNNER_TEMP/cf-auth\" \"$RUNNER_TEMP/cf-curl\" \"$RUNNER_TEMP/cf-answer\"' EXIT"), name
        curl = next(line for line in lines if line.startswith('curl '))
        assert '-K "$RUNNER_TEMP/cf-curl"' in joined and '-H @"$RUNNER_TEMP/cf-auth"' in joined, name
        assert '-o "$RUNNER_TEMP/cf-answer"' in joined and curl.startswith('curl -fsS --max-time '), name
        assert ' -v' not in joined and 'set -x' not in joined and '--trace' not in joined, name
        assert 'GITHUB_OUTPUT' not in run and 'GITHUB_ENV' not in run, name


# Requirement: The upload token stays out of the log ("Reading the token step")
def test_the_upload_token_is_masked_before_its_file_is_written():
    step = deploy_steps()['Get an upload token']
    assert 'python3 -I deploy/cf_answer.py jwt "$RUNNER_TEMP/cf-answer" "$RUNNER_TEMP/pages-jwt"' in step
    code = (ROOT / 'deploy/cf_answer.py').read_text()
    jwt = code.split('def jwt(', 1)[1].split('\ndef ', 1)[0]
    assert jwt.index('::add-mask::') < jwt.index('os.open(')
    assert '0o600' in jwt
    upload = deploy_steps()['Upload the new files']
    assert 'secrets.' not in upload and 'env:' not in upload
    assert '--jwt-file "$RUNNER_TEMP/pages-jwt"' in upload


# Requirement: The deploy's one package is installed from its lockfile
def test_the_one_package_comes_from_the_lockfile_without_install_scripts():
    pkg = json.loads((ROOT / 'deploy/package.json').read_text())
    assert pkg['dependencies'] == {'blake3-wasm': '2.1.5'} and 'scripts' not in pkg
    lock = json.loads((ROOT / 'deploy/package-lock.json').read_text())
    packages = {k: v for k, v in lock['packages'].items() if k}
    assert list(packages) == ['node_modules/blake3-wasm']
    assert packages['node_modules/blake3-wasm']['version'] == '2.1.5'
    assert packages['node_modules/blake3-wasm']['integrity'].startswith('sha512-')
    install = deploy_steps()['Install the hashing package']
    assert 'npm ci --ignore-scripts --no-audit --no-fund' in install and 'secrets.' not in install
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


def test_nothing_runs_until_building_is_turned_on():
    # Spec: slope-extract, "Runs wait until the owner turns building on". Build and deploy need plan,
    # so a skipped plan skips them too.
    j = jobs()
    assert "    if: ${{ vars.BUILD_ENABLED == 'true' }}\n" in j['plan']
    assert 'needs: plan' in j['build']
    assert re.search(r'needs: \[plan, build\]', j['deploy'])



def test_the_first_deploy_switch_reaches_plan_and_assemble_through_env():
    # Spec: slope-extract, "A first deploy can replace a placeholder site". A repository variable, not an
    # input (ADR 0007), given to the two steps that read the live manifest and to no other.
    assert WORKFLOW.count('FIRST_DEPLOY: ${{ vars.FIRST_DEPLOY }}') == 2
    plan, deploy = jobs()['plan'], jobs()['deploy']
    assert 'FIRST_DEPLOY: ${{ vars.FIRST_DEPLOY }}' in plan
    assemble = deploy.split('- name: Assemble the site', 1)[1].split('- name:', 1)[0]
    assert 'FIRST_DEPLOY: ${{ vars.FIRST_DEPLOY }}' in assemble
