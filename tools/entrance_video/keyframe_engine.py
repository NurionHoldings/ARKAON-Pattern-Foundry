#!/usr/bin/env python3
"""Approved local keyframe storyboard renderer. No AI generation or GPU rental."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--frames-dir",type=Path,required=True)
    p.add_argument("--output",type=Path,default=Path("arkaon-keyframes.mp4"))
    p.add_argument("--fps",type=int,default=24)
    p.add_argument("--seconds",type=int,default=8)
    args=p.parse_args()
    if not sys.stdin.isatty() or input("관리자 승인 [ARKAON KEYFRAMES APPROVED]: ").strip()!="ARKAON KEYFRAMES APPROVED":
        raise SystemExit("Approval denied")
    if not shutil.which("ffmpeg"): raise SystemExit("FFmpeg missing")
    if args.output.exists(): raise SystemExit("Output exists; refusing overwrite")
    if args.fps<1 or args.fps>60 or args.seconds<1 or args.seconds>60: raise SystemExit("Invalid duration")
    frames=sorted(args.frames_dir.glob("*.png"))
    if len(frames)<2: raise SystemExit("At least two numbered PNG keyframes required")
    # Crossfade each storyboard frame with the next. No zoom or camera movement.
    # Frames should be prepared with consistent composition and 16:9 aspect ratio.
    total=args.fps*args.seconds
    n=len(frames)
    # Each keyframe holds a base duration with a 0.5s overlap.
    overlap=0.5
    segment=(args.seconds+(n-1)*overlap)/n
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-y"]
    for frame in frames: cmd+=["-loop","1","-framerate",str(args.fps),"-t",str(segment),"-i",str(frame)]
    filters=[]
    for i in range(n):
        filters.append(f"[{i}:v]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1,format=yuv420p,settb=AVTB[v{i}]")
    prev="v0"
    for i in range(1,n):
        dest=f"x{i}"
        offset=i*(segment-overlap)
        filters.append(f"[{prev}][v{i}]xfade=transition=fade:duration={overlap}:offset={offset:.6f}[{dest}]")
        prev=dest
    filters.append(f"[{prev}]trim=duration={args.seconds},setpts=PTS-STARTPTS[out]")
    cmd+=["-filter_complex",";".join(filters),"-map","[out]","-an","-c:v","libx264","-crf","20","-preset","medium","-pix_fmt","yuv420p","-movflags","+faststart",str(args.output)]
    subprocess.run(cmd,check=True)
    print("Rendered",args.output,"from",len(frames),"keyframes")

if __name__=="__main__": main()
