#!/usr/bin/env python3
"""ARKAON V10: gradual region-specific color changes over approved V9 MP4."""
import argparse, math
from pathlib import Path
import cv2
import numpy as np

REF=(1536,1024)
PALETTE=np.array([(42,190,255),(162,105,255),(255,185,95),(115,238,218)],np.float32)
def mask(shape,points,thick=8,blur=10,closed=False):
 h,w=shape;m=np.zeros((h,w),np.uint8)
 p=np.array([[round(x*w/REF[0]),round(y*h/REF[1])] for x,y in points],np.int32)
 cv2.polylines(m,[p],closed,255,max(1,round(thick*w/REF[0])),cv2.LINE_AA)
 return cv2.GaussianBlur(m,(0,0),max(1,blur*w/REF[0])).astype(np.float32)/255
def ellipse(shape,x,y,rx,ry):
 h,w=shape;m=np.zeros((h,w),np.uint8)
 cv2.ellipse(m,(round(x*w/REF[0]),round(y*h/REF[1])),(round(rx*w/REF[0]),round(ry*h/REF[1])),0,0,360,255,max(2,round(13*w/REF[0])),cv2.LINE_AA)
 return cv2.GaussianBlur(m,(0,0),max(1,10*w/REF[0])).astype(np.float32)/255
def box(shape,x0,y0,x1,y1):
 return mask(shape,[(x0,y0),(x1,y0),(x1,y1),(x0,y1)],6,9,True)
def regions(shape):
 out=[('housing',ellipse(shape,770,359,210,195),0,.55,.42),
      ('inner_ring',ellipse(shape,770,359,175,165),.25,.72,.31),
      ('upper_lid',mask(shape,[(115,325),(252,327),(390,265),(540,164),(700,111),(860,116),(1040,182),(1190,285),(1350,371)],12,11),.13,.55,.34),
      ('lower_lid',mask(shape,[(125,353),(290,426),(460,503),(650,556),(830,564),(1010,514),(1180,437),(1340,383)],12,11),.38,.62,.33)]
 chips=[(422,337,455,368),(463,324,493,358),(501,308,544,365),(553,265,575,306),(946,350,978,382),(999,315,1031,344),(1060,334,1139,416),(1168,352,1201,382)]
 for i,c in enumerate(chips):out.append(('chip_'+str(i+1),box(shape,*c),i*.115,.74,.40))
 out.extend([('left_circuit',mask(shape,[(289,355),(360,358),(421,354),(477,381),(535,413)],5,8),.17,.9,.40),
             ('right_circuit',mask(shape,[(962,370),(1020,353),(1097,377),(1176,372),(1297,382)],5,8),.61,.8,.42),
             ('wordmark',box(shape,215,638,1320,789),.72,.33,.105)])
 return out
def color(t,offset,speed):
 pos=((t*speed+offset)%1)*len(PALETTE);k=int(pos);f=pos-k;f=f*f*(3-2*f)
 return (PALETTE[k]*(1-f)+PALETTE[(k+1)%len(PALETTE)]*f)[::-1]
def apply(frame,regions,t,intensity):
 img=frame.astype(np.float32);material=np.clip((np.max(img,axis=2)/255-.13)/.55,0,1)**.7
 for _,m,offset,speed,strength in regions:
  c=color(t,offset,speed)
  alpha=(m*material*strength*intensity)[:,:,None]
  screen=255-(255-img)*(255-c[None,None,:])/255
  img=img*(1-alpha)+screen*alpha
 return np.uint8(np.clip(img,0,255))
def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--intensity',type=float,default=.9)
 a=p.parse_args()
 if not 0<=a.intensity<=1 or a.output.exists() or a.input.resolve()==a.output.resolve():raise SystemExit('Invalid intensity or output path')
 cap=cv2.VideoCapture(str(a.input))
 if not cap.isOpened():raise SystemExit('Cannot open source video')
 w=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));h=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT));fps=cap.get(cv2.CAP_PROP_FPS);n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
 if abs(w/h-1.5)>.025 or fps<=0:raise SystemExit('Only approved ARKAON poster aspect ratio is supported')
 out=cv2.VideoWriter(str(a.output),cv2.VideoWriter_fourcc(*'mp4v'),fps,(w,h))
 if not out.isOpened():raise SystemExit('Cannot open output')
 r=regions((h,w));i=0
 try:
  while True:
   ok,frame=cap.read()
   if not ok:break
   out.write(apply(frame,r,i/max(1,n-1),a.intensity));i+=1
 finally:cap.release();out.release()
 print('Rendered',i,'frames with',len(r),'independent color regions:',a.output)
if __name__=='__main__':main()
