from pathlib import Path

root = Path.cwd()
core = root / "src" / "az_enterprise" / "core"
tests = root / "tests"

director_path = core / "director_ai_runtime.py"
gate_path = core / "quality_gate_rc2.py"

if not director_path.exists() or not gate_path.exists():
    raise SystemExit("Run this script from the atlas_zero1 repository root.")

helper_source = (Path(__file__).parent / "postproduction_quality_rc2.py").read_text(encoding="utf-8")
test_source = (Path(__file__).parent / "test_postproduction_quality_rc2.py").read_text(encoding="utf-8")
(core / "postproduction_quality_rc2.py").write_text(helper_source, encoding="utf-8")
(tests / "test_postproduction_quality_rc2.py").write_text(test_source, encoding="utf-8")

director = director_path.read_text(encoding="utf-8")

if "postproduction_quality_rc2" not in director:
    director = director.replace(
        "from .paths import EXPORTS\n",
        "from .paths import EXPORTS\n"
        "from .project_config_rc2 import ProjectConfigRC2\n"
        "from .postproduction_quality_rc2 import PostProductionQualityRC2\n",
        1,
    )

if "'FILM_TOO_LONG'" not in director:
    anchor = "    'API_NOT_READY': DirectorRule('API_NOT_READY', 'API не подключён для автоматического исполнения', 'blocking', 'connect_api'),\n"
    additions = (
        "    'FILM_TOO_LONG': DirectorRule('FILM_TOO_LONG', 'Фильм превышает целевую длительность', 'high', 'create_director_cut'),\n"
        "    'OPENING_HOOK_WEAK': DirectorRule('OPENING_HOOK_WEAK', 'Слабое вступление', 'high', 'strengthen_opening'),\n"
        "    'STATIC_IMAGE_TOO_LONG': DirectorRule('STATIC_IMAGE_TOO_LONG', 'Статичное изображение показывается слишком долго', 'medium', 'shorten_static_shot'),\n"
        "    'EXCLUDED_ASSET_USED': DirectorRule('EXCLUDED_ASSET_USED', 'Использован запрещённый материал', 'blocking', 'replace_excluded_asset'),\n"
        "    'NATURAL_SOUND_MISSING': DirectorRule('NATURAL_SOUND_MISSING', 'Не используется натуральный звук', 'medium', 'add_natural_sound'),\n"
        "    'ASSET_REUSED_TOO_SOON': DirectorRule('ASSET_REUSED_TOO_SOON', 'Материал повторяется слишком быстро', 'medium', 'replace_repeated_asset'),\n"
    )
    director = director.replace(anchor, anchor + additions, 1)

if "postproduction = self._postproduction_analysis()" not in director:
    director = director.replace(
        "        api_state = self._api_state()\n\n        quality = self._quality_scores(scenes, montage, cv_rows, api_state)\n",
        "        api_state = self._api_state()\n"
        "        postproduction = self._postproduction_analysis()\n\n"
        "        quality = self._quality_scores(scenes, montage, cv_rows, api_state)\n",
        1,
    )
    director = director.replace(
        "        issues += self._issues_for_diversity(scenes, montage)\n",
        "        issues += self._issues_for_diversity(scenes, montage)\n"
        "        issues += postproduction.get('issues', [])\n",
        1,
    )
    director = director.replace(
        "            'project_id': self.project_id,\n            'quality': quality,\n",
        "            'project_id': self.project_id,\n"
        "            'quality': quality,\n"
        "            'postproduction': postproduction,\n",
        1,
    )

if "def _postproduction_analysis" not in director:
    method = """    def _postproduction_analysis(self) -> dict[str, Any]:
        try:
            config = ProjectConfigRC2(project_id=self.project_id)
            return PostProductionQualityRC2(config).analyze()
        except Exception as exc:
            self.bus.emit(
                'DIRECTOR_AI_POSTPRODUCTION_ANALYSIS_FAILED',
                {'error': str(exc)},
            )
            return {
                'state': 'FAILED',
                'metrics': {},
                'issues': [{
                    'rule_code': 'POSTPRODUCTION_ANALYSIS_FAILED',
                    'severity': 'blocking',
                    'title': 'Не выполнен постпродакшн-анализ',
                    'reason': str(exc),
                    'recommendation': 'Проверить конфигурацию и финальный таймлайн.',
                }],
            }

"""
    director = director.replace("    def _clear_previous(self) -> None:\n", method + "    def _clear_previous(self) -> None:\n", 1)

director = director.replace("'version': '2.4'", "'version': '2.5'", 1)
director = director.replace("(self.project_id, '2.4',", "(self.project_id, '2.5',", 1)
director = director.replace("DIRECTOR_AI_2_4_COMPLETED", "DIRECTOR_AI_2_5_COMPLETED", 1)
director = director.replace("director_ai_2_4_report.json", "director_ai_2_5_report.json", 1)
director = director.replace("director_ai_2_4.html", "director_ai_2_5.html", 1)
director = director.replace("Director AI 2.4", "Director AI 2.5")
director_path.write_text(director, encoding="utf-8")

gate = gate_path.read_text(encoding="utf-8")
if "postproduction_quality_rc2" not in gate:
    gate = gate.replace(
        "from .render_engine_rc2 import RenderEngineRC2\n",
        "from .render_engine_rc2 import RenderEngineRC2\n"
        "from .postproduction_quality_rc2 import PostProductionQualityRC2\n",
        1,
    )

if "POSTPRODUCTION_ANALYZED" not in gate:
    block = """        postproduction = PostProductionQualityRC2(self.config).analyze()
        post_metrics = postproduction.get("metrics", {})

        add(
            "POSTPRODUCTION_ANALYZED",
            postproduction.get("state") == "ANALYZED",
            {"state": postproduction.get("state")},
        )
        add(
            "NO_EXCLUDED_ASSETS",
            int(post_metrics.get("excluded_assets_used", 0)) == 0,
            {"count": post_metrics.get("excluded_assets_used", 0)},
        )
        add(
            "FILM_DURATION_ACCEPTABLE",
            float(post_metrics.get("film_duration_sec", 0.0))
            <= float(post_metrics.get("maximum_film_duration_sec", 960.0)),
            {
                "duration_sec": post_metrics.get("film_duration_sec"),
                "maximum_sec": post_metrics.get("maximum_film_duration_sec"),
            },
        )
        add(
            "OPENING_HOOK_ACCEPTABLE",
            not bool(post_metrics.get("opening_hook_weak", False)),
            {
                "opening_items": post_metrics.get("opening_items"),
                "opening_unique_assets": post_metrics.get("opening_unique_assets"),
                "opening_video_items": post_metrics.get("opening_video_items"),
            },
            required=False,
        )
        add(
            "STATIC_IMAGE_DURATION_ACCEPTABLE",
            int(post_metrics.get("static_image_overruns", 0)) == 0,
            {"count": post_metrics.get("static_image_overruns", 0)},
            required=False,
        )

"""
    gate = gate.replace("        context = {\n", block + "        context = {\n", 1)
    gate = gate.replace(
        '            "media_probe": media_probe,\n',
        '            "media_probe": media_probe,\n'
        '            "postproduction": postproduction,\n',
        1,
    )

gate_path.write_text(gate, encoding="utf-8")
print("Director AI 2.5 applied successfully.")
