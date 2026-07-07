from __future__ import annotations
import argparse, json
from .core.database import Database
from .core.workflow import WorkflowEngine
from .core.pipeline_runtime import PipelineRunManager


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pipeline', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    db = Database(); db.init()
    if args.pipeline:
        result = PipelineRunManager(db).run()
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print('ATLAS ZERO Enterprise RC1 Alpha 2.4')
            print('Pipeline complete')
            print('Run ID:', result.get('run_id'))
            print('Status:', result.get('status'))
            print('Report: workspace/exports/franklin/pipeline_run_report.html')
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
