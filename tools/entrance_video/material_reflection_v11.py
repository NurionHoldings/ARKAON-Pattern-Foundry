#!/usr/bin/env python3
"""ARKAON V11: material-specific moving reflection approximation for approved poster video.
No physical material inference; manually assigned regions and image-space light sweeps.
"""
import argparse
from pathlib import Path
import cv2
import numpy as np
from gradual_region_color_v10 import regions, REF

# OpenCV BGR, material presets: roughness, specular strength, tint.
MATERIALS={
 "polished_metal":(.10,.74,(175,220,255)),
 "glass_coating":(.34,.43,(255,226,190)),
 "semiconductor":(.28,.62,(255,198,108)),
 "copper_trace":(.18,.58,(104,220,255)),
 "lettering":(.24,.30,(190,227,255))
}
def classify(name):
 if name in ("housing","inner_ring"):return "polished_metal"
 if "lid" in name:return "glass_coating"
 if name.startswith("chip"):return "semiconductor"
 if "circuit" in name:return "copper_trace"
 return "lettering"

def reflect(frame,area,t,intensity,edge):
 h,w=frame.shape[:2]
 yy,xx=np.mgrid[:h,:w].astype(np.float32)
 x=xx/max(1,w-1);y=yy/max(1,h-1)
 # Smooth diagonal traveling light. Each material has different width and intensity.
 out=frame.astype(np.float32)
 luminance=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY).astype(np.float32)/255.
 # Fine structural features: local gradient, not physically recovered normals.
 gx=cv2.Sobel(luminance,cv2.CV_32F,1,0,ksize=3)
 gy=cv2.Sobel(luminance,cv2.CV_32F,0,1,ksize=3)
 gradient=np.sqrt(gx*gx+gy*gy)
 gradient=np.clip(gradient*2.8,0,1)
 for i,(name,m,offset,speed,_) in enumerate(area):
  material=classify(name)
  rough,spec,color=MATERIALS[material]
  # Moving band varies by region; a low-intensity fill prevents hard on/off.
  phase=(t*(.75+speed*.5)+offset*.5)%1.
  direction=1 if i%2==0 else -1
  coord=x*.72+direction*y*.28
  center=-.32+phase*1.65
  width=.018+rough*.22
  band=np.exp(-.5*((coord-center)/width)**2)
  # Edge-aware highlights, plus weak diffuse contribution on already bright material.
  reflectivity=(.25+.75*gradient)*(.30+.70*np.clip(luminance*1.35,0,1))
  contribution=(m*band*reflectivity*spec*intensity)[:,:,None]
  c=np.asarray(color,np.float32)[None,None,:]
  screen=255-(255-out)*(255-c)/255
  out=out*(1-contribution)+screen*contribution
 return np.clip(out,0,255).astype(np.uint8)

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--input",type=Path,required=True)
 p.add_argument("--output",type=Path,required=True)
 p.add_argument("--intensity",type=float,default=.8)
 args=p.parse_args()
 if not 0<=args.intensity<=1:raise SystemExit("intensity must be 0..1")
 if not args.input.is_file() or args.output.exists() or args.input.resolve()==args.output.resolve():
  raise SystemExit("Input must exist; output must not exist or overwrite input")
 cap=cv2.VideoCapture(str(args.input))
 if not cap.isOpened():raise SystemExit("Cannot open source MP4")
 w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
 fps=cap.get(cv2.CAP_PROP_FPS);n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
 if w<320 or h<200 or abs(w/h-REF[0]/REF[1])>.025 or fps<=0:
  cap.release();raise SystemExit("Expected approved 3:2 ARKAON poster video")
 writer=cv2.VideoWriter(str(args.output),cv2.VideoWriter_fourcc(*"mp4v"),fps,(w,h))
 if not writer.isOpened():cap.release();raise SystemExit("Could not open output encoder")
 mapped=regions((h,w));count=0
 try:
  while True:
   ok,frame=cap.read()
   if not ok:break
   writer.write(reflect(frame,mapped,count/max(1,n-1),args.intensity,None))
   count+=1
 finally:
  cap.release();writer.release()
 print(f"Rendered {count} frames with {len(mapped)} material-assigned reflection regions: {args.output}")
 print("NOTE: image-space lighting approximation, not measured material properties or 3D ray tracing.")
if __name__=="__main__":main()
