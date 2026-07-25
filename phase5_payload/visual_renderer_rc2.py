from __future__ import annotations
import json, os, shutil, subprocess
from pathlib import Path
from typing import Any, Callable, Iterable
from .camera_motion_rc2 import CameraMotionEngine, FFmpegMotionBuilder

ProgressCallback = Callable[[dict[str, Any]], None]

class VisualRendererRC2:
    def __init__(self, *, project_id: str, output_dir: Path, target_width: int=1920, target_height: int=1080, target_fps: int=30, progress: ProgressCallback|None=None) -> None:
        self.project_id=project_id; self.output_dir=Path(output_dir)
        self.target_width=int(target_width); self.target_height=int(target_height); self.target_fps=int(target_fps)
        self.progress=progress or (lambda payload: None)
        self.ffmpeg=shutil.which("ffmpeg")
        if not self.ffmpeg: raise RuntimeError("ffmpeg is not available in PATH")
        self.motion_engine=CameraMotionEngine(fps=self.target_fps)
        self.motion_builder=FFmpegMotionBuilder(width=self.target_width,height=self.target_height,fps=self.target_fps)
        self.temp_dir=self.output_dir/"_native_visual_tmp"; self.segment_dir=self.temp_dir/"segments"
        self.output_video=self.output_dir/"visual_master_rc2.mp4"; self.report_path=self.output_dir/"visual_render_report_rc2.json"
        self.concat_manifest_path=self.temp_dir/"concat_input.txt"

    def run(self, clips: Iterable[Any]) -> dict[str, Any]:
        ordered=sorted(list(clips), key=lambda c:(float(getattr(c,"start_sec",0.0)),int(getattr(c,"shot_index",0))))
        if not ordered: raise RuntimeError("VisualRendererRC2 received zero clips")
        self._reset_workspace(); segments=[]; records=[]
        self._emit("VISUAL_RENDER_START",project_id=self.project_id,clips=len(ordered),migration_phase="PHASE_5_NATIVE_CAMERA_MOTION")
        for pos,clip in enumerate(ordered,1):
            profile=self.motion_engine.build_profile(clip)
            segment=self._render_segment(pos,clip,profile); segments.append(segment)
            records.append({"position":pos,"shot_id":str(getattr(clip,"shot_id",f"shot_{pos:04d}")),"shot_index":int(getattr(clip,"shot_index",pos)),"media_type":str(getattr(clip,"media_type","")),"asset_path":str(getattr(clip,"asset_path","")),"duration_sec":float(getattr(clip,"duration_sec",0.0)),"camera_motion":profile.to_dict(),"output":str(segment),"output_size_bytes":segment.stat().st_size})
        concat=self._concat_segments(segments); self._verify_video_output(concat)
        temp=self.output_video.with_suffix(self.output_video.suffix+".partial"); temp.unlink(missing_ok=True); shutil.copy2(concat,temp); self._verify_video_output(temp); os.replace(temp,self.output_video)
        moving=sum(1 for r in records if r["camera_motion"]["enabled"])
        report={"state":"VISUAL_RENDERED","schema":"atlas_zero.visual_render.rc2.v2","project_id":self.project_id,"backend":"VisualRendererRC2","migration_phase":"PHASE_5_NATIVE_CAMERA_MOTION","output_video":str(self.output_video),"output_exists":self.output_video.exists(),"output_size_bytes":self.output_video.stat().st_size,"target":{"width":self.target_width,"height":self.target_height,"fps":self.target_fps,"pixel_format":"yuv420p","video_codec":"libx264"},"clips_total":len(ordered),"segments_rendered":len(segments),"motion_segments":moving,"static_segments":len(records)-moving,"segments":records,"concat_manifest":str(self.concat_manifest_path),"camera_motion_mode":"native_phase_5","transition_mode":"hard_cut_pending_phase_6"}
        self._write_json(self.report_path,report); self._emit("VISUAL_RENDER_COMPLETE",output=str(self.output_video),segments=len(segments),motion_segments=moving); return report

    def _reset_workspace(self):
        self.output_dir.mkdir(parents=True,exist_ok=True)
        if self.temp_dir.exists(): shutil.rmtree(self.temp_dir)
        self.segment_dir.mkdir(parents=True,exist_ok=True)

    def _render_segment(self,pos,clip,profile):
        media=str(getattr(clip,"media_type","")).strip().lower(); asset=Path(str(getattr(clip,"asset_path","")))
        duration=round(float(getattr(clip,"duration_sec",0.0)),6); source_in=max(0.0,float(getattr(clip,"source_in_sec",0.0))); source_out=getattr(clip,"source_out_sec",None)
        if media not in {"image","video"}: raise RuntimeError(f"Unsupported media type: {media!r}")
        if not asset.is_file(): raise FileNotFoundError(f"Visual asset is missing: {asset}")
        if duration<=0: raise RuntimeError("Invalid clip duration")
        shot=self._safe_name(str(getattr(clip,"shot_id",f"shot_{pos:04d}"))); output=self.segment_dir/f"{pos:04d}_{shot}.mp4"; vf=self.motion_builder.build(profile)
        common=["-map_metadata","-1","-an","-r",str(self.target_fps),"-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-movflags","+faststart",str(output)]
        if media=="image": cmd=[self.ffmpeg,"-y","-loop","1","-framerate",str(self.target_fps),"-i",str(asset),"-t",self._sec(duration),"-vf",vf,*common]
        else:
            requested=duration if source_out is None else min(duration,max(0.0,float(source_out)-source_in))
            if requested<=0: raise RuntimeError("Empty source range")
            cmd=[self.ffmpeg,"-y","-ss",self._sec(source_in),"-i",str(asset),"-t",self._sec(requested),"-vf",vf,*common]
        self._emit("VISUAL_SEGMENT_START",position=pos,shot_id=shot,camera_motion=profile.motion_type,motion_enabled=profile.enabled)
        self._run_ffmpeg(cmd,step=f"Phase 5 segment {shot}"); self._verify_video_output(output); return output

    def _concat_segments(self,segments):
        self.concat_manifest_path.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in segments)+"\n",encoding="utf-8")
        output=self.temp_dir/"visual_concat_rc2.mp4"; cmd=[self.ffmpeg,"-y","-f","concat","-safe","0","-i",str(self.concat_manifest_path),"-an","-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p","-r",str(self.target_fps),"-movflags","+faststart",str(output)]
        self._run_ffmpeg(cmd,step="Phase 5 native visual concat"); return output

    def _verify_video_output(self,path):
        if not Path(path).is_file() or Path(path).stat().st_size<=0: raise RuntimeError(f"Invalid native visual output: {path}")
    @staticmethod
    def _safe_name(v): return ("".join(c if c.isalnum() or c in "-_" else "_" for c in v).strip("_")[:80] or "shot")
    @staticmethod
    def _sec(v): return f"{max(0.0,float(v)):.6f}"
    @staticmethod
    def _run_ffmpeg(command,*,step):
        if "-nostdin" not in command: command=[command[0],"-nostdin",*command[1:]]
        p=subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,text=True,check=False)
        if p.returncode!=0: raise RuntimeError(f"ffmpeg failed during {step}:\n"+"\n".join(p.stderr.splitlines()[-30:]))
    def _emit(self,stage,**details): self.progress({"stage":stage,**details})
    @staticmethod
    def _write_json(path,payload):
        path.parent.mkdir(parents=True,exist_ok=True); temp=path.with_suffix(path.suffix+".partial"); temp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"); os.replace(temp,path)
