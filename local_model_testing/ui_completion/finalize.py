"""Record final local runtime and reversible code change inventory; no DB writes."""
import json
import subprocess
import socket
import urllib.request
import xml.etree.ElementTree as ET

from .common import DOCKER, ROOT, RUN, read, sha, write


def main():
    runtime = {}
    for label, url in {
        'frontend': 'http://localhost:3000/',
        'backend_health': 'http://localhost:8000/api/v1/health',
        'backend_database_ready': 'http://localhost:8000/api/v1/ready',
    }.items():
        with urllib.request.urlopen(url, timeout=15) as response:
            runtime[label] = {'url': url, 'http_status': response.status}
    names = subprocess.check_output([DOCKER, 'ps', '--format', '{{.Names}}']).decode().splitlines()
    runtime['temporary_ui_containers_running'] = [name for name in names if name.startswith('medresident-ui-')]
    running = json.loads(subprocess.check_output([DOCKER, 'inspect', 'medresident-tutor-frontend-1']))[0]['Image']
    latest = json.loads(subprocess.check_output([DOCKER, 'image', 'inspect', 'medresident-tutor-frontend:latest']))[0]['Id']
    runtime['frontend_latest_image_applied'] = running == latest
    assert runtime['frontend_latest_image_applied']
    with socket.create_connection(('127.0.0.1', 7687), timeout=5):
        runtime['neo4j_local_port_open'] = True
    write('runtime-final.json', runtime)
    before = read('code-before-hashes.json')
    files = []
    for folder in ('apps/frontend/app', 'apps/frontend/components', 'apps/frontend/lib', 'apps/frontend/e2e', 'apps/frontend/public/fonts', 'apps/backend/app', 'docs/ui'):
        files.extend(path for path in (ROOT / folder).rglob('*') if path.is_file() and '__pycache__' not in path.parts)
    files.extend(path for path in (ROOT / 'apps/frontend').glob('*') if path.is_file() and path.suffix in ('.json', '.ts', '.mjs'))
    files.extend(path for path in (ROOT / 'PRODUCT.md', ROOT / 'DESIGN.md', ROOT / '.impeccable/design.json') if path.exists())
    changes = {}
    for path in dict.fromkeys(files):
        relative = path.relative_to(ROOT).as_posix()
        current = sha(path)
        if before.get(relative) != current:
            changes[relative] = {'before_sha256': before.get(relative), 'after_sha256': current,
                                 'new_file': relative not in before}
    write('changed-code-files.json', changes)
    tests = ET.parse(RUN / 'tests.xml').getroot()
    suites = [tests] if tests.tag == 'testsuite' else list(tests.iter('testsuite'))
    regression = {key: sum(int(suite.attrib.get(key, 0)) for suite in suites)
                  for key in ('tests', 'failures', 'errors', 'skipped')}
    assert regression == dict(tests=56, failures=0, errors=0, skipped=0)
    assert read('frontend-checks.json')['exit_code'] == 0
    assert '3 passed' in (RUN / 'browser-after.log').read_text(encoding='utf-8')
    assert read('data-preservation.json')['main_database_unchanged']
    assert read('data-preservation.json')['bank_and_locked_files_unchanged']
    assert (ROOT / 'docs/ui/finish-verdict.md').read_text(encoding='utf-8').strip().endswith('disposition: ship') or 'disposition: ship' in (ROOT / 'docs/ui/finish-verdict.md').read_text(encoding='utf-8')
    assert not runtime['temporary_ui_containers_running']
    write('handoff-checks.json', {'backend': regression, 'frontend_typecheck_lint_exit': 0,
          'browser_tests_passed': 3, 'before_screenshots': len(list(RUN.glob('before-*.png'))),
          'after_screenshots': len(list(RUN.glob('after-*.png'))),
          'main_data_unchanged': True, 'paid_model_calls': 0, 'runtime': runtime})
    # File names and diff statistics only, never source contents or environment values.
    result = subprocess.run([DOCKER, 'run', '--rm', '--name', 'medresident-ui-git',
        '--mount', f'type=bind,source={ROOT},target=/repo', '-w', '/repo',
        'node:22-bookworm-slim', 'sh', '-c',
        'apt-get update -qq && apt-get install -y -qq git >/dev/null && '
        'git -c safe.directory=/repo status --short && git -c safe.directory=/repo diff --stat'], capture_output=True)
    (RUN / 'git-status-after.txt').write_bytes(result.stdout)
    assert result.returncode == 0, 'Git status collection failed'
    print(json.dumps({'runtime': runtime, 'changed_code_files': len(changes)}))


if __name__ == '__main__':
    main()
