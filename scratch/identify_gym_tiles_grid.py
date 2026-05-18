import os
from PIL import Image
import numpy as np

def main():
    img_path = "assets/13_School_32x32.png"
    img = Image.open(img_path)
    arr = np.array(img)
    tile_size = 32

    # Let's analyze columns 18 to 31, rows 75 to 95
    c_start, c_end = 18, 32
    r_start, r_end = 75, 96

    print("--- Detailed Tile Analysis ---")
    for r in range(r_start, r_end):
        for c in range(c_start, c_end):
            tile = arr[r*tile_size:(r+1)*tile_size, c*tile_size:(c+1)*tile_size, :]
            alpha = tile[:, :, 3]
            opaque_px = np.sum(alpha > 100)
            if opaque_px == 0:
                continue

            rgb = tile[:, :, :3]
            
            # Check for white pixels (court lines or backboard)
            white_px = np.sum((rgb[:, :, 0] > 220) & (rgb[:, :, 1] > 220) & (rgb[:, :, 2] > 220) & (alpha > 150))
            # Orange/red pixels (hoop rim or ball)
            orange_px = np.sum((rgb[:, :, 0] > 180) & (rgb[:, :, 1] > 50) & (rgb[:, :, 1] < 150) & (rgb[:, :, 2] < 80) & (alpha > 150))
            # Grey/dark pixels (poles, nets, frames)
            grey_px = np.sum((rgb[:, :, 0] > 60) & (rgb[:, :, 0] < 180) & (rgb[:, :, 1] > 60) & (rgb[:, :, 1] < 180) & (rgb[:, :, 2] > 60) & (rgb[:, :, 2] < 180) & (alpha > 150))
            
            # Draw a mini visual description of the tile (e.g. lines, circles, hoops)
            # Find the boundaries of the non-transparent pixels in this tile
            rows, cols = np.where(alpha > 100)
            if len(rows) > 0:
                ymin, ymax = rows.min(), rows.max()
                xmin, xmax = cols.min(), cols.max()
                w_box = xmax - xmin + 1
                h_box = ymax - ymin + 1
                print(f"Tile ({c:02d}, {r:03d}): opaque={opaque_px:4d}, orange={orange_px:3d}, white={white_px:3d}, grey={grey_px:3d}, box=({xmin:02d},{ymin:02d}) to ({xmax:02d},{ymax:02d}), size={w_box}x{h_box}")

if __name__ == "__main__":
    main()
