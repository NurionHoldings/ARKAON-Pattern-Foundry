"""Vectorize the ASIA HOLDINGS A-symbol into an SVG candidate for Blender extrusion (PR-B).

Two sources are compared against the operator reference poster:
- the STEP6 trial alpha mask (auto contour), and
- a manual control-point trace (``config/a_symbol_trace.v1.json``).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

DEFAULT_TRACE = Path(__file__).resolve().parent / "config" / "a_symbol_trace.v1.json"
COMPARE_CROP = (380, 1180, 80, 700)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _imread(path: Path, flags: int) -> np.ndarray:
    """cv2.imread cannot open non-ASCII Windows paths; decode from bytes instead."""
    img = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), flags)
    if img is None:
        raise ValueError(f"unreadable image: {path.name}")
    return img


def _imwrite(path: Path, img: np.ndarray) -> None:
    ok, buf = cv2.imencode(path.suffix, img)
    if not ok:
        raise ValueError(f"encode failed: {path.name}")
    path.write_bytes(buf.tobytes())


def trace_mask(mask_path: Path, *, epsilon_px: float = 1.5, open_px: int = 5) -> tuple[list[np.ndarray], tuple[int, int]]:
    rgba = _imread(mask_path, cv2.IMREAD_UNCHANGED)
    alpha = rgba[..., 3] if rgba.ndim == 3 and rgba.shape[2] == 4 else cv2.cvtColor(rgba, cv2.COLOR_BGR2GRAY)
    binary = (alpha > 127).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (open_px, open_px))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    min_area = 0.01 * binary.shape[0] * binary.shape[1]
    polys = [cv2.approxPolyDP(c, epsilon_px, True) for c in contours if cv2.contourArea(c) >= min_area]
    h, w = binary.shape
    return polys, (w, h)


def load_trace(trace_path: Path) -> tuple[dict[str, np.ndarray], tuple[int, int]]:
    data = json.loads(trace_path.read_text(encoding="utf-8"))
    pieces = {name: np.array(pts, np.int32).reshape(-1, 1, 2) for name, pts in data["pieces"].items()}
    w, h = data["canvas_px"]
    return pieces, (w, h)


def polygons_to_svg(pieces: dict[str, np.ndarray], size: tuple[int, int]) -> str:
    w, h = size
    paths = []
    for name, poly in pieces.items():
        pts = poly.reshape(-1, 2)
        d = "M " + " L ".join(f"{x} {y}" for x, y in pts) + " Z"
        paths.append(f'  <path id="{name}" d="{d}" fill="#000000"/>')
    body = "\n".join(paths)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'
        f"{body}\n</svg>\n"
    )


def _overlay(ref: np.ndarray, polys: list[np.ndarray], color: tuple[int, int, int]) -> np.ndarray:
    out = ref.copy()
    fill = out.copy()
    cv2.fillPoly(fill, [p.reshape(-1, 2) for p in polys], color)
    out = cv2.addWeighted(fill, 0.4, out, 0.6, 0)
    for poly in polys:
        cv2.polylines(out, [poly.reshape(-1, 2)], True, (0, 255, 255), 2, cv2.LINE_AA)
    return out


def _label(img: np.ndarray, text: str) -> np.ndarray:
    out = img.copy()
    cv2.rectangle(out, (0, 0), (out.shape[1], 34), (0, 0, 0), -1)
    cv2.putText(out, text, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return out


def comparison_sheet(ref: np.ndarray, mask_polys: list[np.ndarray], trace_polys: list[np.ndarray]) -> np.ndarray:
    x0, x1, y0, y1 = COMPARE_CROP
    panels = [
        _label(ref[y0:y1, x0:x1], "1. reference (operator)"),
        _label(_overlay(ref, mask_polys, (255, 80, 255))[y0:y1, x0:x1], "2. STEP6 trial mask"),
        _label(_overlay(ref, trace_polys, (80, 255, 80))[y0:y1, x0:x1], "3. agent trace (candidate)"),
    ]
    gap = np.full((y1 - y0, 10, 3), 255, np.uint8)
    return np.hstack([panels[0], gap, panels[1], gap, panels[2]])


def silhouette_preview(pieces: dict[str, np.ndarray], size: tuple[int, int]) -> np.ndarray:
    w, h = size
    canvas = np.full((h, w, 3), 255, np.uint8)
    cv2.fillPoly(canvas, [p.reshape(-1, 2) for p in pieces.values()], (60, 30, 10))
    x0, x1, y0, y1 = COMPARE_CROP
    return canvas[y0:y1, x0:x1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Vectorize ASIA A-symbol (PR-B candidate)")
    parser.add_argument("--mask", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ref = _imread(args.reference, cv2.IMREAD_COLOR)
    mask_polys, _ = trace_mask(args.mask)
    pieces, size = load_trace(args.trace)

    svg_path = args.out_dir / "asia_a_symbol.candidate.svg"
    svg_path.write_text(polygons_to_svg(pieces, size), encoding="utf-8")
    compare_path = args.out_dir / "asia_a_symbol.compare.png"
    _imwrite(compare_path, comparison_sheet(ref, mask_polys, list(pieces.values())))
    silhouette_path = args.out_dir / "asia_a_symbol.silhouette.png"
    _imwrite(silhouette_path, silhouette_preview(pieces, size))

    summary = {
        "schema": "apf.asia-cinema-symbol-vector-candidate/v1",
        "status": "generated_by_agent",
        "source_mask": {"path_ref": f"<operator-local:{args.mask.name}>", "sha256": _sha256(args.mask)},
        "reference": {"path_ref": f"<operator-local:{args.reference.name}>", "sha256": _sha256(args.reference)},
        "trace": {"file": args.trace.name, "sha256": _sha256(args.trace)},
        "canvas_px": list(size),
        "pieces": {name: len(p) for name, p in pieces.items()},
        "outputs": {
            svg_path.name: _sha256(svg_path),
            compare_path.name: _sha256(compare_path),
            silhouette_path.name: _sha256(silhouette_path),
        },
    }
    (args.out_dir / "asia_a_symbol.candidate.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
