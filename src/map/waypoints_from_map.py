"""
Waypoints from map images: platform-centroid logic (same as mark_platform_centers.py).
Used by auto routine to derive waypoints from the matched minimap PNG.

If waypoints appear shifted (e.g. 50px too low), the map image may have a border the
in-game minimap doesn't. Use crop_top/crop_bottom/crop_left/crop_right (pixels), or
generate corrected waypoints with graph_waypoints.py and save as *_waypoints.json.
"""
import json
import os
import re
import cv2
import numpy as np

try:
    import pytesseract
    _PYTESSERACT_IMPORTED = True
except ImportError:
    pytesseract = None
    _PYTESSERACT_IMPORTED = False

def load_map_image_for_match(path, background_bgr=(0, 0, 0)):
    """
    Load a map PNG and composite onto a solid background so transparent (checkered) areas
    match the game minimap's solid black. Game minimap has black background; assets often have alpha.
    """
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 2:
        return img
    if img.ndim == 3 and img.shape[2] == 3:
        return img
    if img.ndim == 3 and img.shape[2] == 4:
        # Composite onto solid background: transparent -> background color
        b, g, r, a = cv2.split(img)
        a = a.astype(np.float32) / 255.0
        bg = np.array(background_bgr, dtype=np.float32)
        out = np.zeros_like(img[:, :, :3], dtype=np.float32)
        for c in range(3):
            out[:, :, c] = a * img[:, :, c].astype(np.float32) + (1 - a) * bg[c]
        return out.astype(np.uint8)
    return img


# Same constants as mark_platform_centers.py
BG_THRESHOLD = 15  # Increased from 5 to catch darker platforms
ERODE_SIZE = 2  # Reduced from 3 to preserve platform detection
MIN_PLATFORM_AREA = 30
MIN_ASPECT_RATIO = 2.0  # Platforms must be at least 2x wider than tall
PLATFORM_SHIFT_UP = 10  # Shift the lowest 3 waypoints up by this many pixels


def waypoints_from_map_image(
    img,
    crop_top=0,
    crop_bottom=0,
    crop_left=0,
    crop_right=0,
):
    """
    Compute platform centers from a map image (BGR or BGRA), return as relative (0-1) waypoints.
    Filters platforms by aspect ratio to exclude non-platform blobs.
    For the bottom-most platform, generates 3 waypoints at 1/4, 1/2, and 3/4 of its width.
    Only the lowest 3 waypoints (by y) are shifted up by PLATFORM_SHIFT_UP pixels.
    Coordinates are normalized by the content region after cropping (so crop compensates for
    borders that would otherwise shift points).
    :param img: numpy array (H, W, 3 or 4) from cv2.imread
    :param crop_top: pixels to exclude from top (use e.g. 50 if map has top border)
    :param crop_bottom: pixels to exclude from bottom
    :param crop_left: pixels to exclude from left
    :param crop_right: pixels to exclude from right
    :return: list of {"x": float, "y": float} in 0-1
    """
    if img is None:
        return []
    if img.ndim == 3 and img.shape[2] == 4:
        img = img[:, :, :3]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, BG_THRESHOLD, 255, cv2.THRESH_BINARY)
    kernel = np.ones((ERODE_SIZE, ERODE_SIZE), np.uint8)
    eroded = cv2.erode(binary, kernel)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(eroded)
    h_img, w_img = gray.shape[:2]
    
    # Content region after crop (same as game minimap if borders match)
    w_content = w_img - crop_left - crop_right
    h_content = h_img - crop_top - crop_bottom
    if w_content <= 0 or h_content <= 0:
        w_content, h_content = w_img, h_img
        crop_left = crop_right = crop_top = crop_bottom = 0
    
    # First pass: collect all valid platforms with aspect ratio filtering
    valid_platforms = []
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        width = stats[i, cv2.CC_STAT_WIDTH]
        height = stats[i, cv2.CC_STAT_HEIGHT]
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        
        # Filter by area
        if area < MIN_PLATFORM_AREA:
            continue
        
        # Calculate aspect ratio and filter
        aspect_ratio = width / height if height > 0 else 0
        if aspect_ratio < MIN_ASPECT_RATIO:
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
        })
    
    # Find the bottom-most platform (highest y-coordinate)
    bottom_platform_index = None
    if valid_platforms:
        bottom_platform = max(valid_platforms, key=lambda p: p['cy'])
        bottom_platform_index = bottom_platform['index']
    
    # Second pass: generate waypoints (unshifted); we'll shift only the lowest 3
    waypoints_raw = []
    for platform in valid_platforms:
        i = platform['index']
        cx = platform['cx']
        cy = platform['cy']
        x = platform['x']
        width = platform['width']
        
        if i == bottom_platform_index:
            # Bottom platform: 3 points at 1/4, 1/2, and 3/4 of width
            positions = [0.25, 0.5, 0.75]
            for pos_fraction in positions:
                px = x + width * pos_fraction
                py = cy
                waypoints_raw.append({
                    "px": px, "py": py,
                    "is_bottom_platform": True
                })
        else:
            # Regular platform: single center point
            px = cx
            py = cy
            waypoints_raw.append({
                "px": px, "py": py,
                "is_bottom_platform": False
            })
    
    # Find indices of the 3 waypoints with highest y (lowest on map); only those get shifted up
    indices_to_shift = sorted(
        range(len(waypoints_raw)),
        key=lambda idx: waypoints_raw[idx]["py"],
        reverse=True
    )[:3]
    for idx in indices_to_shift:
        waypoints_raw[idx]["py"] -= PLATFORM_SHIFT_UP
    
    # Normalize to 0-1 relative to content region (preserve original waypoint order)
    waypoints = []
    for w in waypoints_raw:
        x_rel = (w["px"] - crop_left) / w_content
        y_rel = (w["py"] - crop_top) / h_content
        waypoints.append({
            "x": round(x_rel, 4),
            "y": round(y_rel, 4),
            "is_bottom_platform": w["is_bottom_platform"]
        })
    return waypoints


