#!/usr/bin/env python3
"""Explicitly reviewed, offline knowledge intake. Never executes external content."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_HOSTS={"docs.opencv.org","ffmpeg.org","pillow.readthedocs.io","github.com","arxiv.org"}
ALLOWED_TOPICS={"animation","optical-flow","frame-interpolation","image-compositing","rendering"}

def validate(entry):
    if not isinstance(entry,dict): raise ValueError("Expected JSON object")
    if set(entry)-{"title","source_url","topic","notes","approved_by"}: raise ValueError("Unknown fields")
    for key in ("title","source_url","topic","notes","approved_by"):
        if not isinstance(entry.get(key),str) or not entry[key].strip(): raise ValueError("Missing "+key)
    if len(entry["notes"])>4000 or len(entry["title"])>200: raise ValueError("Entry too long")
    u=urlparse(entry["source_url"])
    if u.scheme!="https" or u.hostname not in ALLOWED_HOSTS or u.username or u.password: raise ValueError("Unapproved source")
    if entry["topic"] not in ALLOWED_TOPICS: raise ValueError("Unapproved topic")
    return {k:entry[k] for k in ("title","source_url","topic","notes","approved_by")}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--output",type=Path,default=Path("knowledge/reviewed_entries.jsonl"))
    a=p.parse_args()
    if not a.input.is_file(): raise SystemExit("Input missing")
    if a.input.stat().st_size>100_000: raise SystemExit("Input too large")
    item=validate(json.loads(a.input.read_text(encoding="utf-8")))
    item["sha256"]=hashlib.sha256(json.dumps(item,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open("a",encoding="utf-8") as f: f.write(json.dumps(item,ensure_ascii=False)+"\n")
    print("Reviewed reference recorded; no code/model updated automatically")

if __name__=="__main__": main()
