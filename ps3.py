"""
CS6476 PS3 - Full ps3.py (designed to pass ps3_tests.py)

Key goals:
- Robust marker detection in BOTH simple rectangle and wall images.
- Correct point ordering: [top-left, bottom-left, top-right, bottom-right]
- Homography via DLT (no banned OpenCV homography solvers)
- Projection via inverse warping using cv2.remap (NO cv2.warpPerspective)

Banned (DO NOT USE):
- cv2.findHomography
- cv2.getPerspectiveTransform
- cv2.warpPerspective
- cv2.goodFeaturesToTrack
- cv2.warpAffine
"""

import cv2
import numpy as np


# ============================================================
# Utilities
# ============================================================

def euclidean_distance(p0, p1):
    """Get Euclidean distance between two (x,y) points."""
    dx = float(p0[0]) - float(p1[0])
    dy = float(p0[1]) - float(p1[1])
    return float(np.sqrt(dx * dx + dy * dy))


def get_corners_list(image):
    """
    List of image corner coordinates used in warping.
    Order: [top-left, bottom-left, top-right, bottom-right]
    """
    h, w = image.shape[:2]
    return [(0, 0), (0, h - 1), (w - 1, 0), (w - 1, h - 1)]


def _order_points_tl_bl_tr_br(pts_xy):
    """
    Robustly order 4 points into [TL, BL, TR, BR].

    We use a two-stage rule that is stable for both axis-aligned and
    perspective quads:
    1) sort by y to split top two vs bottom two
    2) within each pair, sort by x (left/right)

    Returns integer tuples.
    """
    pts = np.array(pts_xy, dtype=np.float64).reshape(4, 2)

    idx_y = np.argsort(pts[:, 1])
    top = pts[idx_y[:2]]
    bot = pts[idx_y[2:]]

    top = top[np.argsort(top[:, 0])]
    bot = bot[np.argsort(bot[:, 0])]

    tl = top[0]
    tr = top[1]
    bl = bot[0]
    br = bot[1]

    return [
        (int(round(tl[0])), int(round(tl[1]))),
        (int(round(bl[0])), int(round(bl[1]))),
        (int(round(tr[0])), int(round(tr[1]))),
        (int(round(br[0])), int(round(br[1]))),
    ]


def _nms_points(points_xy_score, min_dist):
    """
    Non-maximum suppression on (x,y,score) points.
    Keeps highest scores, suppresses points within min_dist.
    """
    if not points_xy_score:
        return []
    pts = sorted(points_xy_score, key=lambda t: -t[2])
    kept = []
    min_d2 = float(min_dist * min_dist)
    for x, y, s in pts:
        ok = True
        for kx, ky, _ in kept:
            dx = float(x) - float(kx)
            dy = float(y) - float(ky)
            if dx * dx + dy * dy < min_d2:
                ok = False
                break
        if ok:
            kept.append((x, y, s))
    return kept


def _quad_is_convex(quad4):
    """Check if 4 points form a convex quad (in any order) by hull size."""
    q = np.array(quad4, dtype=np.float32).reshape(-1, 1, 2)
    hull = cv2.convexHull(q)
    return hull is not None and hull.shape[0] == 4


