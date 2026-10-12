#!/usr/bin/env python3
"""ARKAON v3: local pixel-warp eye animation with frame-difference evidence.
Pillow only. No external calls, no GPU, no upload. Coordinates need visual calibration.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

APPROVAL="ARKAON EYE PIXEL MOTION APPROVED"

def render(src, i, n, cx, cy, iris_r, pupil_r):
    w,h=src.size
    t=i/(n-1)
    # Actual displacement and pupil magnification, not overlays.
    gaze_x=0.032*iris_r*math.sin(2*math.pi*t)
    gaze_y=0.020*iris_r*math.sin(4*math.pi*t)
    dilation=1.0+0.24*math.sin(2*math.pi*(t-0.18))
    # Transform source pixels with a local radial inverse mapping.
    # Move iris texture slightly and expand/contract central pupil texture.
    box=(max(0,int(cx-iris_r*1.35)),max(0,int(cy-iris_r*1.35)),
         min(w,int(cx+iris_r*1.35)),min(h,int(cy+iris_r*1.35)))
    x0,y0,x1,y1=box
    patch=src.crop(box).convert("RGB")
    pw,ph=patch.size
    from PIL import Image as PILImage
    # Transform via a coarse mesh, avoiding 1.5M per-pixel Python calls.
    step=max(5,int(iris_r/16))
    mesh=[]
    for yy in range(0,ph,step):
        for xx in range(0,pw,step):
            xr=min(xx+step,pw); yb=min(yy+step,ph)
            corners=[]
            for px,py in ((xx,yy),(xx,yb),(xr,yb),(xr,yy)):
                dx=px+x0-cx;dy=py+y0-cy
                radius=math.hypot(dx,dy)
                falloff=max(0.0,1.0-radius/(iris_r*1.12))**2
                # Only central pupil texture is dilated.
                pupil_weight=max(0.0,1.0-radius/max(pupil_r*2.1,1))**2
                inv=1.0/(1.0+(dilation-1.0)*pupil_weight)
                sx=cx+(dx-gaze_x*falloff)*inv-x0
                sy=cy+(dy-gaze_y*falloff)*inv-y0
                corners.extend((sx,sy))
            mesh.append(((xx,yy,xr,yb),tuple(corners)))
    warped=patch.transform((pw,ph),PILImage.Transform.MESH,mesh,
                            resample=PILImage.Resampling.BICUBIC)
    mask=Image.new("L",(pw,ph),0)
    d=ImageDraw.Draw(mask)
    # Feathered circle restricts changes to eye; frame stays locked.
    rr=int(iris_r*0.96)
    mx=cx-x0;my=cy-y0
    d.ellipse((mx-rr,my-rr,mx+rr,my+rr),fill=255)
    mask=mask.filter(ImageFilter.GaussianBlur(max(3,int(iris_r*0.10))))
    result=src.convert("RGB").copy()
    result.paste(warped,(x0,y0),mask)
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--image",type=Path,required=True)
    p.add_argument("--frames-dir",type=Path,default=Path("frames-eye-v3"))
    p.add_argument("--center-x",type=float,default=0.5,help="Iris center fraction of image width")
    p.add_argument("--center-y",type=float,default=0.5,help="Iris center fraction of image height")
    p.add_argument("--iris-radius",type=float,default=0.12,help="Iris radius fraction of min dimension")
    p.add_argument("--fps",type=int,default=24)
    p.add_argument("--seconds",type=int,default=8)
    args=p.parse_args()
    if not sys.stdin.isatty() or input("관리자 승인 ["+APPROVAL+"]: ").strip()!=APPROVAL:
        raise SystemExit("Administrator confirmation required")
    if not args.image.is_file():raise SystemExit("Image missing")
    if not (0.1<=args.center_x<=0.9 and 0.1<=args.center_y<=0.9 and 0.04<=args.iris_radius<=0.35):
        raise SystemExit("Invalid iris coordinates")
    if not 1<=args.fps<=60 or not 1<=args.seconds<=30 or args.fps*args.seconds>900:
        raise SystemExit("Invalid duration")
    if args.frames_dir.exists() and any(args.frames_dir.iterdir()):
        raise SystemExit("Output directory not empty; refusing overwrite")
    with Image.open(args.image) as im:
        src=im.convert("RGB")
    w,h=src.size
    if max(w,h)>4096:raise SystemExit("Resize image below 4096 pixels")
    cx=int(w*args.center_x);cy=int(h*args.center_y)
    radius=int(min(w,h)*args.iris_radius)
    if radius<15:raise SystemExit("Iris too small")
    args.frames_dir.mkdir(parents=True,exist_ok=True)
    n=args.fps*args.seconds
    samples={}
    for i in range(n):
        f=render(src,i,n,cx,cy,radius,radius*0.36)
        f.save(args.frames_dir/f"{i+1:06d}.png")
        if i in (0,n//4,n//2,3*n//4,n-1):samples[i]=f
    first=samples[0]
    checks=[]
    for i,f in samples.items():
        if i==0:continue
        diff=ImageChops.difference(first,f)
        stat=ImageStat.Stat(diff)
        checks.append({"frame":i+1,"mean_absolute_rgb_difference":round(sum(stat.mean)/3,5),
                       "difference_bbox":diff.getbbox()})
    report={"input":str(args.image),"image_sha256":hashlib.sha256(args.image.read_bytes()).hexdigest(),
            "frames":n,"fps":args.fps,"seconds":args.seconds,
            "iris_center":[cx,cy],"iris_radius":radius,"checks":checks,
            "warning":"Numeric pixel changes do not prove natural eye motion; inspect playback."}
    (args.frames_dir/"motion-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    if max(x["mean_absolute_rgb_difference"] for x in checks)<0.005:
        raise SystemExit("Motion too small; check iris location and source image")
    print("Generated",n,"frames. Motion report:",args.frames_dir/"motion-report.json")
    print("Next: ffmpeg -framerate",args.fps,"-i",str(args.frames_dir/"%06d.png"),
          "-c:v libx264 -pix_fmt yuv420p -crf 19 -movflags +faststart arkaon-eye-v3.mp4")

if __name__=="__main__":main()
