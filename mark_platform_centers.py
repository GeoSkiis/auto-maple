"""
Mark the center of each platform on a map image (black background, platforms/ropes in front).
Uses thresholding + erosion to separate platforms from thin ropes, then finds each blob's center.
Optionally saves waypoints as relative (0-1) JSON for use as a bot path (see docs/SKILL_BASED_ROUTINE_DESIGN.md).

Run from project root:  python mark_platform_centers.py
"""
import cv2
import json
import numpy as np
import os

MAP_IMAGE = "Map_Laboratory_Behind_Locked_Door_3.png"
OUTPUT_IMAGE = "Map_Laboratory_Behind_Locked_Door_3_marked.png"
# Waypoints as relative 0-1 for routine loader (same base name as map)
WAYPOINTS_JSON = "Map_Laboratory_Behind_Locked_Door_3_waypoints.json"

# Pixels with value <= this are treated as background (black). Increased to catch darker platforms.
BG_THRESHOLD = 15
# Erode this much to break thin ropes from platforms (reduced to preserve platform detection)
ERODE_SIZE = 2
# Minimum area (pixels) to count as a platform (reduced to catch smaller platforms)
MIN_PLATFORM_AREA = 30
# Minimum aspect ratio (width/height) to be considered a platform
# Platforms are wide and flat, so width should be much greater than height
MIN_ASPECT_RATIO = 2.0
# Red dot radius and thickness
DOT_RADIUS = 12
DOT_THICKNESS = 3
# Pixels to shift the lowest 3 waypoints upward (same logic as src.map.waypoints_from_map)
PLATFORM_SHIFT_UP = 10


def main():
    if not os.path.exists(MAP_IMAGE):
        print(f"Put your map image at {MAP_IMAGE} and run again.")
        return

    img = cv2.imread(MAP_IMAGE)
    if img is None:
        print(f"Could not load {MAP_IMAGE}.")
        return
    # Handle PNG with alpha: ignore alpha for thresholding
    if img.shape[2] == 4:
        img = img[:, :, :3]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Non-black = platform or rope (anything brighter than BG_THRESHOLD)
    _, binary = cv2.threshold(gray, BG_THRESHOLD, 255, cv2.THRESH_BINARY)
    
    # Save intermediate images for debugging
    cv2.imwrite("debug_binary.png", binary)
    
    # Erode to break thin ropes so platforms become separate blobs
    kernel = np.ones((ERODE_SIZE, ERODE_SIZE), np.uint8)
    eroded = cv2.erode(binary, kernel)
    cv2.imwrite("debug_eroded.png", eroded)
    
    # Label connected components
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(eroded)
    
    # Debug: show how many blobs and their areas
    print(f"Found {num_labels - 1} blobs after erosion.\n")
    
    out = img.copy()
    count = 0
    rejected = 0
    waypoints = []
    h_img, w_img = gray.shape[:2]
    
    # First pass: collect all valid platforms
    valid_platforms = []
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        width = stats[i, cv2.CC_STAT_WIDTH]
        height = stats[i, cv2.CC_STAT_HEIGHT]
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        
        # Calculate aspect ratio (width/height)
        aspect_ratio = width / height if height > 0 else 0
        
        # Filter by area
        if area < MIN_PLATFORM_AREA:
            continue
            
        # Filter by aspect ratio - platforms should be wide and flat
        if aspect_ratio < MIN_ASPECT_RATIO:
            rejected += 1
            print(f"Rejected blob: area={area}, width={width}, height={height}, aspect_ratio={aspect_ratio:.2f} (too square/tall)")
            continue
        
        cx, cy = centroids[i]
        valid_platforms.append({
            'index': i,
            'cx': cx,
            'cy': cy,
            'x': x,
            'y': y,
            'width': width,
            'height': height,
            'area': area,
            'aspect_ratio': aspect_ratio
        })
    
    # Find the bottom-most platform (highest y-coordinate, since y increases downward)
    if valid_platforms:
        bottom_platform = max(valid_platforms, key=lambda p: p['cy'])
        bottom_platform_index = bottom_platform['index']
        print(f"Bottom platform identified at y={bottom_platform['cy']:.1f} with width={bottom_platform['width']}")
    else:
        bottom_platform_index = None
    
    # Second pass: build waypoints (unshifted), then shift only the lowest 3
    waypoints_raw = []
    for platform in valid_platforms:
        i = platform['index']
        cx = platform['cx']
        cy = platform['cy']
        x = platform['x']
        y = platform['y']
        width = platform['width']
        height = platform['height']
        area = platform['area']
        aspect_ratio = platform['aspect_ratio']
        
        if i == bottom_platform_index:
            positions = [0.25, 0.5, 0.75]
            for pos_fraction in positions:
                px = x + width * pos_fraction
                py = cy
                waypoints_raw.append({
                    "px": px, "py": py,
                    "area": area, "width": width, "height": height, "aspect_ratio": aspect_ratio,
                    "is_bottom_platform": True,
                    "position_fraction": pos_fraction
                })
        else:
            waypoints_raw.append({
                "px": cx, "py": cy,
                "area": area, "width": width, "height": height, "aspect_ratio": aspect_ratio,
                "is_bottom_platform": False,
                "position_fraction": None
            })
    
    # Only the lowest 3 waypoints (by y) get shifted up
    indices_to_shift = sorted(
        range(len(waypoints_raw)),
        key=lambda idx: waypoints_raw[idx]["py"],
        reverse=True
    )[:3]
    for idx in indices_to_shift:
        waypoints_raw[idx]["py"] -= PLATFORM_SHIFT_UP
    
    # Draw and build final waypoints list
    for w in waypoints_raw:
        px_int = int(round(w["px"]))
        py_int = int(round(w["py"]))
        cv2.circle(out, (px_int, py_int), DOT_RADIUS, (0, 0, 255), DOT_THICKNESS)
        count += 1
        wp = {
            "x": round(w["px"] / w_img, 4),
            "y": round(w["py"] / h_img, 4),
            "area": int(w["area"]),
            "width": int(w["width"]),
            "height": int(w["height"]),
            "aspect_ratio": round(w["aspect_ratio"], 2),
            "is_bottom_platform": w["is_bottom_platform"]
        }
        if w.get("position_fraction") is not None:
            wp["position_fraction"] = w["position_fraction"]
            print(f"Platform {count} (BOTTOM - {w['position_fraction']}): center=({px_int}, {py_int}), area={w['area']}, width={w['width']}, height={w['height']}, aspect_ratio={w['aspect_ratio']:.2f}")
        else:
            print(f"Platform {count}: center=({px_int}, {py_int}), area={w['area']}, width={w['width']}, height={w['height']}, aspect_ratio={w['aspect_ratio']:.2f}")
        waypoints.append(wp)
    
    cv2.imwrite(OUTPUT_IMAGE, out)
    print(f"\nMarked {count} platform points (area >= {MIN_PLATFORM_AREA}, aspect_ratio >= {MIN_ASPECT_RATIO}).")
    print(f"Lowest 3 waypoints shifted up by {PLATFORM_SHIFT_UP} pixels.")
    print(f"Rejected {rejected} blobs due to aspect ratio.")
    print(f"Saved to {OUTPUT_IMAGE}.")

    # Export waypoints as relative (0-1) for routine loader
    with open(WAYPOINTS_JSON, "w") as f:
        json.dump(waypoints, f, indent=2)
    print(f"Saved {len(waypoints)} waypoints to {WAYPOINTS_JSON} (relative 0-1).")


if __name__ == "__main__":
    main()