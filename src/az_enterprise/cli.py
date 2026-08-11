from __future__ import annotations

import argparse
import json

from .core.control_layer_rc2 import RC2ControlLayer
from .core.production_director import ProductionDirector
from .core.production_visual_manager import ProductionVisualManager
from .core.project_config_rc2 import ProjectConfigRC2
from .core.render_engine_rc2 import RenderEngineRC2
from .core.visual_asset_registrar import VisualAssetRegistrar


def _print_progress(payload: dict) -> None:
    stage = payload.get("stage", "RENDER")
    details = {
        key: value
        for key, value in payload.items()
        if key != "stage"
    }

    if details:
        print(
            f"[{stage}] "
            + json.dumps(
                details,
                ensure_ascii=False,
            )
        )
    else:
        print(f"[{stage}]")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    render_rc2_parser = subparsers.add_parser(
        "render-rc2",
        help="Canonical ATLAS ZERO RC2 production render.",
    )
    render_rc2_parser.add_argument("project_id")

    production_rc2_parser = subparsers.add_parser(
        "production-rc2",
        help="Run the complete canonical RC2 chain: timeline, voice, render.",
    )
    production_rc2_parser.add_argument("project_id")
    production_rc2_parser.add_argument(
        "--voice-name",
        default="Microsoft Irina Desktop",
    )
    production_rc2_parser.add_argument(
        "--speech-rate",
        type=int,
        default=0,
    )
    production_rc2_parser.add_argument(
        "--reuse-timeline",
        action="store_true",
        help="Reuse the canonical timeline when it already exists.",
    )
    production_rc2_parser.add_argument(
        "--reuse-voice",
        action="store_true",
        help="Reuse the canonical voice master when it already exists.",
    )

    voice_rc2_parser = subparsers.add_parser(
        "voice-rc2",
        help="Build only the canonical RC2 voice master.",
    )
    voice_rc2_parser.add_argument("project_id")
    voice_rc2_parser.add_argument(
        "--voice-name",
        default="Microsoft Irina Desktop",
    )
    voice_rc2_parser.add_argument(
        "--speech-rate",
        type=int,
        default=0,
    )
    voice_rc2_parser.add_argument(
        "--scene-id",
        default=None,
        help=(
            "Render only the specified scene "
            "(for example: VO01)."
        ),
    )

    production_parser = subparsers.add_parser("production-status")
    production_parser.add_argument("project_id")
    production_parser.add_argument("--days", type=int, default=4)

    visual_queue_parser = subparsers.add_parser("visual-queue")
    visual_queue_parser.add_argument("project_id")

    visual_progress_parser = subparsers.add_parser("visual-progress")
    visual_progress_parser.add_argument("project_id")

    visual_register_parser = subparsers.add_parser("visual-register")
    visual_register_parser.add_argument("project_id")

    parser.add_argument(
        "--pipeline",
        action="store_true",
        help=(
            "Compatibility alias for the canonical Franklin RC2 production "
            "chain."
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.command == "render-rc2":
        config = ProjectConfigRC2(
            project_id=args.project_id,
        )

        result = RenderEngineRC2(
            config,
            progress=None if args.json else _print_progress,
        ).run()

        if args.json:
            print(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print("ATLAS ZERO RC2 Render Engine")
            print("Project:", args.project_id)
            print("State:", result.get("state"))
            print("Authority:", result.get("authority"))
            print("Backend:", result.get("backend"))
            print("Output MP4:", result.get("output"))

        return

    if args.command == "production-rc2":
        result = RC2ControlLayer(
            project_id=args.project_id,
            voice_name=args.voice_name,
            speech_rate=args.speech_rate,
        ).run(
            rebuild_timeline=not args.reuse_timeline,
            rebuild_voice=not args.reuse_voice,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("ATLAS ZERO RC2 Production Chain")
            print("Project:", args.project_id)
            print("State:", result.get("state"))
            print("Authority:", result.get("authority"))
            print("Output MP4:", result.get("output"))
            print("Report:", result.get("report_path"))

        return

    if args.command == "voice-rc2":
        result = RC2ControlLayer(
            project_id=args.project_id,
            voice_name=args.voice_name,
            speech_rate=args.speech_rate,
            scene_id=args.scene_id,
        ).build_voice()

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("ATLAS ZERO RC2 Voice Production")
            print("Project:", args.project_id)
            print("State:", result.get("state"))
            print("Authority:", result.get("authority"))
            print("Voice:", result.get("voice_name"))
            print("Master Audio:", result.get("master_audio_path"))
            print("Report:", result.get("report_path"))

        return

    if args.command == "production-status":
        result = ProductionDirector(
            project_id=args.project_id,
            deadline_days_remaining=args.days,
        ).run()

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("ATLAS ZERO Production Director MVP")
            print("Project:", result.get("project_id"))
            print("Days Remaining:", result.get("deadline_days_remaining"))
            print(
                "Readiness:",
                f"{result.get('release_progress_percent')}%",
            )
            print("Main Blocker:", result.get("main_blocker"))
            print("Next Action:", result.get("next_action"))
            print("Next Module:", result.get("next_module"))
            print(
                "Status:",
                (
                    f"workspace/exports/{args.project_id}/"
                    "production_director_status.json"
                ),
            )
            print(
                "Brief:",
                (
                    f"workspace/exports/{args.project_id}/"
                    "production_director_brief.md"
                ),
            )

        return

    if args.command == "visual-queue":
        result = ProductionVisualManager(
            project_id=args.project_id,
        ).run_queue()

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("ATLAS ZERO Offline Visual Queue")
            print("Project:", args.project_id)
            print("Queue Items:", len(result.get("queue_items", [])))
            print(
                "Queue:",
                (
                    f"workspace/exports/{args.project_id}/"
                    "visual_generation_queue.json"
                ),
            )
            print(
                "Batch:",
                (
                    f"workspace/exports/{args.project_id}/"
                    "visual_generation_batch.md"
                ),
            )
            print(
                "Progress:",
                (
                    f"workspace/exports/{args.project_id}/"
                    "visual_generation_progress.json"
                ),
            )

        return

    if args.command == "visual-progress":
        result = ProductionVisualManager(
            project_id=args.project_id,
        ).run_progress()

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("ATLAS ZERO Offline Visual Progress")
            print("Project:", result.get("project_id"))
            print("Completed:", result.get("completed_items"))
            print("Pending:", result.get("pending_items"))
            print(
                "Completion:",
                f"{result.get('completion_percent')}%",
            )
            next_item = result.get("next_item") or {}
            print("Next Item:", next_item.get("visual_need"))
            print("Image Library:", result.get("image_library_path"))
            print(
                "Queue:",
                (
                    f"workspace/exports/{args.project_id}/"
                    "visual_generation_queue.json"
                ),
            )
            print(
                "Batch:",
                (
                    f"workspace/exports/{args.project_id}/"
                    "visual_generation_batch.md"
                ),
            )
            print(
                "Progress:",
                (
                    f"workspace/exports/{args.project_id}/"
                    "visual_generation_progress.json"
                ),
            )

        return

    if args.command == "visual-register":
        result = VisualAssetRegistrar(
            project_id=args.project_id,
        ).run()

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("ATLAS ZERO Visual Asset Registrar")
            print("Project:", result.get("project_id"))
            print("scanned:", result.get("scanned"))
            print("auto_accepted:", result.get("auto_accepted"))
            print("review:", result.get("review"))
            print("rejected:", result.get("rejected"))
            print("completed:", result.get("completed"))
            print("pending:", result.get("pending"))
            next_item = result.get("next_item") or {}
            print("next_item:", next_item.get("visual_need"))
            print("Report JSON:", result.get("report_json"))
            print("Report HTML:", result.get("report_html"))
            print("Review CSV:", result.get("review_csv"))

        return

    if args.pipeline:
        result = RC2ControlLayer(
            project_id="franklin",
        ).run(
            rebuild_timeline=True,
            rebuild_voice=True,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("ATLAS ZERO RC2 Production Chain")
            print("Pipeline complete")
            print("Project:", result.get("project_id"))
            print("State:", result.get("state"))
            print("Output:", result.get("output"))
            print("Report:", result.get("report_path"))

        return

    parser.print_help()


if __name__ == "__main__":
    main()
