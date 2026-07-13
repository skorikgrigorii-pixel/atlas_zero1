from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
TOOLS_DIR = ROOT / "tools"
WORKSPACE = ROOT / "workspace"


class DirectorCoreRC1:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id

        self.project_dir = (
            WORKSPACE
            / "projects"
            / project_id
        )

        self.export_dir = (
            WORKSPACE
            / "exports"
            / project_id
        )

        self.render_dir = (
            self.export_dir
            / "render_rc1"
        )

        self.timeline_path = (
            self.export_dir
            / "movie_runtime_rc1"
            / "timeline.json"
        )

        self.render_output = (
            self.render_dir
            / f"{project_id}_render_rc1.mp4"
        )

        # Текущий RenderEngine Franklin сохраняет файл
        # под этим фиксированным именем.
        if project_id == "franklin":
            self.render_output = (
                self.render_dir
                / "franklin_render_rc1.mp4"
            )

        self.recovered_output = (
            self.render_dir
            / "franklin_multimedia_v3_40_assets_fixed.mp4"
        )

        self.final_dir = (
            self.export_dir
            / "director_core_rc1"
        )

        self.final_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.report_path = (
            self.final_dir
            / "director_core_report.json"
        )

        self.state_path = (
            self.final_dir
            / "director_core_state.json"
        )

        self.python = Path(sys.executable)

        self.ffmpeg = shutil.which("ffmpeg")
        self.ffprobe = shutil.which("ffprobe")

        if not self.ffmpeg:
            raise RuntimeError("FFmpeg не найден.")

        if not self.ffprobe:
            raise RuntimeError("FFprobe не найден.")

        self.report: dict[str, Any] = {
            "version": "1.0",
            "project_id": project_id,
            "state": "STARTING",
            "started_at": datetime.now().isoformat(),
            "stages": [],
        }

    def save_state(
        self,
        stage: str,
        state: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "project_id": self.project_id,
            "stage": stage,
            "state": state,
            "updated_at": datetime.now().isoformat(),
            "details": details or {},
        }

        self.state_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def record_stage(
        self,
        name: str,
        state: str,
        started_at: float,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.report["stages"].append(
            {
                "name": name,
                "state": state,
                "duration_sec": round(
                    time.time() - started_at,
                    3,
                ),
                "details": details or {},
            }
        )

        self.report_path.write_text(
            json.dumps(
                self.report,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def run_script(
        self,
        stage_name: str,
        script_name: str,
    ) -> None:
        script_path = (
            TOOLS_DIR
            / script_name
        )

        if not script_path.exists():
            raise FileNotFoundError(
                f"Не найден модуль: {script_path}"
            )

        started = time.time()

        self.save_state(
            stage_name,
            "RUNNING",
            {
                "script": str(script_path),
            },
        )

        print()
        print("=" * 76)
        print(f"[{stage_name}]")
        print(f"Запуск: {script_name}")
        print("=" * 76)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(
            ROOT / "src"
        )

        process = subprocess.run(
            [
                str(self.python),
                str(script_path),
            ],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            check=False,
        )

        if process.returncode != 0:
            self.record_stage(
                stage_name,
                "FAILED",
                started,
                {
                    "script": str(script_path),
                    "return_code": process.returncode,
                },
            )

            self.save_state(
                stage_name,
                "FAILED",
                {
                    "return_code": process.returncode,
                },
            )

            raise RuntimeError(
                f"Этап {stage_name} завершился "
                f"с кодом {process.returncode}."
            )

        self.record_stage(
            stage_name,
            "COMPLETED",
            started,
            {
                "script": str(script_path),
            },
        )

        self.save_state(
            stage_name,
            "COMPLETED",
        )

    def verify_temporal_report(self) -> dict[str, Any]:
        path = (
            self.export_dir
            / "semantic_director_v1_2_temporal"
            / "temporal_assignment_summary.json"
        )

        if not path.exists():
            raise FileNotFoundError(
                f"Не найден временной отчёт: {path}"
            )

        report = json.loads(
            path.read_text(encoding="utf-8")
        )

        if report.get("state") != "TEMPORALLY_VALIDATED":
            raise RuntimeError(
                "Temporal Guard не подтвердил таймлайн."
            )

        if int(
            report.get("temporal_violations", 0)
        ) != 0:
            raise RuntimeError(
                "В таймлайне остались временные нарушения."
            )

        if int(
            report.get(
                "modern_assets_in_historical",
                0,
            )
        ) != 0:
            raise RuntimeError(
                "Современные материалы остались "
                "в исторических сценах."
            )

        return report

    def verify_timeline(self) -> dict[str, Any]:
        if not self.timeline_path.exists():
            raise FileNotFoundError(
                f"Timeline не найден: {self.timeline_path}"
            )

        timeline = json.loads(
            self.timeline_path.read_text(
                encoding="utf-8"
            )
        )

        incomplete = [
            row
            for row in timeline
            if (
                row.get("status") != "assigned"
                or not row.get("asset_path")
            )
        ]

        unique_assets = {
            row.get("asset_path")
            for row in timeline
            if row.get("asset_path")
        }

        media_usage: dict[str, int] = {}

        for row in timeline:
            media_type = str(
                row.get("media_type") or "missing"
            )

            media_usage[media_type] = (
                media_usage.get(media_type, 0)
                + 1
            )

        result = {
            "items": len(timeline),
            "incomplete": len(incomplete),
            "unique_assets": len(unique_assets),
            "media_usage": media_usage,
        }

        if len(timeline) != 149:
            raise RuntimeError(
                f"Timeline содержит {len(timeline)} "
                "шотов вместо 149."
            )

        if incomplete:
            raise RuntimeError(
                f"Незакрытых шотов: {len(incomplete)}."
            )

        if media_usage.get("video", 0) < 3:
            raise RuntimeError(
                "Видео не были назначены в таймлайн."
            )

        return result

    @staticmethod
    def newest_render_temp() -> Path | None:
        temp_root = Path(
            os.environ.get(
                "TEMP",
                str(Path.home() / "AppData/Local/Temp"),
            )
        )

        candidates = sorted(
            [
                path
                for path
                in temp_root.glob(
                    "atlas_zero_franklin_*"
                )
                if path.is_dir()
            ],
            key=lambda path: (
                path.stat().st_mtime
            ),
            reverse=True,
        )

        return (
            candidates[0]
            if candidates
            else None
        )

    def render_with_progress(self) -> None:
        script_path = (
            TOOLS_DIR
            / "render_franklin_roughcut.py"
        )

        if not script_path.exists():
            raise FileNotFoundError(script_path)

        started = time.time()

        self.save_state(
            "RENDER",
            "RUNNING",
        )

        print()
        print("=" * 76)
        print("[RENDER]")
        print("Запускаю RenderEngine RC1")
        print("=" * 76)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(
            ROOT / "src"
        )

        process = subprocess.Popen(
            [
                str(self.python),
                str(script_path),
            ],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
        )

        last_count = -1
        temp_dir: Path | None = None
        render_start = time.time()

        while process.poll() is None:
            current_temp = (
                self.newest_render_temp()
            )

            if current_temp:
                temp_dir = current_temp

                count = len(
                    list(
                        temp_dir.glob(
                            "segment_*.mp4"
                        )
                    )
                )

                if count != last_count:
                    elapsed = int(
                        time.time() - render_start
                    )

                    percent = round(
                        count / 149 * 100,
                        1,
                    )

                    print(
                        f"[RENDER SEGMENTS] "
                        f"{count:03d}/149 "
                        f"({percent:5.1f}%) | "
                        f"{elapsed // 60:02d}:"
                        f"{elapsed % 60:02d}",
                        flush=True,
                    )

                    self.save_state(
                        "RENDER_SEGMENTS",
                        "RUNNING",
                        {
                            "segments": count,
                            "total": 149,
                            "percent": percent,
                            "temp_dir": str(temp_dir),
                        },
                    )

                    last_count = count

            time.sleep(3)

        return_code = process.wait()

        if return_code != 0:
            self.record_stage(
                "RENDER",
                "FAILED",
                started,
                {
                    "return_code": return_code,
                    "temp_dir": (
                        str(temp_dir)
                        if temp_dir
                        else None
                    ),
                },
            )

            raise RuntimeError(
                f"RenderEngine завершился "
                f"с кодом {return_code}."
            )

        print(
            "[RENDER SEGMENTS] 149/149"
        )
        print(
            "[RENDER CONCAT] Проверяю склейку..."
        )

        self.record_stage(
            "RENDER",
            "COMPLETED",
            started,
            {
                "temp_dir": (
                    str(temp_dir)
                    if temp_dir
                    else None
                ),
            },
        )

    def probe_mp4(
        self,
        path: Path,
    ) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path)

        process = subprocess.run(
            [
                str(self.ffprobe),
                "-v",
                "error",
                "-show_entries",
                "format=duration,size",
                "-show_entries",
                (
                    "stream=index,codec_type,"
                    "codec_name,width,height,"
                    "r_frame_rate"
                ),
                "-of",
                "json",
                str(path),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )

        if process.returncode != 0:
            raise RuntimeError(
                process.stderr.strip()
                or "FFprobe не смог проверить MP4."
            )

        return json.loads(
            process.stdout
        )

    def recover_render(self) -> Path:
        script_path = (
            TOOLS_DIR
            / "recover_franklin_multimedia_render.py"
        )

        if not script_path.exists():
            raise FileNotFoundError(
                f"Recovery script не найден: {script_path}"
            )

        started = time.time()

        print()
        print(
            "[RECOVERY] Итоговый MP4 повреждён. "
            "Повторно использую 149 готовых сегментов."
        )

        self.save_state(
            "RECOVERY",
            "RUNNING",
        )

        process = subprocess.run(
            [
                str(self.python),
                str(script_path),
            ],
            cwd=ROOT,
            env={
                **os.environ,
                "PYTHONPATH": str(
                    ROOT / "src"
                ),
            },
            stdin=subprocess.DEVNULL,
            check=False,
        )

        if process.returncode != 0:
            self.record_stage(
                "RECOVERY",
                "FAILED",
                started,
                {
                    "return_code": (
                        process.returncode
                    ),
                },
            )

            raise RuntimeError(
                "Автоматическое восстановление "
                "рендера не выполнено."
            )

        if not self.recovered_output.exists():
            raise FileNotFoundError(
                self.recovered_output
            )

        self.record_stage(
            "RECOVERY",
            "COMPLETED",
            started,
            {
                "output": str(
                    self.recovered_output
                ),
            },
        )

        return self.recovered_output

    def publish_final_file(
        self,
        source: Path,
    ) -> Path:
        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        final_path = (
            self.final_dir
            / (
                f"{self.project_id}_"
                f"director_core_{timestamp}.mp4"
            )
        )

        shutil.copy2(
            source,
            final_path,
        )

        latest_path = (
            self.final_dir
            / f"{self.project_id}_LATEST.mp4"
        )

        shutil.copy2(
            source,
            latest_path,
        )

        return final_path

    def run(self) -> dict[str, Any]:
        try:
            print("=" * 76)
            print("ATLAS ZERO — DIRECTOR CORE RC1")
            print("=" * 76)
            print("PROJECT =", self.project_id)

            self.report["state"] = "RUNNING"

            self.run_script(
                "VISUAL_INTELLIGENCE_IMAGES",
                "visual_intelligence_v1.py",
            )

            self.run_script(
                "VISUAL_INTELLIGENCE_MULTIMEDIA",
                (
                    "visual_intelligence_"
                    "v1_1_multimedia.py"
                ),
            )

            self.run_script(
                "SEMANTIC_TEMPORAL_DIRECTOR",
                (
                    "semantic_director_"
                    "v1_2_temporal.py"
                ),
            )

            print()
            print("[QC TIMELINE] Проверяю таймлайн...")

            temporal_report = (
                self.verify_temporal_report()
            )

            timeline_report = (
                self.verify_timeline()
            )

            self.report["temporal_qc"] = (
                temporal_report
            )

            self.report["timeline_qc"] = (
                timeline_report
            )

            print(
                "[QC TIMELINE] "
                f"{timeline_report['items']} шотов, "
                f"{timeline_report['unique_assets']} "
                "уникальных материалов."
            )

            print(
                "[QC TEMPORAL] "
                "Временных нарушений: 0."
            )

            self.render_with_progress()

            print()
            print(
                "[VERIFY MP4] Проверяю итоговый файл..."
            )

            source_output = self.render_output

            try:
                media_probe = self.probe_mp4(
                    source_output
                )

                print(
                    "[VERIFY MP4] Файл корректен."
                )

            except Exception as exc:
                print(
                    "[VERIFY MP4] Ошибка:",
                    exc,
                )

                source_output = (
                    self.recover_render()
                )

                media_probe = self.probe_mp4(
                    source_output
                )

                print(
                    "[VERIFY MP4] "
                    "Восстановленный файл корректен."
                )

            final_output = (
                self.publish_final_file(
                    source_output
                )
            )

            self.report.update(
                {
                    "state": "COMPLETED",
                    "completed_at": (
                        datetime.now().isoformat()
                    ),
                    "final_output": str(
                        final_output
                    ),
                    "latest_output": str(
                        self.final_dir
                        / (
                            f"{self.project_id}"
                            "_LATEST.mp4"
                        )
                    ),
                    "media_probe": media_probe,
                }
            )

            self.report_path.write_text(
                json.dumps(
                    self.report,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            self.save_state(
                "DIRECTOR_CORE",
                "COMPLETED",
                {
                    "final_output": str(
                        final_output
                    ),
                },
            )

            print()
            print("=" * 76)
            print("DIRECTOR CORE COMPLETED")
            print("=" * 76)
            print("FINAL OUTPUT =", final_output)
            print("REPORT       =", self.report_path)

            return self.report

        except Exception as exc:
            self.report["state"] = "FAILED"
            self.report["completed_at"] = (
                datetime.now().isoformat()
            )
            self.report["error"] = str(exc)

            self.report_path.write_text(
                json.dumps(
                    self.report,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            self.save_state(
                "DIRECTOR_CORE",
                "FAILED",
                {
                    "error": str(exc),
                },
            )

            print()
            print("=" * 76)
            print("DIRECTOR CORE FAILED")
            print("=" * 76)
            print("ERROR  =", exc)
            print("REPORT =", self.report_path)

            raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "ATLAS ZERO autonomous Director Core RC1"
        )
    )

    parser.add_argument(
        "--project-id",
        default="franklin",
    )

    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()

    DirectorCoreRC1(
        project_id=arguments.project_id
    ).run()
