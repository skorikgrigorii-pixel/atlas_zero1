from __future__ import annotations
import csv, json, shutil
from pathlib import Path
from .database import Database
from .paths import EXPORTS, WORKSPACE

class FinalAssemblyPack:
    """Creates a practical local assembly package for the Franklin project.

    The goal is to make the current OS useful now: a human operator can open one
    folder and build the rough cut in CapCut/DaVinci/Premiere using ordered media,
    timeline CSV, prompts for missing shots, subtitles and QC notes.
    """
    def __init__(self, db: Database, project_id='franklin'):
        self.db=db; self.project_id=project_id
        self.export_dir=EXPORTS/project_id; self.export_dir.mkdir(parents=True,exist_ok=True)
        self.pack_dir=self.export_dir/'FINAL_ASSEMBLY_PACK'

    def build(self)->dict:
        if self.pack_dir.exists(): shutil.rmtree(self.pack_dir)
        for sub in ['01_TIMELINE','02_MEDIA_REFERENCES','03_MISSING_PROMPTS','04_SUBTITLES','05_QC','06_IMPORT_TOOLS']:
            (self.pack_dir/sub).mkdir(parents=True,exist_ok=True)
        shots=self.db.rows('''SELECT s.idx,s.start_sec,s.end_sec,s.block,s.story_goal,s.visual_need,s.emotion,s.status,a.filename,a.path,a.media_type
                              FROM shots s LEFT JOIN assets a ON a.id=s.assigned_asset_id WHERE s.project_id=? ORDER BY s.idx''',(self.project_id,))
        missing=[r for r in shots if r['status']=='missing']
        assigned=[r for r in shots if r['status']!='missing']
        # ordered build sheet
        timeline_csv=self.pack_dir/'01_TIMELINE'/'01_build_order.csv'
        with timeline_csv.open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.writer(f); w.writerow(['№','Начало','Конец','Длительность','Блок','Что звучит/смысл','Материал','Тип','Статус','Операторское действие'])
            for r in shots:
                action='Положить на V1 и растянуть по таймкоду' if r['status']!='missing' else 'Оставить плейсхолдер, сгенерировать материал из prompt pack'
                w.writerow([r['idx'],r['start_sec'],r['end_sec'],round(r['end_sec']-r['start_sec'],2),r['block'],r['story_goal'],r['filename'] or 'MISSING',r['media_type'] or '',r['status'],action])
        # media references no copying heavy files by default
        media_csv=self.pack_dir/'02_MEDIA_REFERENCES'/'02_media_references.csv'
        with media_csv.open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.writer(f); w.writerow(['Файл','Путь','Тип','Использовать в шотах'])
            assets={}
            for r in assigned:
                assets.setdefault(r['filename'], {'path':r['path'], 'type':r['media_type'], 'shots':[]})['shots'].append(str(r['idx']))
            for name,d in sorted(assets.items()): w.writerow([name,d['path'],d['type'], ','.join(d['shots'])])
        # prompt pack
        prompt_md=self.pack_dir/'03_MISSING_PROMPTS'/'03_missing_prompts.md'
        lines=['# Пакет недостающих кадров Franklin\n']
        for r in missing:
            lines.append(f"\n## Shot {r['idx']} · {r['block']} · {r['start_sec']:.1f}–{r['end_sec']:.1f}\n")
            lines.append(f"**Потребность:** {r['visual_need']}\n\n**Эмоция:** {r['emotion']}\n\n")
            lines.append('```text\nUltra photorealistic historical documentary frame, 1845 Franklin Expedition, cold Arctic atmosphere, BBC / Netflix documentary realism, cinematic composition, no modern objects, no fantasy, no CGI look. Visual need: '+str(r['visual_need'])+'\n```\n')
        prompt_md.write_text(''.join(lines),encoding='utf-8')
        # subtitles copy/generate
        srt=self.pack_dir/'04_SUBTITLES'/'04_shot_subtitles.srt'
        srt_lines=[]
        def ts(sec):
            h=int(sec//3600); m=int((sec%3600)//60); s=int(sec%60); ms=int((sec-int(sec))*1000)
            return f'{h:02}:{m:02}:{s:02},{ms:03}'
        for i,r in enumerate(shots,1):
            srt_lines.append(f"{i}\n{ts(r['start_sec'])} --> {ts(r['end_sec'])}\n{r['story_goal']}\n\n")
        srt.write_text(''.join(srt_lines),encoding='utf-8')
        # QC readme
        manifest={
            'project_id': self.project_id,
            'version': 'RC1 Alpha 1.4',
            'shots': len(shots), 'assigned': len(assigned), 'missing': len(missing),
            'coverage_pct': round(len(assigned)/len(shots)*100,2) if shots else 0,
            'pack_dir': str(self.pack_dir),
            'ready_for_local_rough_cut': True,
            'ready_for_full_autonomy': False,
            'blockers': ['live API integrations', 'full CV model', 'native timeline/viewer']
        }
        (self.pack_dir/'assembly_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        readme=self.pack_dir/'README_СБОРКА.md'
        readme.write_text(f"""# ATLAS ZERO — Final Assembly Pack

Этот пакет предназначен для практической сборки чернового монтажа Franklin.

## Статус
- Шотов: {len(shots)}
- Назначено материалов: {len(assigned)}
- Нужно создать: {len(missing)}
- Покрытие: {manifest['coverage_pct']}%

## Порядок работы
1. Откройте `01_TIMELINE/01_build_order.csv`.
2. В CapCut положите единую дорожку озвучки 1–6 блоков на A1.
3. По строкам CSV укладывайте материалы на V1.
4. Для строк MISSING используйте `03_MISSING_PROMPTS/03_missing_prompts.md`.
5. После генерации новых кадров запустите Scan/Build ещё раз.

## Важно
Это локально рабочий production-пакет. Полная автономия требует live API и нативный timeline/viewer.
""",encoding='utf-8')
        # html index
        html=self.pack_dir/'index.html'
        html.write_text(f"""<!doctype html><meta charset='utf-8'><title>Final Assembly Pack</title><style>body{{font-family:Segoe UI,Arial;background:#0f172a;color:#e5e7eb;margin:24px}}a{{color:#38bdf8}}.card{{background:#111827;border:1px solid #334155;border-radius:12px;padding:16px;margin:12px 0}}</style><h1>ATLAS ZERO Final Assembly Pack</h1><div class='card'>Шотов: {len(shots)} · Назначено: {len(assigned)} · Нужно создать: {len(missing)} · Покрытие: {manifest['coverage_pct']}%</div><ul><li><a href='01_TIMELINE/01_build_order.csv'>Build order CSV</a></li><li><a href='02_MEDIA_REFERENCES/02_media_references.csv'>Media references</a></li><li><a href='03_MISSING_PROMPTS/03_missing_prompts.md'>Missing prompts</a></li><li><a href='04_SUBTITLES/04_shot_subtitles.srt'>Subtitles SRT</a></li><li><a href='README_СБОРКА.md'>Инструкция</a></li></ul>""",encoding='utf-8')
        return manifest
