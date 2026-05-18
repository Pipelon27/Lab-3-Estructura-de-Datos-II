from PIL import Image
import numpy as np

def main():
    img_path = "assets/13_School_32x32.png"
    img = Image.open(img_path)
    arr = np.array(img)
    tile_size = 32

    # Let's inspect columns 21-26, rows 84-86
    print("Analyzing columns 21-26, rows 84-86:")
    for r in range(84, 87):
        for c in range(21, 27):
            tile = arr[r*tile_size:(r+1)*tile_size, c*tile_size:(c+1)*tile_size, :]
            alpha = tile[:, :, 3]
            opaque_px = np.sum(alpha > 100)
            rgb = tile[:, :, :3]
            
            orange = np.sum((rgb[:, :, 0] > 180) & (rgb[:, :, 1] > 50) & (rgb[:, :, 1] < 150) & (rgb[:, :, 2] < 80) & (alpha > 100))
            white = np.sum((rgb[:, :, 0] > 220) & (rgb[:, :, 1] > 220) & (rgb[:, :, 2] > 220) & (alpha > 100))
            grey = np.sum((rgb[:, :, 0] > 60) & (rgb[:, :, 0] < 180) & (rgb[:, :, 1] > 60) & (rgb[:, :, 1] < 180) & (rgb[:, :, 2] > 60) & (rgb[:, :, 2] < 180) & (alpha > 100))
            
            print(f"Tile ({c}, {r}): opaque={opaque_px:4d}, orange={orange:3d}, white={white:3d}, grey={grey:3d}")

if __name__ == "__main__":
    main()
