"""Capture native Docker exit codes without PowerShell stderr conversion."""
import subprocess

from .common import DOCKER, ROOT, RUN, write

command = [DOCKER, 'run', '--rm', '--name', 'medresident-ui-fe-check',
           '--mount', f'type=bind,source={ROOT},target=/workspace',
           '-w', '/workspace/apps/frontend', 'node:22-bookworm-slim',
           'sh', '-c', 'npm run typecheck && npm run lint']
result = subprocess.run(command, capture_output=True)
output = (result.stdout + result.stderr).decode(errors='replace')
(RUN / 'frontend-checks.log').write_text(output, encoding='utf-8')
write('frontend-checks.json', {'command': 'npm run typecheck && npm run lint', 'exit_code': result.returncode})
print(output[-3000:].encode('ascii', 'backslashreplace').decode())
print('Frontend checks exit:', result.returncode)
raise SystemExit(result.returncode)
