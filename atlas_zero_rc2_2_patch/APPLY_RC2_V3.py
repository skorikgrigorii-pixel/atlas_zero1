from __future__ import annotations

import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

TARGETS = [
    Path('src/az_enterprise/core/project_config_rc2.py'),
    Path('src/az_enterprise/core/production_state_rc2.py'),
    Path('src/az_enterprise/core/asset_engine_rc2.py'),
    Path('src/az_enterprise/core/assignment_engine_rc2.py'),
    Path('src/az_enterprise/core/timeline_engine_rc2.py'),
    Path('src/az_enterprise/core/render_engine_rc2.py'),
    Path('src/az_enterprise/core/quality_gate_rc2.py'),
    Path('src/az_enterprise/core/director_core_rc2.py'),
    Path('src/az_enterprise/core/rc2_cli.py'),
    Path('tests/test_rc2_foundation.py'),
    Path('docs/RC2_MIGRATION_STAGE_1.md'),
]

COMPILE_TARGETS = [p for p in TARGETS if p.suffix == '.py' and 'tests' not in p.parts]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str], cwd: Path, env: dict[str, str]) -> None:
    print('[RUN]', ' '.join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f'Command failed with exit code {proc.returncode}: {cmd}')


def main() -> int:
    patch_root = Path(__file__).resolve().parent
    project_root = Path.cwd().resolve()

    if not (project_root / 'src/az_enterprise/core').is_dir():
        print('ERROR: Run this installer from the atlas_zero1 project root.', file=sys.stderr)
        print(f'Current directory: {project_root}', file=sys.stderr)
        return 2

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_root = project_root / 'workspace' / 'backups' / f'rc2_stage1_v3_{timestamp}'
    report_dir = project_root / 'workspace' / 'exports' / '_system' / 'rc2_stage1'

    created: list[Path] = []
    backed_up: list[Path] = []
    actions: list[dict[str, str]] = []

    print('=' * 72)
    print('ATLAS ZERO - RC2 STAGE 1 V3')
    print('=' * 72)
    print('Project:', project_root)
    print('Patch:  ', patch_root)
    print('Backup: ', backup_root)

    try:
        backup_root.mkdir(parents=True, exist_ok=True)

        for relative in TARGETS:
            source = patch_root / relative
            destination = project_root / relative

            if not source.is_file():
                raise FileNotFoundError(f'Patch file missing: {source}')

            if source.resolve() == destination.resolve():
                print('[SKIP SAME FILE]', relative)
                actions.append({'path': str(relative), 'action': 'skip_same_file'})
                continue

            if destination.exists():
                if sha256(source) == sha256(destination):
                    print('[ALREADY CURRENT]', relative)
                    actions.append({'path': str(relative), 'action': 'already_current'})
                    continue

                backup_file = backup_root / relative
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, backup_file)
                backed_up.append(destination)
            else:
                created.append(destination)

            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            print('[COPIED]', relative)
            actions.append({'path': str(relative), 'action': 'copied'})

        print('\nCompiling RC2 modules...')
        for relative in COMPILE_TARGETS:
            py_compile.compile(str(project_root / relative), doraise=True)
            print('[COMPILE OK]', relative)

        env = os.environ.copy()
        env['PYTHONPATH'] = str(project_root / 'src')

        print('\nRunning RC2 foundation tests...')
        run([sys.executable, '-m', 'pytest', '-q', 'tests/test_rc2_foundation.py'], project_root, env)

        print('\nChecking RC2 imports...')
        run([
            sys.executable,
            '-c',
            'from az_enterprise.core.director_core_rc2 import DirectorCoreRC2; '
            'from az_enterprise.core.rc2_cli import main; '
            'print("RC2 imports OK")',
        ], project_root, env)

        report_dir.mkdir(parents=True, exist_ok=True)
        report = {
            'version': '2.2',
            'state': 'APPLIED_AND_VERIFIED',
            'applied_at': datetime.now().isoformat(),
            'project_root': str(project_root),
            'patch_root': str(patch_root),
            'backup': str(backup_root),
            'actions': actions,
        }
        (report_dir / 'install_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8'
        )

        print('\n' + '=' * 72)
        print('ATLAS ZERO RC2 STAGE 1 V3 APPLIED AND VERIFIED')
        print('=' * 72)
        print('Backup:', backup_root)
        print('Report:', report_dir / 'install_report.json')
        print('Next safe command:')
        print(f'{sys.executable} -m az_enterprise.core.rc2_cli status franklin')
        return 0

    except Exception as exc:
        print('\nINSTALL FAILED:', exc, file=sys.stderr)
        print('Rolling back changes...', file=sys.stderr)

        for destination in reversed(created):
            try:
                if destination.exists():
                    destination.unlink()
            except Exception as rollback_exc:
                print('Rollback warning:', rollback_exc, file=sys.stderr)

        for destination in reversed(backed_up):
            try:
                relative = destination.relative_to(project_root)
                backup_file = backup_root / relative
                if backup_file.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_file, destination)
            except Exception as rollback_exc:
                print('Rollback warning:', rollback_exc, file=sys.stderr)

        return 1


if __name__ == '__main__':
    raise SystemExit(main())
