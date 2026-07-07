from __future__ import annotations
import json, csv, os
from pathlib import Path
from .paths import EXPORTS

class TestCenter:
    """RC1 Alpha 1.8 testing center.

    Создает не демонстрационный отчет, а пакет приемочного тестирования для
    Franklin: что проверять, какие артефакты должны быть на месте, какие
    критерии означают рабочее состояние локального production workflow.
    Live API проверяются безопасно: без платных генераций и без раскрытия ключей.
    """
    def __init__(self, db, project_id='franklin'):
        self.db = db
        self.project_id = project_id
        self.export_dir = EXPORTS / project_id
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def _exists(self, rel: str) -> dict:
        p = self.export_dir / rel
        return {"artifact": rel, "exists": p.exists(), "size": p.stat().st_size if p.exists() else 0}

    def run(self) -> dict:
        # Ensure tables without touching global schema.
        self.db.execute("""CREATE TABLE IF NOT EXISTS rc1_test_cases(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            suite TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            expected TEXT,
            actual TEXT,
            severity TEXT DEFAULT 'normal',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        self.db.execute("DELETE FROM rc1_test_cases WHERE project_id=?", (self.project_id,))

        shots = self.db.one("SELECT COUNT(*) c FROM shots WHERE project_id=?", (self.project_id,))["c"]
        assigned = self.db.one("SELECT COUNT(*) c FROM shots WHERE project_id=? AND status='assigned'", (self.project_id,))["c"]
        assets = self.db.one("SELECT COUNT(*) c FROM assets WHERE project_id=?", (self.project_id,))["c"]
        missing = self.db.one("SELECT COUNT(*) c FROM shots WHERE project_id=? AND status='missing'", (self.project_id,))["c"]
        qc = self.db.one("SELECT readiness FROM quality_reports WHERE project_id=? ORDER BY id DESC LIMIT 1", (self.project_id,))
        readiness = float(qc["readiness"]) if qc else 0.0
        coverage = round((assigned / shots * 100), 2) if shots else 0

        required = [
            "монтажный_лист.csv", "capcut_пакет.csv", "capcut_guide.md",
            "timeline_viewer_2.html", "cv_review_board.html", "live_api_test_suite.html",
            "working_state_audit.html", "FINAL_ASSEMBLY_PACK/index.html",
            "command_center.html", "franklin_acceptance.html"
        ]
        artifacts = [self._exists(x) for x in required]

        cases = []
        def add(suite, title, ok, expected, actual, severity='normal'):
            status = 'pass' if ok else 'fail'
            cases.append({"suite": suite, "title": title, "status": status,
                          "expected": expected, "actual": actual, "severity": severity})
            self.db.execute("INSERT INTO rc1_test_cases(project_id,suite,title,status,expected,actual,severity) VALUES(?,?,?,?,?,?,?)",
                            (self.project_id, suite, title, status, expected, str(actual), severity))

        add('Franklin local workflow', 'Шоты построены', shots >= 150, '>=150', shots, 'critical')
        add('Franklin local workflow', 'Материалы обнаружены', assets >= 8, '>=8', assets, 'critical')
        add('Franklin local workflow', 'Покрытие материалами', coverage >= 80, '>=80%', f'{coverage}%', 'critical')
        add('Quality Control', 'QC readiness', readiness >= 80, '>=80%', f'{readiness}%', 'critical')
        add('Missing assets', 'Дефицит не блокирует ручной CapCut handoff', missing <= 70, '<=70', missing, 'normal')
        for a in artifacts:
            add('Exports', f"Артефакт {a['artifact']}", a['exists'] and a['size'] > 0, 'exists and >0 bytes', f"exists={a['exists']}, size={a['size']}", 'critical')

        # Safe API readiness: check only env variables presence, never print values.
        api_env = {
            'OpenAI': 'OPENAI_API_KEY', 'Leonardo': 'LEONARDO_API_KEY',
            'ElevenLabs': 'ELEVENLABS_API_KEY', 'YouTube': 'YOUTUBE_CLIENT_ID'
        }
        api_readiness = []
        for service, key in api_env.items():
            present = bool(os.environ.get(key))
            api_readiness.append({'service': service, 'env_key': key, 'present': present})
            add('Live API preflight', f'{service} credential present', present, 'ENV key present', 'present' if present else 'missing', 'live_api')

        passed = sum(1 for c in cases if c['status'] == 'pass')
        failed = len(cases) - passed
        critical_failed = [c for c in cases if c['status'] == 'fail' and c['severity'] == 'critical']
        local_ready = len(critical_failed) == 0
        live_ready = all(x['present'] for x in api_readiness)
        full_ready = local_ready and live_ready and readiness >= 90 and missing <= 30

        report = {
            'version': 'RC1 Alpha 1.8',
            'project_id': self.project_id,
            'cases_total': len(cases),
            'passed': passed,
            'failed': failed,
            'local_ready_for_testing': local_ready,
            'full_autonomous_ready': full_ready,
            'coverage_pct': coverage,
            'qc_readiness': readiness,
            'missing': missing,
            'api_readiness': api_readiness,
            'critical_failed': critical_failed,
            'cases': cases,
            'next_test_actions': [
                'Открыть command_center.html и проверить сводку проекта.',
                'Открыть timeline_viewer_2.html и проверить первые 20 шотов.',
                'Открыть capcut_guide.md и собрать первые 60 секунд в CapCut.',
                'Проверить missing_prioritized.csv и выбрать 10 кадров для генерации.',
                'Если доступны ключи API — заполнить .env и повторить live preflight.'
            ]
        }
        self._export(report)
        return report

    def _export(self, report: dict):
        (self.export_dir / 'rc1_test_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        with (self.export_dir / 'rc1_test_cases.csv').open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['Suite','Test','Status','Expected','Actual','Severity'])
            for c in report['cases']:
                writer.writerow([c['suite'], c['title'], c['status'], c['expected'], c['actual'], c['severity']])
        rows = ''.join(
            f"<tr class='{c['status']}'><td>{c['suite']}</td><td>{c['title']}</td><td>{c['status']}</td><td>{c['expected']}</td><td>{c['actual']}</td><td>{c['severity']}</td></tr>"
            for c in report['cases']
        )
        actions = ''.join(f"<li>{a}</li>" for a in report['next_test_actions'])
        html = f"""<!doctype html><html lang='ru'><meta charset='utf-8'><title>RC1 Test Center</title>
<style>body{{font-family:Segoe UI,Arial;background:#0f172a;color:#e5e7eb;margin:24px;font-size:13px}}.card{{background:#111827;border:1px solid #334155;border-radius:12px;padding:14px;margin:12px 0}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #334155;padding:7px;text-align:left}}.pass td{{color:#bbf7d0}}.fail td{{color:#fecaca}}.num{{font-size:26px;font-weight:700}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}</style>
<h1>ATLAS ZERO Enterprise RC1 Alpha 1.8 — центр тестирования</h1>
<div class='grid'><div class='card'><div>Тестов</div><div class='num'>{report['cases_total']}</div></div><div class='card'><div>Пройдено</div><div class='num'>{report['passed']}</div></div><div class='card'><div>Провалено</div><div class='num'>{report['failed']}</div></div><div class='card'><div>Локально к тесту</div><div class='num'>{'ДА' if report['local_ready_for_testing'] else 'НЕТ'}</div></div></div>
<div class='card'><b>Полная автономная готовность:</b> {'ДА' if report['full_autonomous_ready'] else 'НЕТ'}<br><b>QC:</b> {report['qc_readiness']}% · <b>Покрытие:</b> {report['coverage_pct']}% · <b>Недостающих:</b> {report['missing']}</div>
<div class='card'><h2>Что тестировать сейчас</h2><ol>{actions}</ol></div>
<div class='card'><h2>Тест-кейсы</h2><table><tr><th>Suite</th><th>Test</th><th>Status</th><th>Expected</th><th>Actual</th><th>Severity</th></tr>{rows}</table></div>
</html>"""
        (self.export_dir / 'rc1_test_center.html').write_text(html, encoding='utf-8')
