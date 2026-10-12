#!/usr/bin/env python3
"""ARKAON v5: image-aware iris motion and explicitly mapped circuit illumination.
Pillow only, offline, interactive approval. No model training or auto segmentation.
"""
import argparse
import json
import math
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageStat
from eye_pixel_motion_v3 import render as warp_eye

APPROVAL="ARKAON V5 LOCAL RENDER APPROVED"
def ease(x):
    x=max(0.,min(1.,x))
    return x*x*(3-2*x)
def load_map(path):
    if path is None:return []
    data=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict) or not isinstance(data.get("paths"),list) or len(data["paths"])>64:
        raise ValueError("Expected {paths:[...]}, max 64")
    paths=[]
    for path in data["paths"]:
        if not isinstance(path,list) or not 2<=len(path)<=80:raise ValueError("Each path needs 2..80 points")
        points=[]
        for point in path:
            if not isinstance(point,list) or len(point)!=2 or any(type(v) not in (float,int) or not 0<=v<=1 for v in point):
                raise ValueError("Coordinates must be normalized [x,y] numbers in 0..1")
            points.append(tuple(point))
        paths.append(points)
    return paths

def circuit_layer(size,paths,t,opacity):
    w,h=size
    layer=Image.new("RGBA",size,(0,0,0,0))
    draw=ImageDraw.Draw(layer,"RGBA")
    for index,path in enumerate(paths):
        start=.28+.48*index/max(1,len(paths))
        progress=ease((t-start)/.24)
        if progress<=0:continue
        pts=[(round(x*(w-1)),round(y*(h-1))) for x,y in path]
        # Draw progressively along the actual user-traced polyline.
        distances=[math.dist(a,b) for a,b in zip(pts,pts[1:])]
        total=sum(distances)
        if total<=0:continue
        left=total*progress
        lit=[pts[0]]
        for j,length in enumerate(distances):
            if left>=length:
                lit.append(pts[j+1]);left-=length
            else:
                if length>0:
                    f=left/length
                    lit.append((round(pts[j][0]+f*(pts[j+1][0]-pts[j][0])),
                                round(pts[j][1]+f*(pts[j+1][1]-pts[j][1]))))
                break
        if len(lit)>1:
            draw.line(lit,fill=(78,206,249,opacity),width=max(2,round(min(w,h)*.003)),joint="curve")
            x,y=lit[-1];r=max(2,round(min(w,h)*.004))
            draw.ellipse((x-r,y-r,x+r,y+r),fill=(255,199,109,opacity))
    return layer

def render_v5(src,index,count,cx,cy,radius,paths,opacity):
    w,h=src.size
    t=index/max(1,count-1)
    base=warp_eye(src,index,count,cx,cy,radius,radius*.36).convert("RGBA")
    # Restrained iris reflection; preserves underlying original texture.
    iris=Image.new("RGBA",(w,h),(0,0,0,0))
    d=ImageDraw.Draw(iris,"RGBA")
    strength=ease((t-.10)/.25)
    a=int(35*strength*(.85+.15*math.sin(2*math.pi*2*t)))
    r=radius*.92
    d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=(115,220,255,a),width=max(2,round(radius*.055)))
    base=Image.alpha_composite(base,iris)
    if paths:
        circuit=circuit_layer((w,h),paths,t,opacity)
        bloom=circuit.filter(ImageFilter.GaussianBlur(max(2,round(radius*.07))))
        bloom.putalpha(bloom.getchannel("A").point(lambda a:round(a*.35)))
        base=Image.alpha_composite(base,bloom)
        base=Image.alpha_composite(base,circuit)
    return base.convert("RGB")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--image",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--circuit-map",type=Path,help="Reviewed normalized circuit paths JSON")
    p.add_argument("--center-x",type=float,default=.5)
    p.add_argument("--center-y",type=float,default=.5)
    p.add_argument("--iris-radius",type=float,default=.12)
    p.add_argument("--circuit-opacity",type=int,default=110)
    p.add_argument("--fps",type=int,default=24)
    p.add_argument("--seconds",type=int,default=8)
    args=p.parse_args()
    if not sys.stdin.isatty() or input("관리자 승인 ["+APPROVAL+"]: ").strip()!=APPROVAL:
        raise SystemExit("Approval required")
    if not args.image.is_file():raise SystemExit("Source image missing")
    if args.circuit_map is not None and not args.circuit_map.is_file():raise SystemExit("Circuit map missing")
    if not (.1<=args.center_x<=.9 and .1<=args.center_y<=.9 and .04<=args.iris_radius<=.35):
        raise SystemExit("Invalid iris geometry")
    if not 0<=args.circuit_opacity<=255 or not 1<=args.fps<=60 or not 1<=args.seconds<=30 or args.fps*args.seconds>900:
        raise SystemExit("Invalid render parameters")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):raise SystemExit("Output directory must be empty")
    paths=load_map(args.circuit_map)
    with Image.open(args.image) as image:src=image.convert("RGB")
    w,h=src.size
    if max(w,h)>4096:raise SystemExit("Source too large")
    cx=round(w*args.center_x);cy=round(h*args.center_y);r=round(min(w,h)*args.iris_radius)
    if r<15:raise SystemExit("Iris radius too small")
    count=args.fps*args.seconds
    args.output_dir.mkdir(parents=True,exist_ok=True)
    samples={}
    for i in range(count):
        frame=render_v5(src,i,count,cx,cy,r,paths,args.circuit_opacity)
        frame.save(args.output_dir/f"{i+1:06d}.png")
        if i in (0,count//4,count//2,3*count//4,count-1):samples[i]=frame
    first=samples[0]
    changes={}
    for i,img in samples.items():
        if i==0:continue
        diff=ImageChops.difference(first,img)
        changes[str(i+1)]=round(sum(ImageStat.Stat(diff).mean)/3,5)
    report={"frames":count,"fps":args.fps,"duration_seconds":args.seconds,
            "iris_center":[cx,cy],"iris_radius":r,"circuit_paths":len(paths),
            "frame_mean_absolute_difference":changes,
            "limitations":["No automatic iris or circuit detection","Pixel warping is not neural image synthesis",
                           "Manual alignment and visual review required"]}
    (args.output_dir/"quality-report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    if max(changes.values(),default=0)<.005:raise SystemExit("Insufficient visible pixel changes; inspect alignment")
    print(f"Created {count} frames; {len(paths)} mapped circuit paths. QA: {args.output_dir/'quality-report.json'}")
    if not paths:print("WARNING: no circuit map supplied; circuit lighting intentionally disabled.")
if __name__=="__main__":main()
