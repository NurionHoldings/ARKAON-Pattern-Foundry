"""Render original, silent service motion illustrations (requires Pillow and ffmpeg)."""
from pathlib import Path
import math
import subprocess
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assets/service-clips'
OUT.mkdir(exist_ok=True)
FONT=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',13)
SLUGS=['logo-card','ai-video','site-builder','personal-page','co-create','publish','account','admin','self-heal']
LABELS=['BRAND STUDIO','MOTION STUDIO','WEB BUILDER','PERSONAL SPACE','CO-CREATION','PUBLISH','MY ACCOUNT','CONTROL CENTER','EVOLUTION']
COLORS=['#ead5ab','#dfc9e5','#badbd1','#c8d9ef','#d1cbed','#cbdba9','#edcbb9','#c4d2ce','#e5c6cf']
for k,slug in enumerate(SLUGS):
    pipe=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','320x180','-r','12','-i','-','-an','-c:v','libx264','-crf','27','-pix_fmt','yuv420p','-movflags','+faststart',str(OUT/f'{slug}.mp4')],stdin=subprocess.PIPE)
    for frame in range(48):
        t=frame/48*math.tau
        im=Image.new('RGB',(320,180),COLORS[k]);d=ImageDraw.Draw(im)
        ink='#214b46'; white='#fffdf6'
        def box(x,y,w,h,fill=white):d.rounded_rectangle((x,y,x+w,y+h),radius=7,fill=fill)
        def line(x,y,w):d.rounded_rectangle((x,y,x+w,y+4),radius=2,fill=ink)
        if k==0:
            box(30,32,112,100,ink);d.regular_polygon((86,80,27),6,rotation=frame*7.5,fill=COLORS[k]);box(158,58,132,76);line(173,80,65);line(173,96,95);line(173,109,48)
        elif k==1:
            box(36,28,248,111,ink);d.polygon([(142,52),(142,108),(187,80)],fill=white)
            for j in range(18):
                h=8+18*(1+math.sin(t+j*.6));d.rectangle((51+j*12,137-h,57+j*12,137),fill=COLORS[k])
        elif k in (2,3):
            box(35,22,250,123);box(35,22,250,20,ink)
            if k==2:
                box(48,53,92,73,COLORS[k]);line(155,58,100);line(155,75,77);box(155,96,75+int(8*math.sin(t)),21,ink)
            else:
                x=160+int(5*math.sin(t));d.ellipse((x-21,48,x+21,90),fill=ink);line(119,101,82);box(91,117,138,15,COLORS[k])
        elif k==4:
            for j,(x,y) in enumerate([(64,52),(249,52),(155,120)]):
                d.line((x,y,160,74),fill=ink,width=2);r=16+int(3*math.sin(t+j*2));d.ellipse((x-r,y-r,x+r,y+r),fill=white)
            box(125,48,70,44,ink);d.text((139,60),'AI',font=FONT,fill=white)
        elif k==5:
            box(57,62,206,75);d.line((160,103,160,31),fill=ink,width=6);d.line((138,52,160,30,182,52),fill=ink,width=6)
            x=73+int((1+math.sin(t))*76);box(73,116,x-72,7,ink)
        elif k==6:
            box(40,31,110,108);d.ellipse((77,46,113,82),fill=ink);line(60,95,70);line(69,111,52);box(167,66,119,68,ink);box(177,80,99,9,COLORS[k]);d.ellipse((252,108,266,122),fill=white)
        elif k==7:
            for j in range(3):
                box(35+j*85,30,78,105);h=int(26+15*math.sin(t+j));box(54+j*85,117-h,14,h,ink);line(46+j*85,42,53)
        else:
            box(57,30,206,102);d.line((78,108,118,86,154,98,190,67,238,52),fill=ink,width=4)
            x=78+int((1+math.sin(t))*80);d.ellipse((x-6,65,x+6,77),fill=ink);line(78,118,160)
        d.text((15,157),LABELS[k],font=FONT,fill=ink)
        if frame==0:im.save(OUT/f'{slug}.png')
        pipe.stdin.write(im.tobytes())
    pipe.stdin.close()
    if pipe.wait():raise RuntimeError(slug)
