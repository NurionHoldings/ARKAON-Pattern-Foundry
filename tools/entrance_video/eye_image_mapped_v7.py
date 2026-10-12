#!/usr/bin/env python3
"""ARKAON V7: artwork-specific eyelid and chip lighting over moving-eye frames.
Coordinate reference: supplied 1536x1024 ARKAON poster. No automatic segmentation.
"""
import argparse, math, json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageStat
APPROVAL="ARKAON V7 IMAGE MAPPED APPROVED"
W,H=1536,1024
# Traced approximate highlights from the user-supplied poster, in source pixels.
UPPER=[(112,326),(230,332),(340,292),(460,207),(570,149),(690,117),(782,106),(888,119),(994,163),(1110,230),(1240,314),(1350,369)]
LOWER=[(115,345),(242,393),(367,457),(487,512),(610,550),(735,566),(859,560),(982,531),(1110,478),(1235,418),(1343,378)]
# Actual visible components; positions manually read from image, not fabricated radial lines.
CHIPS=[(432,352,32,28),(476,338,25,27),(522,330,42,53),(562,283,18,36),
       (960,366,24,31),(1014,332,24,25),(1100,376,73,79),(1182,369,27,25)]
TRACES=[
 [(340,353),(415,354),(432,352)],[(475,390),(520,391),(540,413)],
 [(960,365),(998,356),(1038,362)],[(1172,375),(1238,373),(1315,380)],
 [(1012,428),(1075,452),(1130,452)]]
def clamp(v):return max(0,min(1,v))
def ease(v):
 v=clamp(v);return v*v*(3-2*v)
def scaled(p,sx,sy):return (round(p[0]*sx),round(p[1]*sy))
def glow_layer(size,lines,boxes,t,intensity,sx,sy):
 w,h=size
 bright=Image.new("RGBA",size,(0,0,0,0));d=ImageDraw.Draw(bright,"RGBA")
 # Eyelid color transition blue -> violet -> warm white, upper and lower delayed.
 colors=[(45,181,255),(165,111,247),(255,221,172)]
 phase=t*2
 lo=min(1,int(phase));f=clamp(phase-lo)
 col=tuple(round(colors[lo][k]*(1-f)+colors[lo+1][k]*f) for k in range(3))
 for j,path in enumerate(lines):
  on=ease((t-(.13+j*.10))/.20)
  if on:
   points=[scaled(p,sx,sy) for p in path]
   d.line(points,fill=(*col,round(125*intensity*on)),width=max(2,round(7*sy)),joint="curve")
 # Circuit components light up individually, preserving their original shapes.
 for j,(x,y,bw,bh) in enumerate(boxes):
  on=ease((t-(.28+j*.065))/.14)
  if not on:continue
  x0,y0=scaled((x-bw/2,y-bh/2),sx,sy)
  x1,y1=scaled((x+bw/2,y+bh/2),sx,sy)
  chipcolor=(62,206,255) if j%2==0 else (250,188,102)
  d.rounded_rectangle((x0,y0,x1,y1),radius=max(1,round(3*sx)),outline=(*chipcolor,round(160*intensity*on)),width=max(2,round(3*sx)))
 for j,path in enumerate(TRACES):
  on=ease((t-(.40+j*.08))/.15)
  if on:
   d.line([scaled(p,sx,sy) for p in path],fill=(72,202,255,round(120*intensity*on)),width=max(1,round(2*sx)))
 blur=bright.filter(ImageFilter.GaussianBlur(max(2,round(12*sy))))
 blur.putalpha(blur.getchannel("A").point(lambda a:round(a*.55)))
 return bright,blur
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--frames-dir",type=Path,required=True,help="V5 moving-iris PNG frames")
 p.add_argument("--output-dir",type=Path,required=True)
 p.add_argument("--intensity",type=float,default=.75)
 args=p.parse_args()
 if not sys.stdin.isatty() or input("Approval ["+APPROVAL+"]: ").strip()!=APPROVAL:raise SystemExit("Approval required")
 if not 0<=args.intensity<=1:raise SystemExit("Intensity must be 0..1")
 if args.frames_dir.resolve()==args.output_dir.resolve():raise SystemExit("Input and output must differ")
 paths=sorted(args.frames_dir.glob("*.png"))
 if not 2<=len(paths)<=900:raise SystemExit("Expected 2..900 PNG frames")
 if args.output_dir.exists() and any(args.output_dir.iterdir()):raise SystemExit("Output must be empty")
 with Image.open(paths[0]) as im:w,h=im.size
 if abs(w/h-W/H)>.03:raise SystemExit("Image aspect ratio differs from mapped poster; refusing misaligned overlay")
 if max(w,h)>4096:raise SystemExit("Image too large")
 sx,sy=w/W,h/H
 args.output_dir.mkdir(parents=True,exist_ok=True)
 diffs=[]
 for i,path in enumerate(paths):
  with Image.open(path) as im:
   if im.size!=(w,h):raise SystemExit("Inconsistent frame dimensions")
   base=im.convert("RGBA")
  bright,bloom=glow_layer((w,h),[UPPER,LOWER],CHIPS,i/max(1,len(paths)-1),args.intensity,sx,sy)
  out=Image.alpha_composite(Image.alpha_composite(base,bloom),bright).convert("RGB")
  out.save(args.output_dir/f"{i+1:06d}.png")
  if i in (len(paths)//4,len(paths)//2,3*len(paths)//4):
   diff=ImageChops.difference(base.convert("RGB"),out)
   diffs.append(round(sum(ImageStat.Stat(diff).mean)/3,5))
 report={"source_reference":[W,H],"frames":len(paths),"eyelid_paths":2,"chip_regions":len(CHIPS),"trace_paths":len(TRACES),
         "sample_mean_pixel_changes":diffs,"note":"Manually estimated region geometry from provided image; verify alignment. No automatic segmentation."}
 (args.output_dir/"v7-report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
 print("Rendered",len(paths),"frames:",args.output_dir)
if __name__=="__main__":main()
