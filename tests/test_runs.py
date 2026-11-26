"""back-to-back-runs: the schedule, and live reads past the CDN's cache."""
import http.server
import inspect
import re
import threading

from slope_extracts import publish, site
from test_workflow import WORKFLOW


# Requirement: Runs follow one another ("Reading the schedule")
def test_the_build_workflow_runs_every_15_minutes_one_run_at_a_time():
    crons = re.findall(r'^\s+- cron: "([^"]+)"', WORKFLOW, re.M)
    assert len(crons) == 1
    minute, *rest = crons[0].split()
    assert rest == ['*', '*', '*', '*']
    minutes = list(range(0, 60, 15)) if minute == '*/15' else sorted(int(m) for m in minute.split(','))
    assert len(minutes) == 4 and all(b - a == 15 for a, b in zip(minutes, minutes[1:]))
    assert re.search(r'^concurrency:\n  group: slope-extract\n  cancel-in-progress: false\n', WORKFLOW, re.M)
    assert WORKFLOW.count('concurrency:') == 1


class Recorder(http.server.BaseHTTPRequestHandler):
    seen = []

    def do_GET(self):
        Recorder.seen.append(self.path)
        body = b'{}'
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


# Requirement: The pipeline reads the live site past its edge cache ("A file the CDN still caches")
def test_every_live_read_carries_a_query_string_of_its_own():
    server = http.server.HTTPServer(('127.0.0.1', 0), Recorder)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f'http://127.0.0.1:{server.server_address[1]}'
        Recorder.seen.clear()
        for p in ('manifest.json', 'manifest.json', 'tiles/19_-54/index.json'):
            assert publish.http_get(f'{base}/{p}', 100) == (200, b'{}')
    finally:
        server.shutdown()
    paths = [s.split('?', 1) for s in Recorder.seen]
    assert [p[0] for p in paths] == ['/manifest.json', '/manifest.json', '/tiles/19_-54/index.json']
    queries = [p[1] if len(p) == 2 else '' for p in paths]
    assert all(len(q) >= 8 for q in queries) and len(set(queries)) == 3


def test_the_plan_and_deploy_read_the_live_site_through_http_get():
    for fn in (publish.fetch_live, publish.fetch_hashes, publish.read_back, publish.assemble, publish.verify_live):
        assert inspect.signature(fn).parameters['get'].default is publish.http_get, fn.__name__
    assert 'publish.fetch_live(publish.SITE_URL, publish.http_get' in inspect.getsource(site.main_plan)
