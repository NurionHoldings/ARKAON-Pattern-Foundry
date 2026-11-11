"""The AI video service shows exactly the operator-approved ASIA HOLDINGS pilot MP4."""
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "assets" / "showcase" / "asia-holdings-cinema-16s.mp4"
POSTER = ROOT / "assets" / "showcase" / "asia-holdings-cinema-poster.jpg"
PAGE = ROOT / "services" / "ai-video.html"
APPROVED_VIDEO_SHA = "5b11327d1b5ac82e7a57b8f1b1f8d7e8f76b543f68425e9a69e1d6847ae7f00a"


def test_published_video_is_the_approved_pilot():
    assert sha256(VIDEO.read_bytes()).hexdigest() == APPROVED_VIDEO_SHA


def test_ai_video_page_embeds_showcase():
    html = PAGE.read_text(encoding="utf-8")
    assert 'src="/assets/showcase/asia-holdings-cinema-16s.mp4"' in html
    assert 'poster="/assets/showcase/asia-holdings-cinema-poster.jpg"' in html
    assert POSTER.is_file()