def waypoints_from_map_path(map_path):
    """
    Load map image from path and return waypoints. If a *_waypoints.json exists
    alongside the map (same base name), load that instead of recomputing.
    If a *_crop.json exists with e.g. {"crop_top": 50}, those pixels are excluded
    when computing waypoints (so borders don't shift points).
    :param map_path: path to map PNG
    :return: list of {"x": float, "y": float} in 0-1
    """
    base, _ = os.path.splitext(map_path)
    json_path = base + "_waypoints.json"
    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            return json.load(f)
    crop = {}
    crop_path = base + "_crop.json"
    if os.path.exists(crop_path):
        with open(crop_path, "r") as f:
            crop = json.load(f)
    # Composite transparent PNGs onto black so platform detection matches game minimap
    img = load_map_image_for_match(map_path)
    if img is None:
        img = cv2.imread(map_path)
    if img is not None and img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return waypoints_from_map_image(
        img,
        crop_top=crop.get("crop_top", 0),
        crop_bottom=crop.get("crop_bottom", 0),
        crop_left=crop.get("crop_left", 0),
        crop_right=crop.get("crop_right", 0),
    )


# OCR: region where map name appears (top 20% height, left 40% width)
_OCR_ROI_WIDTH_FRAC = 0.40
_OCR_ROI_HEIGHT_FRAC = 0.20
_OCR_MATCH_MIN_SCORE = 0.5  # minimum score to accept OCR match (word overlap / containment)
# Default Windows Tesseract path when not on PATH (fail gracefully if missing)
_TESSERACT_CMD_WINDOWS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def _is_ocr_available():
    """True if pytesseract is installed and Tesseract executable is usable. Fails gracefully."""
    if not _PYTESSERACT_IMPORTED:
        return False
    try:
        if os.name == "nt" and os.path.isfile(_TESSERACT_CMD_WINDOWS):
            pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD_WINDOWS
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _asset_filename_to_map_name(filename):
    """Map_Laboratory_Behind_Locked_Door_4.png -> Laboratory Behind Locked Door 4"""
    name = os.path.splitext(filename)[0]
    if name.lower().startswith("map_"):
        name = name[4:]
    return name.replace("_", " ").strip()


def _normalize_for_match(text):
    """Lowercase, collapse spaces, remove non-alphanumeric for fuzzy match."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _read_text_from_roi_ocr(image, roi_rect):
    """Run OCR on cropped region (x, y, w, h). Returns extracted text or '' on failure."""
    try:
        x, y, w, h = roi_rect
        img = image[y : y + h, x : x + w]
        if img.size == 0:
            return ""
        if len(img.shape) == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return pytesseract.image_to_string(img).strip()
    except Exception:
        return ""


def _best_matching_asset_ocr(ocr_text, minimaps_dir):
    """
    Compare OCR text to each asset's derived map name; return (best_path, best_score).
    Returns (None, 0.0) if no OCR text or no assets.
    """
    norm_ocr = _normalize_for_match(ocr_text)
    if not norm_ocr or not os.path.isdir(minimaps_dir):
        return None, 0.0
    best_path = None
    best_score = 0.0
    for name in sorted(os.listdir(minimaps_dir)):
        if not name.lower().endswith(".png"):
            continue
        path = os.path.join(minimaps_dir, name)
        map_name = _asset_filename_to_map_name(name)
        norm_map = _normalize_for_match(map_name)
        if not norm_map:
            continue
        if norm_map in norm_ocr:
            score = 1.0
        elif norm_ocr in norm_map:
            score = 0.95
        else:
            ocr_words = set(norm_ocr.split())
            map_words = set(norm_map.split())
            if not map_words:
                continue
            overlap = len(ocr_words & map_words) / len(map_words)
            score = overlap if overlap >= 0.5 else overlap * 0.5
        if score > best_score:
            best_score = score
            best_path = path
    return best_path, best_score


def find_matching_map(game_minimap_or_frame, minimaps_dir, threshold=0.7, scales=(0.25, 0.35, 0.5, 0.7, 0.85, 1.0, 1.2)):
    """
    Find which map asset matches the game by reading the map name with OCR from the
    top-left area (20% height, 40% width) and matching to asset names. If Tesseract
    is not installed or the path is missing, returns None without raising.
    :param game_minimap_or_frame: BGR numpy array (full game frame; we use top-left ROI for OCR)
    :param minimaps_dir: path to folder containing map PNGs (e.g. assets/minimaps)
    :param threshold: unused (kept for API compatibility)
    :param scales: unused (kept for API compatibility)
    :return: path to first matching PNG, or None
    """
    if game_minimap_or_frame is None or game_minimap_or_frame.size == 0:
        return None
    h, w = game_minimap_or_frame.shape[:2]
    if min(h, w) < 50:
        return None
    if not os.path.isdir(minimaps_dir):
        return None
    if min(h, w) <= 400:
        return None  # Need full frame for OCR region
    if not _is_ocr_available():
        return None
    roi_w = int(w * _OCR_ROI_WIDTH_FRAC)
    roi_h = int(h * _OCR_ROI_HEIGHT_FRAC)
    roi_rect = (0, 0, roi_w, roi_h)
    ocr_text = _read_text_from_roi_ocr(game_minimap_or_frame, roi_rect)
    best_path, best_score = _best_matching_asset_ocr(ocr_text, minimaps_dir)
    if best_path is not None and best_score >= _OCR_MATCH_MIN_SCORE:
        return best_path
    return None
