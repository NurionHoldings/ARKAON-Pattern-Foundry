#!/usr/bin/env python3
"""ARKAON v6: whole-eye progressive glow over existing v5 PNG frames.
Offline, Pillow-only, explicit local approval, no overwrite or uploads.
"""
import argparse
import json
import math
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageStat, ImageChops

APPROVAL="ARKAON WHOLE EYE GLOW APPROVED"
def ease(x):
    x=max(0.,min(1.,x))
    return x*x*(3-2*x)

def render(frame,i,n,cx,cy,rx,ry,intensity):
    w,h=frame.size
    t=i/max(1,n-1)
    # Center ignition -> spread -> breathing -> final afterglow.
    ignition=ease((t-.04)/.19)
    spread=ease((t-.20)/.33)
    breathing=.72+.28*math.sin(2*math.pi*(1.6*t-.15))**2
    afterglow=1-.30*ease((t-.82)/.18)
    strength=intensity*ignition*breathing*afterglow
    # Elliptical soft mask confines illumination to the eye area.
    mask=Image.new("L",(w,h),0)
    d=ImageDraw.Draw(mask)
    scale=.25+.75*spread
    ex=max(2,rx*scale);ey=max(2,ry*scale)
    d.ellipse((cx-ex,cy-ey,cx+ex,cy+ey),fill=255)
    mask=mask.filter(ImageFilter.GaussianBlur(max(3,int(min(rx,ry)*.22))))
    # Preserve underlying eye texture: soft screen-like composite.
    base=frame.convert("RGB")
    tint=Image.new("RGB",(w,h),(80,191,245))
    screen=ImageChops.screen(base,tint)
    alpha=mask.point(lambda a:round(a*strength*.40))
    result=Image.composite(screen,base,alpha)
    # Separate optical bloom, still clipped to a slightly larger ellipse.
    core=Image.new("RGBA",(w,h),(0,0,0,0))
    cd=ImageDraw.Draw(core,"RGBA")
    cr=max(2,rx*(.20+.55*spread))
    cd.ellipse((cx-cr,cy-cr*.78,cx+cr,cy+cr*.78),
               fill=(115,219,255,round(46*strength)))
    bloom=core.filter(ImageFilter.GaussianBlur(max(4,int(rx*.24))))
    result=Image.alpha_composite(result.convert("RGBA"),bloom)
    return result.convert("RGB")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--frames-dir",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--center-x",type=float,default=.5)
    p.add_argument("--center-y",type=float,default=.5)
    p.add_argument("--eye-width",type=float,default=.54,help="Eye glow width as fraction of image width")
    p.add_argument("--eye-height",type=float,default=.32,help="Eye glow height as fraction of image height")
    p.add_argument("--intensity",type=float,default=.8)
    args=p.parse_args()
    if not sys.stdin.isatty() or input("관리자 승인 ["+APPROVAL+"]: ").strip()!=APPROVAL:
        raise SystemExit("Administrator approval required")
    if not (.1<=args.center_x<=.9 and .1<=args.center_y<=.9 and .1<=args.eye_width<=.95
            and .05<=args.eye_height<=.8 and 0<=args.intensity<=1):
        raise SystemExit("Invalid eye glow geometry or intensity")
    if args.frames_dir.resolve()==args.output_dir.resolve():raise SystemExit("Input/output must differ")
    paths=sorted(args.frames_dir.glob("*.png"))
    if not 2<=len(paths)<=900:raise SystemExit("Need 2..900 PNG frames")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit("Output directory not empty")
    with Image.open(paths[0]) as im:w,h=im.size
    if max(w,h)>4096:raise SystemExit("Frame too large")
    cx=int(w*args.center_x);cy=int(h*args.center_y)
    rx=int(w*args.eye_width/2);ry=int(h*args.eye_height/2)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    sample_diffs=[]
    for i,path in enumerate(paths):
        with Image.open(path) as im:
            if im.size!=(w,h):raise SystemExit("Frame size mismatch")
            base=im.convert("RGB")
        output=render(base,i,len(paths),cx,cy,rx,ry,args.intensity)
        output.save(args.output_dir/f"{i+1:06d}.png")
        if i in (len(paths)//4,len(paths)//2,3*len(paths)//4):
            sample_diffs.append(round(sum(ImageStat.Stat(ImageChops.difference(base,output)).mean)/3,5))
    report={"frames":len(paths),"eye_ellipse":[cx,cy,rx,ry],
            "intensity":args.intensity,"sample_mean_rgb_changes":sample_diffs,
            "limitations":"Ellipse is manually aligned; not automatic eye segmentation. Visual review required."}
    (args.output_dir/"glow-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Created",len(paths),"whole-eye glow frames in",args.output_dir)
    print("QA:",args.output_dir/"glow-report.json")
if __name__=="__main__":main()