def _best_quad_by_area_and_score(candidates_xy_score, max_take=30):
    """
    Choose best 4 points among candidates by:
    - maximizing convex hull area (primary)
    - tie-breaker: maximize sum of scores

    candidates_xy_score: list[(x,y,score)]
    returns list[(x,y)] length 4 or None
    """
    if len(candidates_xy_score) < 4:
        return None

    cand = sorted(candidates_xy_score, key=lambda t: -t[2])[:max_take]
    pts = np.array([[c[0], c[1]] for c in cand], dtype=np.float32)
    scores = np.array([c[2] for c in cand], dtype=np.float64)
    n = pts.shape[0]

    best_area = -1.0
    best_sum = -1.0
    best_quad = None

    # brute force combos up to ~C(30,4)=27405 -> fine
    for i in range(n - 3):
        for j in range(i + 1, n - 2):
            for k in range(j + 1, n - 1):
                for m in range(k + 1, n):
                    quad = np.array([pts[i], pts[j], pts[k], pts[m]], dtype=np.float32)
                    if not _quad_is_convex(quad):
                        continue
                    area = float(abs(cv2.contourArea(quad.reshape(-1, 1, 2))))
                    if area <= 1e-6:
                        continue
                    ssum = float(scores[i] + scores[j] + scores[k] + scores[m])

                    # prioritize area, then score sum
                    if (area > best_area + 1e-9) or (abs(area - best_area) <= 1e-9 and ssum > best_sum):
                        best_area = area
                        best_sum = ssum
                        best_quad = quad

    if best_quad is None:
        return None

    return [(float(p[0]), float(p[1])) for p in best_quad]


# ============================================================
# Marker detection
# ============================================================

def _contour_candidates(gray):
    """
    Produce circle-ish blob center candidates using adaptive thresholding + contours.
    Returns list of (x,y,score).
    """
    h, w = gray.shape[:2]
    img_area = float(h * w)

    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # robust threshold for varied lighting/noise
    # markers are typically darker -> invert
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # clean small specks
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)

    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    out = []
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 60 or area > 0.25 * img_area:
            continue

        per = cv2.arcLength(c, True)
        if per < 1e-6:
            continue

        # circularity
        circ = 4.0 * np.pi * area / (per * per)
        if circ < 0.35:
            continue

        (cx, cy), r = cv2.minEnclosingCircle(c)
        if r < 5 or r > 250:
            continue

        # avoid border artifacts
        if cx < 2 or cy < 2 or cx > (w - 3) or cy > (h - 3):
            continue

        # score encourages circular & medium size
        score = float(2.5 * circ + (r / 60.0))
        out.append((float(cx), float(cy), score))

    return out


def _hough_candidates(gray):
    """
    Produce circle candidates using HoughCircles (helpful when contours merge/break).
    Returns list of (x,y,score).
    """
    h, w = gray.shape[:2]
    blur = cv2.GaussianBlur(gray, (7, 7), 1.5)

    # Hough params tuned for PS3 marker scale range
    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(25, int(0.08 * min(h, w))),
        param1=120,
        param2=22,
        minRadius=6,
        maxRadius=120,
    )

    out = []
    if circles is None:
        return out

    circles = circles[0].astype(np.float64)
    for x, y, r in circles:
        if x < 2 or y < 2 or x > (w - 3) or y > (h - 3):
            continue
        # score: prefer radius in a reasonable band and stable detections
        score = float(1.0 + min(r, 80.0) / 80.0)
        out.append((float(x), float(y), score))
    return out


def _template_score_map(gray, template_gray):
    """
    Full-image template match score map (normalized correlation).
    """
    res = cv2.matchTemplate(gray, template_gray, cv2.TM_CCOEFF_NORMED)
    return res.astype(np.float32)


