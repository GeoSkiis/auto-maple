"""
Draw waypoints (x, y in 0-1) on a map image to verify positions.
Use this to check if points are shifted (e.g. 50px too low) and tune crop_* or regenerate.

Usage (from project root):
  python graph_waypoints.py assets/minimaps/Map_Rocky_Overlook_4.png
  python graph_waypoints.py assets/minimaps/Map_Rocky_Overlook_4.png --waypoints Map_Rocky_Overlook_4_waypoints.json
  python graph_waypoints.py assets/minimaps/Map_Rocky_Overlook_4.png --crop-top 50

Output: same path with _waypoints_drawn.png
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

# Allow importing from src when run from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.map.waypoints_from_map import waypoints_from_map_image, waypoints_from_map_path


def draw_waypoints_on_image(map_path, waypoints, crop_top=0, crop_bottom=0, crop_left=0, crop_right=0):
    """
    Draw circles at each (x, y) on the map. (x, y) are 0-1 relative to the *content* region
    after crop (same convention as waypoints_from_map). So we draw at:
      px = crop_left + x * (w - crop_left - crop_right)
      py = crop_top  + y * (h - crop_top - crop_bottom)
    If waypoints were computed with no crop, crop_* are 0 and we draw at (x*w, y*h).
    """
    img = cv2.imread(map_path)
    if img is None:
        print(f"Could not load {map_path}")
        return None
    h, w = img.shape[:2]
    w_content = w - crop_left - crop_right
    h_content = h - crop_top - crop_bottom
    if w_content <= 0 or h_content <= 0:
        w_content, h_content = w, h
        crop_left = crop_right = crop_top = crop_bottom = 0
    out = img.copy()
    radius = max(8, min(w, h) // 80)
    for i, wp in enumerate(waypoints):
        x_rel = wp["x"]
        y_rel = wp["y"]
        px = int(round(crop_left + x_rel * w_content))
        py = int(round(crop_top + y_rel * h_content))
        cv2.circle(out, (px, py), radius, (0, 0, 255), 2)
        cv2.putText(out, str(i), (px - 6, py + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    return out


def main():
    ap = argparse.ArgumentParser(description="Draw waypoints on a map image to verify (x,y).")
    ap.add_argument("map_path", help="Path to map PNG (e.g. assets/minimaps/Map_Rocky_Overlook_4.png)")
    ap.add_argument("--waypoints", "-w", help="Path to waypoints JSON (default: compute from map or use *_waypoints.json)")
    ap.add_argument("--crop-top", type=int, default=0, help="Crop this many pixels from top when computing waypoints")
    ap.add_argument("--crop-bottom", type=int, default=0)
    ap.add_argument("--crop-left", type=int, default=0)
    ap.add_argument("--crop-right", type=int, default=0)
    ap.add_argument("--output", "-o", help="Output image path (default: <map_base>_waypoints_drawn.png)")
    args = ap.parse_args()

    if not os.path.exists(args.map_path):
        print(f"File not found: {args.map_path}")
        return 1

    crop_top = crop_bottom = crop_left = crop_right = 0
    if args.waypoints and os.path.exists(args.waypoints):
        with open(args.waypoints, "r") as f:
            waypoints = json.load(f)
        print(f"Loaded {len(waypoints)} waypoints from {args.waypoints} (drawn at x*w, y*h)")
    else:
        # Compute waypoints (optionally with crop via _crop.json or CLI)
        base, _ = os.path.splitext(args.map_path)
        crop_path = base + "_crop.json"
        crop = {}
        if os.path.exists(crop_path):
            with open(crop_path, "r") as f:
                crop = json.load(f)
        crop_top = crop.get("crop_top", args.crop_top)
        crop_bottom = crop.get("crop_bottom", args.crop_bottom)
        crop_left = crop.get("crop_left", args.crop_left)
        crop_right = crop.get("crop_right", args.crop_right)
        img = cv2.imread(args.map_path)
        waypoints = waypoints_from_map_image(
            img,
            crop_top=crop_top,
            crop_bottom=crop_bottom,
            crop_left=crop_left,
            crop_right=crop_right,
        )
        print(f"Computed {len(waypoints)} waypoints (crop: t={crop_top} b={crop_bottom} l={crop_left} r={crop_right})")

    out_img = draw_waypoints_on_image(
        args.map_path,
        waypoints,
        crop_top=crop_top,
        crop_bottom=crop_bottom,
        crop_left=crop_left,
        crop_right=crop_right,
    )
    if out_img is None:
        return 1

    if args.output:
        out_path = args.output
    else:
        base, _ = os.path.splitext(args.map_path)
        out_path = base + "_waypoints_drawn.png"
    cv2.imwrite(out_path, out_img)
    print(f"Saved {out_path} — open to verify waypoint positions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
