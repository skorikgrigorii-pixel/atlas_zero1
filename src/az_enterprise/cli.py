from __future__ import annotations
import argparse, json
from .core.database import Database
from .core.workflow import WorkflowEngine
from .core.pipeline_runtime import PipelineRunManager
from .core.render_engine_rc1 import RenderEngineRC1


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='command')
    render_parser = subparsers.add_parser('render-rc1')
    render_parser.add_argument('project_id')
    parser.add_argument('--pipeline', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    if args.command == 'render-rc1':
        result = RenderEngineRC1(project_id=args.project_id).run()
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print('ATLAS ZERO Enterprise RC1 Render Engine')
            print('Project:', args.project_id)
            print('State:', result.get('state'))
            print('Output MP4:', result.get('output_mp4'))
            print('Report:', f"workspace/exports/{args.project_id}/render_rc1/render_report.json")
        return

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