def _candidates_from_template_peaks(score_map, template_shape, max_peaks=60, peak_thresh=0.35):
    """
    Extract candidate centers from template score_map by greedy peak picking.
    Returns list of (x_center, y_center, score).
    """
    th, tw = template_shape[:2]
    sm = score_map.copy()
    H, W = sm.shape
    out = []

    # suppression radius roughly half template
    sup_x = max(4, tw // 2)
    sup_y = max(4, th // 2)

    for _ in range(max_peaks):
        _, mv, _, ml = cv2.minMaxLoc(sm)
        if mv < peak_thresh:
            break
        x0, y0 = ml  # top-left in score map
        cx = float(x0 + tw / 2.0)
        cy = float(y0 + th / 2.0)
        out.append((cx, cy, float(mv)))

        x1 = max(0, x0 - sup_x)
        x2 = min(W, x0 + sup_x + 1)
        y1 = max(0, y0 - sup_y)
        y2 = min(H, y0 + sup_y + 1)
        sm[y1:y2, x1:x2] = 0.0

    return out


def find_markers(image, template=None):
    """
    Finds four corner markers.

    Returns list of four (x,y) tuples in order:
    [top-left, bottom-left, top-right, bottom-right]
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    h, w = gray.shape[:2]

    # --- 1) Template match (very strong signal in PS3 tests) ---
    candidates = []
    if template is not None:
        tgray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) if template.ndim == 3 else template.copy()
        score_map = _template_score_map(gray, tgray)
        t_cands = _candidates_from_template_peaks(score_map, tgray.shape, max_peaks=80, peak_thresh=0.25)
        candidates.extend(t_cands)

    # --- 2) Add geometric candidates (helpful under noise) ---
    candidates.extend(_contour_candidates(gray))
    candidates.extend(_hough_candidates(gray))

    if not candidates:
        return []

    # NMS: keep unique centers
    min_sep = max(18, int(0.04 * min(h, w)))
    candidates_nms = _nms_points(candidates, min_sep)

    # If we still don't have enough, just return what we can (but tests need 4)
    if len(candidates_nms) < 4:
        pts = [(int(round(x)), int(round(y))) for x, y, _ in candidates_nms]
        return pts

    # Pick best quad among candidates
    best_quad = _best_quad_by_area_and_score(candidates_nms, max_take=30)

    if best_quad is None:
        # fallback: top 4
        best_quad = [(candidates_nms[i][0], candidates_nms[i][1]) for i in range(4)]

    ordered = _order_points_tl_bl_tr_br(best_quad)
    return ordered


# ============================================================
# Draw box
# ============================================================

def draw_box(image, markers, thickness=1):
    """
    Draw 1-pixel width lines connecting box markers.

    markers order: [TL, BL, TR, BR]
    """
    out = image.copy()
    if markers is None or len(markers) != 4:
        return out

    tl, bl, tr, br = markers
    color = (0, 0, 255)

    cv2.line(out, tl, tr, color, thickness)
    cv2.line(out, tr, br, color, thickness)
    cv2.line(out, br, bl, color, thickness)
    cv2.line(out, bl, tl, color, thickness)

    return out


# ============================================================
# Homography (DLT)
# ============================================================

def find_four_point_transform(srcPoints, dstPoints):
    """
    Solve for perspective transform H using DLT.

    H maps src -> dst:  [x',y',1]^T ~ H [x,y,1]^T
    """
    if len(srcPoints) != 4 or len(dstPoints) != 4:
        raise ValueError("srcPoints and dstPoints must have length 4")

    A = []
    for (x, y), (xp, yp) in zip(srcPoints, dstPoints):
        x = float(x); y = float(y)
        xp = float(xp); yp = float(yp)
        A.append([x, y, 1.0, 0.0, 0.0, 0.0, -xp * x, -xp * y, -xp])
        A.append([0.0, 0.0, 0.0, x, y, 1.0, -yp * x, -yp * y, -yp])

    A = np.array(A, dtype=np.float64)
    _, _, Vt = np.linalg.svd(A)
    h = Vt[-1, :]
    H = h.reshape(3, 3)

    # normalize so H[2,2] = 1
    if abs(H[2, 2]) < 1e-12:
        # if extremely small, normalize by norm
        H = H / (np.linalg.norm(H) + 1e-12)
    else:
        H = H / H[2, 2]

    return H.astype(np.float64)


# ============================================================
# Projection (inverse warping via remap)
# ============================================================

def project_imageA_onto_imageB(imageA, imageB, homography):
    """
    Project imageA into imageB using homography (A->B).

    We compute warpedA (same size as B) using inverse mapping and cv2.remap.
    Then we overlay warpedA onto imageB where warped pixels are valid.

    IMPORTANT for unit test:
    - When imageB is black background, result should match cv2.warpPerspective
      output closely (they compare SSIM).
    """
    out = imageB.copy()
    hB, wB = imageB.shape[:2]
    hA, wA = imageA.shape[:2]

    H = homography.astype(np.float64)
    Hinv = np.linalg.inv(H)

    # destination grid
    ys, xs = np.indices((hB, wB), dtype=np.float32)
    ones = np.ones_like(xs, dtype=np.float32)

    dst_h = np.stack([xs, ys, ones], axis=0).reshape(3, -1).astype(np.float64)  # 3xN
    src_h = Hinv @ dst_h
    src_h /= (src_h[2:3, :] + 1e-12)

    map_x = src_h[0, :].reshape(hB, wB).astype(np.float32)
    map_y = src_h[1, :].reshape(hB, wB).astype(np.float32)

    warped = cv2.remap(
        imageA,
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0
    )

    # Valid where source coords inside imageA (use -1 for bilinear safety)
    valid = (map_x >= 0) & (map_x < (wA - 1)) & (map_y >= 0) & (map_y < (hA - 1))

    if warped.ndim == 3:
        out[valid] = warped[valid]
    else:
        out[valid] = warped[valid]

    return out


# ============================================================
# Video generator
# ============================================================

def video_frame_generator(filename):
    """Generator that yields frames and yields None at end."""
    video = cv2.VideoCapture(filename)
    while True:
        ret, frame = video.read()
        if not ret:
            break
        yield frame
    video.release()
    yield None


# ============================================================
# Harris Corner Detection (Parts 8+)
# ============================================================

class Automatic_Corner_Detection(object):
    def __init__(self):
        self.SOBEL_X = np.array([[-1, 0, 1],
                                 [-2, 0, 2],
                                 [-1, 0, 1]], dtype=np.float32)
        self.SOBEL_Y = np.array([[-1, -2, -1],
                                 [0,   0,  0],
                                 [1,   2,  1]], dtype=np.float32)

    def gradients(self, image_bw):
        img = image_bw.astype(np.float32)
        Ix = cv2.filter2D(img, ddepth=-1, kernel=self.SOBEL_X, borderType=cv2.BORDER_CONSTANT)
        Iy = cv2.filter2D(img, ddepth=-1, kernel=self.SOBEL_Y, borderType=cv2.BORDER_CONSTANT)
        return Ix, Iy

    def second_moments(self, image_bw, ksize=7, sigma=10):
        Ix, Iy = self.gradients(image_bw)
        Ix2 = Ix * Ix
        Iy2 = Iy * Iy
        Ixy = Ix * Iy

        half = ksize // 2
        x = np.arange(-half, half + 1, dtype=np.float32)
        X, Y = np.meshgrid(x, x)
        G = np.exp(-(X * X + Y * Y) / (2.0 * sigma * sigma))
        G /= (np.sum(G) + 1e-12)

        sx2 = cv2.filter2D(Ix2, -1, G, borderType=cv2.BORDER_CONSTANT)
        sy2 = cv2.filter2D(Iy2, -1, G, borderType=cv2.BORDER_CONSTANT)
        sxsy = cv2.filter2D(Ixy, -1, G, borderType=cv2.BORDER_CONSTANT)
        return sx2, sy2, sxsy

    def harris_response_map(self, image_bw, ksize=7, sigma=5, alpha=0.05):
        sx2, sy2, sxsy = self.second_moments(image_bw, ksize, sigma)
        det = sx2 * sy2 - sxsy * sxsy
        trace = sx2 + sy2
        R = det - alpha * (trace ** 2)

        # normalize to 0..1 for stability
        rmin, rmax = float(np.min(R)), float(np.max(R))
        if rmax - rmin > 1e-12:
            R = (R - rmin) / (rmax - rmin)
        else:
            R = np.zeros_like(R, dtype=np.float32)
        return R.astype(np.float32)

    def nms_maxpool(self, R, k, ksize):
        # threshold below median
        Rt = R.copy()
        med = float(np.median(Rt))
        Rt[Rt < med] = 0.0

        kernel = np.ones((ksize, ksize), dtype=np.uint8)
        R_dil = cv2.dilate(Rt, kernel, iterations=1)

        keep = (Rt == R_dil) & (Rt > 0)
        ys, xs = np.where(keep)
        vals = Rt[keep]

        if vals.size == 0:
            return np.array([], dtype=np.int32), np.array([], dtype=np.int32)

        idx = np.argsort(vals)[::-1][:k]
        x = xs[idx].astype(np.int32)
        y = ys[idx].astype(np.int32)
        return x, y

    def harris_corner(self, image_bw, k=100):
        R = self.harris_response_map(image_bw, ksize=7, sigma=5, alpha=0.05)
        x, y = self.nms_maxpool(R, k=k, ksize=7)
        return x, y


# ============================================================
# Mosaic (Parts 7/9) - inverse warp via remap
# ============================================================

class Image_Mosaic(object):
    def __init__(self):
        self.tx = 0
        self.ty = 0

    def image_warp_inv(self, im_src, im_dst, H):
        """
        Inverse warp im_dst into a canvas aligned with im_src.
        H is expected to map dst -> src (as many PS3 setups do).
        """
        H = H.astype(np.float64)

        hS, wS = im_src.shape[:2]
        hD, wD = im_dst.shape[:2]

        # Map dst corners into src space: p_src ~ H p_dst
        dst_corners = np.array([[0, 0, 1],
                                [wD - 1, 0, 1],
                                [wD - 1, hD - 1, 1],
                                [0, hD - 1, 1]], dtype=np.float64).T
        dst_in_src = H @ dst_corners
        dst_in_src /= (dst_in_src[2:3, :] + 1e-12)

        xs = dst_in_src[0, :]
        ys = dst_in_src[1, :]

        x_min = min(0.0, float(xs.min()))
        y_min = min(0.0, float(ys.min()))
        x_max = max(float(wS - 1), float(xs.max()))
        y_max = max(float(hS - 1), float(ys.max()))

        self.tx = int(np.floor(-x_min)) if x_min < 0 else 0
        self.ty = int(np.floor(-y_min)) if y_min < 0 else 0

        out_w = int(np.ceil(x_max - x_min + 1))
        out_h = int(np.ceil(y_max - y_min + 1))

        # translation to canvas
        T = np.array([[1, 0, self.tx],
                      [0, 1, self.ty],
                      [0, 0, 1]], dtype=np.float64)

        # dst -> canvas is T * (dst->src) = T*H
        H_canvas = T @ H
        H_canvas_inv = np.linalg.inv(H_canvas)  # canvas -> dst

        ys_c, xs_c = np.indices((out_h, out_w), dtype=np.float32)
        ones = np.ones_like(xs_c, dtype=np.float32)
        canvas_h = np.stack([xs_c, ys_c, ones], axis=0).reshape(3, -1).astype(np.float64)

        dst_h = H_canvas_inv @ canvas_h
        dst_h /= (dst_h[2:3, :] + 1e-12)

        map_x = dst_h[0, :].reshape(out_h, out_w).astype(np.float32)
        map_y = dst_h[1, :].reshape(out_h, out_w).astype(np.float32)

        warped = cv2.remap(im_dst, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        return warped

    def output_mosaic(self, img_src, img_warped):
        """Overlay img_src onto img_warped at offset (tx,ty)."""
        out = img_warped.copy()
        hS, wS = img_src.shape[:2]
        hW, wW = out.shape[:2]

        x0, y0 = self.tx, self.ty
        x1 = min(wW, x0 + wS)
        y1 = min(hW, y0 + hS)

        src_crop = img_src[0:(y1 - y0), 0:(x1 - x0)]
        dst_crop = out[y0:y1, x0:x1]

        if src_crop.ndim == 3:
            mask = np.any(src_crop > 0, axis=2)
            dst_crop[mask] = src_crop[mask]
        else:
            mask = src_crop > 0
            dst_crop[mask] = src_crop[mask]

        out[y0:y1, x0:x1] = dst_crop
        return out
