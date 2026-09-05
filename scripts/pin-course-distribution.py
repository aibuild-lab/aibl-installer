#!/usr/bin/env python3
"""Create an external reviewed lock candidate from a clean exact installer revision."""
import argparse, json, subprocess
from pathlib import Path
from pinned_distribution import INSTALLER_FILES, digest, encoded, validate_lock

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--essentials-pin', required=True); parser.add_argument('--workforce-pin', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args(); root = Path(__file__).resolve().parents[1]; output = Path(args.output).expanduser().resolve()
    if output.is_relative_to(root): raise ValueError('Keep the release lock outside the source checkout.')
    def git(*arguments): return subprocess.check_output(['git', *arguments], cwd=root, text=True).strip()
    if git('status', '--porcelain'): raise ValueError('Commit and validate the installer before generating an exact distribution lock.')
    value = validate_lock({'schema_version': 'aibl.course-distribution/v1', 'course_id': 'agent-native-workforce', 'installer': {'repository': 'aibuild-lab/workshop-installer', 'commit': git('rev-parse', 'HEAD'), 'files': {name: digest((root / name).read_bytes()) for name in INSTALLER_FILES}}, 'source_release_pins': {'agent-essentials': json.loads(Path(args.essentials_pin).read_text()), 'agent-native-workforce': json.loads(Path(args.workforce_pin).read_text())}})
    data = encoded(value); output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream: stream.write(data)
    print(json.dumps({'lock': str(output), 'sha256': digest(data), 'installer_commit': value['installer']['commit'], 'launcher_sha256': {name: value['installer']['files'][name] for name in ('start.sh', 'start.ps1')}, 'state': 'candidate; independent review and platform acceptance still required'}, indent=2))

if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error: raise SystemExit(str(error))
