"""Reference image -> colour regions (outer contour + holes + a safe fill seed) for tracing in Paint.

usage: python demos/vectorize.py            -> demos/ref/regions.json, demos/ref/preview.png
Pipeline: crop -> remove the speech bubble -> 4x cubic upscale -> k-means colour clustering -> label cleanup
          -> per-colour contours (RETR_CCOMP) -> simplified polygons; seed = deepest interior point (distance transform).
Regions tile the picture (no overlap), so they can be painted in any order: outline in the region's own colour, then flood fill.
"""
import json
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).parent
SRC = HERE / "ref" / "shinchan_vol1_cover.jpg"
CROP = (0, 150, 265, 376)          # x0, y0, x1, y1 in the original 265x376 cover
UP = 4                             # upscale before clustering: smoother contours
K = 6
MIN_AREA = 260                     # at UP x scale (~16 original px^2)


def whiteout_bubble(img):
    """The 'Vol.1' speech bubble (circle + tail) in the crop's top-left corner is not part of the character."""
    cv2.circle(img, (37, 20), 31, (255, 255, 255), -1)
    cv2.fillPoly(img, [np.array([[50, 30], [72, 52], [64, 28]])], (255, 255, 255))
    return img


def name_of(c):
    b, g, r = [int(v) for v in c]
    if max(r, g, b) < 130:            # black and the dark antialiasing transition between black and skin
        return "black"
    if r > 180 and g < 70 and b < 70:
        return "red"                  # leftover of the red '1' in the speech bubble: ignored
    if min(r, g, b) > 225:
        return "white"
    if r > 200 and 110 <= g <= 205 and b < 110:
        return "orange"
    return "skin"


def main():
    im = cv2.imread(str(SRC))
    x0, y0, x1, y1 = CROP
    crop = whiteout_bubble(im[y0:y1, x0:x1].copy())
    up = cv2.resize(crop, None, fx=UP, fy=UP, interpolation=cv2.INTER_CUBIC)
    up = cv2.GaussianBlur(up, (0, 0), 1.6)
    Z = up.reshape(-1, 3).astype(np.float32)
    _, labels, centers = cv2.kmeans(Z, K, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5), 3, cv2.KMEANS_PP_CENTERS)
    lab = labels.reshape(up.shape[:2]).astype(np.uint8)
    lab = cv2.medianBlur(lab, 7)
    names = [name_of(c) for c in centers]
    # merge clusters that got the same name (e.g. two skin shades) into the first of them, using the mean colour
    canon = {}
    for i, n in enumerate(names):
        canon.setdefault(n, []).append(i)
    counts = np.bincount(lab.ravel(), minlength=K)
    palette = {n: [int(v) for v in centers[max(idx, key=lambda i: counts[i])][::-1]] for n, idx in canon.items()}   # RGB of the biggest cluster
    merged = np.zeros_like(lab)
    order = list(canon)
    for n, idx in canon.items():
        for i in idx:
            merged[lab == i] = order.index(n)
    print("palette (RGB):", palette, "| pixel share:", {n: round(float((merged == order.index(n)).mean()), 3) for n in order})

    regions = []
    for n in order:
        if n in ("white", "red"):
            continue                                   # the canvas is already white / bubble leftover
        m = (merged == order.index(n)).astype(np.uint8) * 255
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        cs, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        if hier is None:
            continue
        hier = hier[0]
        for i, c in enumerate(cs):
            if hier[i][3] != -1:
                continue                               # holes are attached to their parent below
            holes = [cs[j] for j in range(len(cs)) if hier[j][3] == i and cv2.contourArea(cs[j]) >= MIN_AREA / 2]
            area = cv2.contourArea(c) - sum(cv2.contourArea(h) for h in holes)
            if area < MIN_AREA or cv2.boundingRect(c)[1] < 4:      # tiny, or touching the top edge (cover text leftovers)
                continue
            mask = np.zeros(m.shape, np.uint8)
            cv2.drawContours(mask, [c], -1, 255, -1)
            for h in holes:
                cv2.drawContours(mask, [h], -1, 0, -1)
            dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
            sy, sx = np.unravel_index(int(dist.argmax()), dist.shape)
            simp = lambda p: cv2.approxPolyDP(p, 1.6, True).reshape(-1, 2).tolist()
            regions.append({"color": n, "rgb": palette[n], "area": float(area), "radius": float(dist.max()),
                            "seed": [int(sx), int(sy)], "outer": simp(c), "holes": [simp(h) for h in holes]})
    regions.sort(key=lambda r: -r["area"])
    out = {"size": [up.shape[1], up.shape[0]], "up": UP, "palette": palette, "regions": regions}
    (HERE / "ref" / "regions.json").write_text(json.dumps(out), encoding="utf-8")
    print(len(regions), "regions:", [(r["color"], int(r["area"] / UP / UP), round(r["radius"] / UP, 1)) for r in regions[:25]])

    prev = np.full(up.shape, 255, np.uint8)
    for r in regions:                                   # paint exactly each region's own pixels (outer minus holes)
        mask = np.zeros(up.shape[:2], np.uint8)
        cv2.fillPoly(mask, [np.array(r["outer"], np.int32)], 255)
        for h in r["holes"]:
            cv2.fillPoly(mask, [np.array(h, np.int32)], 0)
        prev[mask > 0] = tuple(int(v) for v in r["rgb"][::-1])
    side = np.hstack([cv2.resize(crop, up.shape[1::-1], interpolation=cv2.INTER_CUBIC), prev])
    cv2.imwrite(str(HERE / "ref" / "preview.png"), cv2.resize(side, None, fx=0.55, fy=0.55, interpolation=cv2.INTER_AREA))


if __name__ == "__main__":
    main()
