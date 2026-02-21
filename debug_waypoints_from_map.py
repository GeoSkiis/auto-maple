"""
Investigate why "no waypoints (no platforms detected on minimap)" appears.

Run from project root:
  python debug_waypoints_from_map.py
  python debug_waypoints_from_map.py assets/minimaps/Map_Breathtaking_Cave_1.png

Saves to project root:
  debug_waypoints_loaded.png   - image as used for detection (transparent -> black)
  debug_waypoints_binary.png   - after threshold (white = platform, black = background)
  debug_waypoints_eroded.png   - after erosion (small gaps removed)
  debug_waypoints_platforms.png - detected platform rectangles (green = kept, red = rejected)
Prints: image shape, component counts, and why components were rejected (area / aspect ratio).
"""
import os
import sys
import cv2
import numpy as np

# Project root
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from src.map.waypoints_from_map import (
    load_map_image_for_match,
    waypoints_from_map_path,
    BG_THRESHOLD,
    ERODE_SIZE,
    MIN_PLATFORM_AREA,
    MIN_ASPECT_RATIO,
)


def main():
    if len(sys.argv) >= 2:
        map_path = sys.argv[1]
    else:
        minimaps_dir = os.path.join(ROOT, "assets", "minimaps")
        if not os.path.isdir(minimaps_dir):
            print(f"No path given and {minimaps_dir} not found.")
            print("Usage: python debug_waypoints_from_map.py [path/to/minimap.png]")
            return
        pngs = [f for f in os.listdir(minimaps_dir) if f.lower().endswith(".png")]
        if not pngs:
            print(f"No PNGs in {minimaps_dir}. Usage: python debug_waypoints_from_map.py path/to/minimap.png")
            return
        map_path = os.path.join(minimaps_dir, sorted(pngs)[0])
        print(f"No path given, using: {map_path}")

    if not os.path.isfile(map_path):
        print(f"File not found: {map_path}")
        return

    # Load same way as waypoints_from_map_path (composite transparent -> black)
    img = load_map_image_for_match(map_path)
    if img is None:
        img = cv2.imread(map_path)
    if img is None:
        print("Failed to load image.")
        return
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    cv2.imwrite(os.path.join(ROOT, "debug_waypoints_loaded.png"), img)
    print(f"Saved debug_waypoints_loaded.png  shape={img.shape}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, BG_THRESHOLD, 255, cv2.THRESH_BINARY)
    cv2.imwrite(os.path.join(ROOT, "debug_waypoints_binary.png"), binary)
    print(f"Saved debug_waypoints_binary.png  (threshold={BG_THRESHOLD}: pixel > {BG_THRESHOLD} -> white)")

    kernel = np.ones((ERODE_SIZE, ERODE_SIZE), np.uint8)
    eroded = cv2.erode(binary, kernel)
    cv2.imwrite(os.path.join(ROOT, "debug_waypoints_eroded.png"), eroded)
    print(f"Saved debug_waypoints_eroded.png  (erode kernel={ERODE_SIZE}x{ERODE_SIZE})")

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(eroded)
    h_img, w_img = gray.shape[:2]

    # Classify each component
    passed_area = 0
    passed_aspect = 0
    valid_platforms = []
    reject_reasons = []

    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        width = stats[i, cv2.CC_STAT_WIDTH]
        height = stats[i, cv2.CC_STAT_HEIGHT]
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        aspect_ratio = width / height if height > 0 else 0

        if area < MIN_PLATFORM_AREA:
            reject_reasons.append(f"  label {i}: area={area} < MIN_PLATFORM_AREA={MIN_PLATFORM_AREA}")
            continue
        passed_area += 1

        if aspect_ratio < MIN_ASPECT_RATIO:
            reject_reasons.append(
                f"  label {i}: aspect_ratio={aspect_ratio:.2f} (w={width} h={height}) < MIN_ASPECT_RATIO={MIN_ASPECT_RATIO}"
            )
            continue
        passed_aspect += 1
        cx, cy = centroids[i]
        valid_platforms.append({"x": x, "y": y, "width": width, "height": height, "cx": cx, "cy": cy})

    print(f"\nConstants: BG_THRESHOLD={BG_THRESHOLD}  MIN_PLATFORM_AREA={MIN_PLATFORM_AREA}  MIN_ASPECT_RATIO={MIN_ASPECT_RATIO}")
    print(f"Connected components (excluding background): {num_labels - 1}")
    print(f"After area filter (area >= {MIN_PLATFORM_AREA}): {passed_area}")
    print(f"After aspect ratio filter (width/height >= {MIN_ASPECT_RATIO}): {passed_aspect}")
    print(f"Valid platforms: {len(valid_platforms)}")

    if reject_reasons:
        print("\nRejected components (first 20):")
        for r in reject_reasons[:20]:
            print(r)
        if len(reject_reasons) > 20:
            print(f"  ... and {len(reject_reasons) - 20} more")

    # Draw on copy: green = valid platform, red = rejected but passed area
    vis = cv2.cvtColor(eroded, cv2.COLOR_GRAY2BGR)
    for i in range(1, num_labels):
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        area = stats[i, cv2.CC_STAT_AREA]
        ar = w / h if h > 0 else 0
        if area >= MIN_PLATFORM_AREA and ar >= MIN_ASPECT_RATIO:
            color = (0, 255, 0)  # green = kept
        else:
            color = (0, 0, 255)  # red = rejected
        cv2.rectangle(vis, (x, y), (x + w, y + h), color, 1)
    cv2.imwrite(os.path.join(ROOT, "debug_waypoints_platforms.png"), vis)
    print("\nSaved debug_waypoints_platforms.png  (green=kept, red=rejected)")

    # Compare with actual waypoints_from_map_path
    waypoints = waypoints_from_map_path(map_path)
    print(f"\nwaypoints_from_map_path returned {len(waypoints)} waypoints.")
    if not waypoints and valid_platforms:
        print("(Pipeline here found platforms but waypoints_from_map_path may use *_waypoints.json or *_crop.json.)")
    if len(valid_platforms) == 0:
        print("\nTip: Detection expects dark background and lighter platforms (pixel value > BG_THRESHOLD).")
        print("  - Check debug_waypoints_binary.png: platforms should be white, background black.")
        print("  - If your map has light background / dark platforms, we'd need an inverted threshold.")
        print("  - Relaxing MIN_ASPECT_RATIO or MIN_PLATFORM_AREA in src/map/waypoints_from_map.py may help.")


if __name__ == "__main__":
    main()
