from pathlib import Path
import sys, json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from az_enterprise.core.database import Database
from az_enterprise.core.pipeline_runtime import PipelineRunManager
from az_enterprise.core.paths import EXPORTS

db=Database(); db.init()
result=PipelineRunManager(db,'franklin').run()
exports=EXPORTS/'franklin'
required=['pipeline_run_report.json','pipeline_run_report.html','pipeline_task_queue.json','pipeline_task_events.json','монтажный_лист.csv','решения_режиссера.json','готовность_rc1.json','очередь_api.json','визуальный_анализ.csv','timeline_viewer_2.html','cv_model_report.json','story_engine_runtime.html','story_engine_2_3.html','story_scenes.csv','montage_sheet.csv','missing_story_requirements.md','director_ai_2_4.html','director_ai_2_4_report.json','director_tasks.csv','director_issues.csv','director_decision_matrix.csv','native_viewer_pro.html','franklin_e2e_runtime.html','live_api_test_suite.json','capcut_operator_bridge.html','FINAL_ASSEMBLY_PACK/index.html']
missing=[x for x in required if not (exports/x).exists()]
assert not missing, missing
assert result['status']=='done'
assert len(result['steps']) >= 20
assert result.get('counts_after', {}).get('shots', 0) >= 100
run = db.one('SELECT status,progress FROM pipeline_runs ORDER BY id DESC LIMIT 1')
assert run['status']=='done' and float(run['progress']) == 100.0
cv = json.loads((exports/'cv_model_report.json').read_text(encoding='utf-8'))['summary']
assert cv['engine'] != 'opencv_unavailable'
api = json.loads((exports/'live_api_test_suite.json').read_text(encoding='utf-8'))
assert 'configured' in api and 'rows' in api
director = json.loads((exports/'director_ai_2_4_report.json').read_text(encoding='utf-8'))
assert director['summary']['tasks'] >= 1
print('smoke tests passed', json.dumps({'run_id': result['run_id'], 'steps': len(result['steps']), 'pipeline_status': run['status'], 'progress': run['progress'], 'cv_engine': cv['engine'], 'cv_videos': cv.get('videos',0), 'api_mode': api['mode'], 'api_configured': api['configured'], 'director_quality': director['quality']['overall'], 'director_tasks': director['summary']['tasks']}, ensure_ascii=False), flush=True)
import os; os._exit(0)
