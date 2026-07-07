from __future__ import annotations
import json, tkinter as tk
from tkinter import ttk
from pathlib import Path
from .core.paths import EXPORTS

BG='#0f172a'; PANEL='#111827'; TEXT='#e5e7eb'; MUTED='#94a3b8'

class TimelineViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('ATLAS ZERO — Native Timeline Viewer RC 1.5')
        self.geometry('1400x820')
        self.configure(bg=BG)
        p=EXPORTS/'franklin'/'native_viewer_model_rc.json'
        self.model=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'tracks':{'Видео':[],'QC':[]},'duration_sec':1}
        self._build()

    def _build(self):
        top=tk.Frame(self,bg='#020617',height=44); top.pack(fill='x')
        tk.Label(top,text='ATLAS ZERO Native Timeline',bg='#020617',fg=TEXT,font=('Segoe UI',12,'bold')).pack(side='left',padx=12)
        tk.Label(top,text=f"Клипов: {len(self.model['tracks'].get('Видео',[]))} · Длительность: {self.model.get('duration_sec',0):.1f}s",bg='#020617',fg=MUTED,font=('Segoe UI',9)).pack(side='left')
        body=tk.PanedWindow(self,orient='horizontal',bg=BG,sashwidth=6); body.pack(fill='both',expand=True,padx=10,pady=10)
        left=tk.Frame(body,bg=BG); right=tk.Frame(body,bg=PANEL,width=330)
        body.add(left,stretch='always'); body.add(right)
        self.canvas=tk.Canvas(left,bg='#0b1220',highlightthickness=0,height=620)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.draw())
        tk.Label(right,text='Инспектор',bg=PANEL,fg=TEXT,font=('Segoe UI',12,'bold')).pack(anchor='w',padx=12,pady=10)
        self.info=tk.Text(right,bg='#020617',fg=TEXT,font=('Segoe UI',9),relief='flat',wrap='word')
        self.info.pack(fill='both',expand=True,padx=12,pady=8)
        self.draw()

    def draw(self):
        self.canvas.delete('all')
        clips=self.model['tracks'].get('Видео',[]); dur=max(float(self.model.get('duration_sec') or 1),1)
        w=max(self.canvas.winfo_width(),800); lane_h=42; top=30
        self.canvas.create_text(12,12,anchor='w',fill=TEXT,font=('Segoe UI',10,'bold'),text='Видео')
        for c in clips:
            x1=20+(w-40)*c['start']/dur; x2=20+(w-40)*c['end']/dur
            y1=top+(int(c['idx'])%12)*lane_h; y2=y1+28
            color='#22c55e' if c.get('status')=='assigned' else '#f59e0b'
            rect=self.canvas.create_rectangle(x1,y1,x2,y2,fill=color,outline='')
            txt=self.canvas.create_text((x1+x2)/2,y1+14,fill='#020617',font=('Segoe UI',7,'bold'),text=str(c['idx']))
            self.canvas.tag_bind(rect,'<Button-1>',lambda e,clip=c:self.show_clip(clip))
            self.canvas.tag_bind(txt,'<Button-1>',lambda e,clip=c:self.show_clip(clip))
        for sec in range(0,int(dur)+1,60):
            x=20+(w-40)*sec/dur
            self.canvas.create_line(x,top-12,x,top+12*lane_h,fill='#1f2937')
            self.canvas.create_text(x+3,top-18,anchor='w',fill=MUTED,font=('Segoe UI',7),text=f'{sec//60:02d}:00')

    def show_clip(self, c):
        self.info.delete('1.0','end')
        self.info.insert('end', json.dumps(c, ensure_ascii=False, indent=2))

def main():
    TimelineViewer().mainloop()

if __name__=='__main__': main()
