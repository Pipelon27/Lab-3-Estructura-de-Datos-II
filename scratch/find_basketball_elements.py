import os
from PIL import Image
import numpy as np

def main():
    crop_dir = "artifacts/cropped_props"
    files = sorted(os.listdir(crop_dir))

    hoop_candidates = []
    court_candidates = []

    for fname in files:
        if not fname.endswith(".png"):
            continue
        # Extract c and r from tile_cXX_rYYY.png
        parts = fname.replace("tile_c", "").replace(".png", "").split("_r")
        c = int(parts[0])
        r = int(parts[1])

        img = Image.open(os.path.join(crop_dir, fname))
        arr = np.array(img)
        alpha = arr[:, :, 3]
        rgb = arr[:, :, :3]

        opaque_px = np.sum(alpha > 100)
        transparent_px = np.sum(alpha < 50)
        
        # Check if it has a high concentration of white/light pixels (court lines or backboard)
        white_px = np.sum((rgb[:, :, 0] > 200) & (rgb[:, :, 1] > 200) & (rgb[:, :, 2] > 200) & (alpha > 100))
        # Orange pixels (hoop rim)
        orange_px = np.sum((rgb[:, :, 0] > 180) & (rgb[:, :, 1] > 60) & (rgb[:, :, 1] < 150) & (rgb[:, :, 2] < 80) & (alpha > 100))
        # Dark pixels (pole or base)
        dark_px = np.sum((rgb[:, :, 0] < 100) & (rgb[:, :, 1] < 100) & (rgb[:, :, 2] < 100) & (alpha > 100))

        # Classify:
        # Court lines are usually highly transparent (e.g. transparent background > 600 pixels out of 1024) and have white lines.
        # But wait, gym court lines in modern school packs are usually 12-16 tiles in total, representing a half court or full court markings.
        # Let's see if a tile has transparent background and only white lines.
        if transparent_px > 400:
            if white_px > 10 and orange_px == 0 and dark_px < 50:
                court_candidates.append((c, r, white_px, transparent_px))
            elif orange_px > 5 or dark_px > 20:
                hoop_candidates.append((c, r, orange_px, white_px, dark_px, transparent_px))

    print("--- COURT LINES CANDIDATES (c, r, white_px, transparent_px) ---")
    for item in sorted(court_candidates, key=lambda x: (x[1], x[0])):
        print(f"Court Line: c={item[0]:02d}, r={item[1]:03d} (white={item[2]}, trans={item[3]})")

    print("\n--- HOOP/PROP CANDIDATES (c, r, orange_px, white_px, dark_px, transparent_px) ---")
    for item in sorted(hoop_candidates, key=lambda x: (x[1], x[0])):
        print(f"Hoop Prop: c={item[0]:02d}, r={item[1]:03d} (orange={item[2]}, white={item[3]}, dark={item[4]}, trans={item[5]})")

if __name__ == "__main__":
    main()
