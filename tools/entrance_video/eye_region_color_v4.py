#!/usr/bin/env python3
"""ARKAON v4: add individually timed color layers to existing v3 PNG frames.
Pillow only; never changes source frames. No network, no upload.
"""
import argparse
import json
import math
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

APPROVAL="ARKAON COLOR LAYERS APPROVED"
def clamp(x):return max(0,min(1,x))
def smooth(x):
    x=clamp(x)
    return x*x*(3-2*x)
def colorize(frame,i,n,cx,cy,rad,settings):
    w,h=frame.size
    t=i/max(1,n-1)
    base=frame.convert("RGBA")
    layer=Image.new("RGBA",(w,h),(0,0,0,0))
    d=ImageDraw.Draw(layer,"RGBA")
    # Iris: translucent colored annulus; preserve underlying texture and motion.
    activation=smooth((t-.08)/.25)
    rr=rad*.88
    pulse=.65+.35*math.sin(2*math.pi*(2*t+.1))**2
    alpha=int(settings["iris_alpha"]*activation*pulse)
    width=max(2,int(rad*.14))
    d.ellipse((cx-rr,cy-rr,cx+rr,cy+rr),outline=(25,192,255,alpha),width=width)
    # Pupil halo: separate narrow white ring.
    pr=rad*.38
    d.ellipse((cx-pr,cy-pr,cx+pr,cy+pr),outline=(230,247,255,int(settings["halo_alpha"]*activation*pulse)),width=max(2,int(rad*.04)))
    # Circuit traces are radial illustrative accents, NOT automatic image segmentation.
    count=settings["circuit_count"]
    for k in range(count):
        start=.32+.46*k/max(1,count-1)
        on=smooth((t-start)/.12)
        if on==0:continue
        angle=2*math.pi*k/count
        r0=rad*1.6;r1=rad*2.45
        p0=(int(cx+math.cos(angle)*r0),int(cy+math.sin(angle)*r0))
        p1=(int(cx+math.cos(angle)*r1),int(cy+math.sin(angle)*r1))
        d.line((p0,p1),fill=(246,179,75,int(settings["circuit_alpha"]*on)),width=max(2,int(rad*.045)))
        dot=max(2,int(rad*.045))
        d.ellipse((p1[0]-dot,p1[1]-dot,p1[0]+dot,p1[1]+dot),fill=(85,217,255,int(settings["circuit_alpha"]*on)))
    # Outer purple reflections: low intensity.
    if settings["outer_alpha"]:
        for k in range(4):
            angle=2*math.pi*(k/4+t*.04)
            x=cx+math.cos(angle)*rad*2.9;y=cy+math.sin(angle)*rad*2.9
            r=rad*.15
            d.ellipse((x-r,y-r,x+r,y+r),fill=(160,93,255,int(settings["outer_alpha"]*smooth((t-.45)/.3))))
    blur=layer.filter(ImageFilter.GaussianBlur(max(2,int(rad*.10))))
    glow_alpha=int(settings["glow_strength"]*255)
    if glow_alpha:
        blur.putalpha(blur.getchannel("A").point(lambda a:a*glow_alpha//255))
        base=Image.alpha_composite(base,blur)
    return Image.alpha_composite(base,layer).convert("RGB")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--frames-dir",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--center-x",type=float,default=.5)
    p.add_argument("--center-y",type=float,default=.5)
    p.add_argument("--iris-radius",type=float,default=.12)
    p.add_argument("--iris-alpha",type=int,default=110)
    p.add_argument("--halo-alpha",type=int,default=90)
    p.add_argument("--circuit-alpha",type=int,default=150)
    p.add_argument("--outer-alpha",type=int,default=32)
    p.add_argument("--circuit-count",type=int,default=12)
    p.add_argument("--glow-strength",type=float,default=.65)
    args=p.parse_args()
    if not sys.stdin.isatty() or input("관리자 승인 ["+APPROVAL+"]: ").strip()!=APPROVAL:
        raise SystemExit("Administrator confirmation required")
    if not (.1<=args.center_x<=.9 and .1<=args.center_y<=.9 and .04<=args.iris_radius<=.35):
        raise SystemExit("Invalid iris geometry")
    if any(not 0<=v<=255 for v in (args.iris_alpha,args.halo_alpha,args.circuit_alpha,args.outer_alpha)):
        raise SystemExit("Alpha must be 0..255")
    if not 0<=args.glow_strength<=1 or not 1<=args.circuit_count<=48:raise SystemExit("Invalid color settings")
    source=sorted(args.frames_dir.glob("*.png"))
    if len(source)<2 or len(source)>900:raise SystemExit("Expected 2..900 source PNG frames")
    if args.output_dir.resolve()==args.frames_dir.resolve():raise SystemExit("Input and output directories must differ")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):raise SystemExit("Output directory not empty")
    with Image.open(source[0]) as im: w,h=im.size
    if max(w,h)>4096:raise SystemExit("Frames too large")
    cx=int(w*args.center_x);cy=int(h*args.center_y);rad=int(min(w,h)*args.iris_radius)
    settings={k:getattr(args,k) for k in ("iris_alpha","halo_alpha","circuit_alpha","outer_alpha","circuit_count","glow_strength")}
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for i,path in enumerate(source):
        with Image.open(path) as im:
            if im.size!=(w,h):raise SystemExit("Inconsistent frame sizes")
            result=colorize(im,i,len(source),cx,cy,rad,settings)
            result.save(args.output_dir/f"{i+1:06d}.png")
    report={"frames":len(source),"input_dir":str(args.frames_dir),"output_dir":str(args.output_dir),
            "geometry":[cx,cy,rad],"settings":settings,
            "warning":"Illustrative overlays; circuitry is not automatically detected. Visually inspect alignment."}
    (args.output_dir/"color-layer-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Created",len(source),"color-layer frames:",args.output_dir)
if __name__=="__main__":main()
