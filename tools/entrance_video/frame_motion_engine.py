#!/usr/bin/env python3
"""ARKAON Frame Motion Engine v1: deterministic 2D frame animation.
Requires Pillow. Local only; no network, no rented GPU, no upload.
"""
import argparse
import math
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

FPS=24
COUNT=192
APPROVAL="ARKAON FRAME MOTION APPROVED"

def smooth(t):
    t=max(0.0,min(1.0,t))
    return t*t*(3-2*t)

def frame(source, idx, count=COUNT):
    w,h=source.size
    t=idx/(count-1)
    base=source.convert("RGB").copy()
    # Keep background and geometry fixed; overlay motion on separately controlled layers.
    # Center/radius may be tuned to the user's approved eye image.
    cx,cy=w//2,h//2
    unit=min(w,h)
    pupil_radius=int(unit*(0.025+0.015*smooth((t-0.14)/0.30)))
    # Transparent animated iris glow and pupil. This is an artistic overlay, not
    # true segmentation of the source iris.
    layer=Image.new("RGBA",(w,h),(0,0,0,0))
    d=ImageDraw.Draw(layer,"RGBA")
    activation=smooth((t-0.10)/0.42)
    ring_r=int(unit*0.115)
    alpha=int(100*activation*(0.75+0.25*math.sin(2*math.pi*t*2)))
    d.ellipse((cx-ring_r,cy-ring_r,cx+ring_r,cy+ring_r),outline=(52,202,255,alpha),width=max(2,unit//180))
    d.ellipse((cx-pupil_radius,cy-pupil_radius,cx+pupil_radius,cy+pupil_radius),fill=(3,10,22,int(110*activation)))
    # Radial circuitry light pulses: fixed locations; brightness changes over time.
    circuits=16
    for i in range(circuits):
        a=2*math.pi*i/circuits
        r0=unit*0.20
        r1=unit*0.31
        delay=i/circuits*0.35
        strength=smooth((t-0.32-delay)/0.17)
        if strength<=0: continue
        color=(65,205,255,int(160*strength))
        p0=(int(cx+math.cos(a)*r0),int(cy+math.sin(a)*r0))
        p1=(int(cx+math.cos(a)*r1),int(cy+math.sin(a)*r1))
        d.line((p0,p1),fill=color,width=max(2,unit//240))
        d.ellipse((p1[0]-3,p1[1]-3,p1[0]+3,p1[1]+3),fill=(247,204,105,int(170*strength)))
    # Soft glow is a separate composited layer.
    glow=layer.filter(ImageFilter.GaussianBlur(radius=max(4,unit//80)))
    base=Image.alpha_composite(base.convert("RGBA"),glow)
    base=Image.alpha_composite(base,layer)
    # Gentle fade-in only; no zoom, pan, shake or camera motion.
    fade=smooth(t/0.12)
    if fade<1:
        base=Image.blend(Image.new("RGBA",(w,h),(3,8,19,255)),base,fade)
    return base.convert("RGB")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--image",type=Path,required=True)
    p.add_argument("--frames-dir",type=Path,default=Path("frames-motion"))
    p.add_argument("--fps",type=int,default=FPS)
    p.add_argument("--seconds",type=int,default=8)
    args=p.parse_args()
    if not sys.stdin.isatty() or input("관리자 승인 ["+APPROVAL+"]: ").strip()!=APPROVAL:
        raise SystemExit("Administrator confirmation required")
    if not args.image.is_file(): raise SystemExit("Source image not found")
    if not 1<=args.fps<=60 or not 1<=args.seconds<=30: raise SystemExit("Invalid FPS/duration")
    count=args.fps*args.seconds
    if count>900: raise SystemExit("Frame count limit exceeded")
    if args.frames_dir.exists() and any(args.frames_dir.iterdir()):
        raise SystemExit("Frames directory must be empty; refusing overwrite")
    with Image.open(args.image) as src:
        src=src.convert("RGB")
        if max(src.size)>4096: raise SystemExit("Source too large; resize before processing")
        args.frames_dir.mkdir(parents=True,exist_ok=True)
        for i in range(count):
            frame(src,i,count).save(args.frames_dir/f"{i+1:06d}.png",optimize=True)
    print(f"Created {count} frames in {args.frames_dir}")
    print("Assemble: ffmpeg -framerate",args.fps,"-i",str(args.frames_dir/"%06d.png"),"-c:v libx264 -pix_fmt yuv420p -crf 20 -movflags +faststart arkaon-motion.mp4")

if __name__=="__main__": main()
