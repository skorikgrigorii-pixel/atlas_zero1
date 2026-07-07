from __future__ import annotations
import json, os, shutil, sys, platform
from pathlib import Path
from .database import Database
from .paths import PROJECTS, EXPORTS, DB_PATH
from .integrations import SERVICES
from .events import EventBus

class PreflightCenter:
    """RC1 operational preflight.

    This is intentionally local-first: it does not call paid APIs and does not
    consume credits. It validates whether the workstation, project folders,
    database, export pipeline, environment variables and optional tools are
    ready for a real production run.
    """
    def __init__(self, db: Database, project_id: str = 'franklin'):
        self.db = db
        self.project_id = project_id
        self.bus = EventBus(db, project_id)
        self.export_dir = EXPORTS / project_id
        self.project_dir = PROJECTS / project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> dict:
        checks: list[dict] = []
        def add(key: str, title: str, passed: bool, level: str, detail: str, fix: str = ''):
            checks.append({
                'key': key, 'title': title, 'passed': bool(passed),
                'level': level, 'detail': detail, 'fix': fix
            })

        add('python', 'Python Runtime', sys.version_info >= (3, 10), 'critical',
            f"{platform.python_implementation()} {platform.python_version()}",
            'Install Python 3.10+ and run start_os.bat again.')
        add('sqlite', 'Project Brain SQLite', DB_PATH.exists(), 'critical',
            str(DB_PATH), 'Run the production pipeline once to initialize the database.')
        add('project_dir', 'Franklin project folder', self.project_dir.exists(), 'critical',
            str(self.project_dir), 'Restore workspace/projects/franklin.')
        for sub in ['01_Audio','02_Images','03_Video','04_CapCut','05_Music','06_Export']:
            p = self.project_dir / sub
            add(f'folder_{sub}', f'Project folder {sub}', p.exists(), 'major', str(p), f'Create folder {sub}.')
        add('exports', 'Export folder writable', self._is_writable(self.export_dir), 'critical',
            str(self.export_dir), 'Check folder permissions.')

        ffmpeg = shutil.which('ffmpeg')
        ffprobe = shutil.which('ffprobe')
        add('ffmpeg', 'FFmpeg installed', bool(ffmpeg), 'major', ffmpeg or 'not found',
            'Install FFmpeg and add it to PATH for media probing and future renders.')
        add('ffprobe', 'FFprobe installed', bool(ffprobe), 'major', ffprobe or 'not found',
            'Install FFmpeg package including ffprobe.')

        # Data coverage checks
        try:
            assets = self.db.one('SELECT COUNT(*) c FROM assets')['c']
            shots = self.db.one('SELECT COUNT(*) c FROM shots')['c']
            missing = self.db.one("SELECT COUNT(*) c FROM shots WHERE status='missing'")['c'] if shots else 0
        except Exception:
            assets = shots = missing = 0
        add('assets_indexed', 'Assets indexed', assets > 0, 'critical', f'{assets} assets', 'Run Scan Assets / pipeline.')
        add('shots_built', 'Shots built', shots > 0, 'critical', f'{shots} shots', 'Run Build Film / pipeline.')
        add('coverage_local', 'Franklin local coverage', shots > 0 and missing < shots, 'major',
            f'{shots-missing}/{shots} assigned', 'Add missing assets or run generation queue.')

        # Integration readiness (not required for local Franklin, required for autonomous RC1)
        configured = 0
        integration_checks = []
        for service, (env_key, caps, endpoint) in SERVICES.items():
            value = os.getenv(env_key)
            ok = bool(value)
            if endpoint == 'local_exchange':
                ok = bool(value and Path(value).exists())
            if ok: configured += 1
            integration_checks.append({'service': service, 'env_key': env_key, 'configured': ok, 'capabilities': caps})
        add('integrations_minimum', 'Minimum live integrations configured', configured >= 3, 'major',
            f'{configured}/{len(SERVICES)} configured', 'Configure at least OpenAI, Leonardo, ElevenLabs/YouTube credentials for RC1 live mode.')

        critical_failed = [c for c in checks if not c['passed'] and c['level'] == 'critical']
        major_failed = [c for c in checks if not c['passed'] and c['level'] == 'major']
        passed_count = sum(1 for c in checks if c['passed'])
        score = round(passed_count / max(1, len(checks)) * 100, 2)
        local_ready = not critical_failed
        autonomous_ready = local_ready and len(major_failed) == 0 and configured >= 4
        report = {
            'project_id': self.project_id,
            'score': score,
            'local_ready': local_ready,
            'autonomous_ready': autonomous_ready,
            'critical_failed': len(critical_failed),
            'major_failed': len(major_failed),
            'checks': checks,
            'integrations': integration_checks,
            'next_actions': self._next_actions(checks)
        }
        self._export(report)
        self.bus.emit('PREFLIGHT_COMPLETED', {'score': score, 'local_ready': local_ready, 'autonomous_ready': autonomous_ready})
        return report

    def _is_writable(self, path: Path) -> bool:
        try:
            path.mkdir(parents=True, exist_ok=True)
            test = path / '.write_test'
            test.write_text('ok', encoding='utf-8')
            test.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def _next_actions(self, checks: list[dict]) -> list[str]:
        failed = [c for c in checks if not c['passed']]
        actions = []
        for c in failed[:8]:
            if c.get('fix'):
                actions.append(c['fix'])
            else:
                actions.append(f"Fix: {c['title']}")
        if not actions:
            actions.append('Local production preflight passed. Continue to QC and handoff export.')
        return actions

    def _export(self, report: dict):
        json_path = self.export_dir / 'preflight_report.json'
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        rows = ''.join(
            f"<tr><td>{c['title']}</td><td>{'✅' if c['passed'] else '❌'}</td><td>{c['level']}</td><td>{c['detail']}</td><td>{c.get('fix','')}</td></tr>"
            for c in report['checks']
        )
        actions = ''.join(f"<li>{a}</li>" for a in report['next_actions'])
        html = f"""<!doctype html><html lang='ru'><meta charset='utf-8'><title>ATLAS ZERO Preflight</title>
<style>body{{font-family:Segoe UI,Arial;background:#0f172a;color:#e5e7eb;margin:24px;font-size:13px}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #334155;padding:7px;text-align:left}}.card{{background:#111827;border:1px solid #334155;border-radius:12px;padding:14px;margin:10px 0}}.score{{font-size:34px;font-weight:700}}</style>
<h1>ATLAS ZERO Enterprise RC1 Alpha 0.9 — Preflight</h1>
<div class='card'><div class='score'>{report['score']}%</div><div>Локальная готовность: {'Да' if report['local_ready'] else 'Нет'} · Автономная готовность: {'Да' if report['autonomous_ready'] else 'Нет'}</div></div>
<div class='card'><h2>Следующие действия</h2><ol>{actions}</ol></div>
<div class='card'><h2>Проверки</h2><table><tr><th>Проверка</th><th>Статус</th><th>Уровень</th><th>Деталь</th><th>Исправление</th></tr>{rows}</table></div>
</html>"""
        (self.export_dir / 'preflight_report.html').write_text(html, encoding='utf-8')
