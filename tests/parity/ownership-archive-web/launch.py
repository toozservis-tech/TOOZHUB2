"""Run the reviewed readonly ownership browser journey only after fresh root GO.

Fictional password is streamed from a mode0600 file to child stdin, never argv.
No fixture setup, API login, product changes, retries, restoration or deployment.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--go-file', required=True, type=Path)
parser.add_argument('--output', required=True, type=Path)
parser.add_argument('--node')
args = parser.parse_args()
go = json.loads(args.go_file.read_text())
assert go['allowed'] is True and go['origin'] == 'http://127.0.0.1:18879'
assert go['readonly_product'] is True and go['allow_safety_network_abort'] is True
oracle_file = Path(go['oracle_file']).resolve()
assert hashlib.sha256(oracle_file.read_bytes()).hexdigest() == go['oracle_sha256']
oracle = json.loads(oracle_file.read_text())
fixture = Path(oracle['fixture_dir']).resolve()
work = fixture.parent / 'web-ownership-ui'
assert args.output.resolve().parent == work and args.output.name.startswith('run')
assert not args.output.exists(), 'Preserve every raw run; select a new output directory'
assert args.go_file.resolve().parent == work
secret = Path(oracle['password_file']).resolve()
assert secret.parent == fixture and secret.stat().st_mode & 0o077 == 0
project = Path(go['project_root']).resolve()
assert not (project / '.env').exists()
node = args.node or go.get('node_binary') or os.environ.get('NODE_BINARY') or shutil.which('node')
assert node
log = work / (args.output.name + '-launcher.log')
assert not log.exists()
command = [node, str(HERE / 'archive-detail.cjs'), '--go-file', str(args.go_file.resolve()),
           '--output', str(args.output.resolve()), '--project-root', str(project), '--oracle', str(oracle_file)]
env = dict(os.environ)
env['PARITY_PYTHON'] = sys.executable
with secret.open('rb') as stdin, log.open('xb') as stdout:
    result = subprocess.run(command, stdin=stdin, stdout=stdout, stderr=subprocess.STDOUT, cwd=work, env=env)
receipt = {'exit_code': result.returncode, 'output': str(args.output.resolve()), 'log': str(log),
           'harness_sha256': hashlib.sha256((HERE / 'archive-detail.cjs').read_bytes()).hexdigest(),
           'secret_delivery': 'mode0600 fixture file streamed to stdin only', 'automatic_retry': False,
           'fixture_or_product_setup': False}
(work / (args.output.name + '-launcher.json')).write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
raise SystemExit(result.returncode)
