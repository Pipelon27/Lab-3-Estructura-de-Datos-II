from PIL import Image
import numpy as np

def main():
    img_path = "assets/13_School_32x32.png"
    img = Image.open(img_path)
    arr = np.array(img)
    tile_size = 32

    # Let's inspect rows 60 to 85, columns 0 to 31
    for r in range(60, 85):
        for c in range(32):
            tile = arr[r*tile_size:(r+1)*tile_size, c*tile_size:(c+1)*tile_size, :]
            alpha = tile[:, :, 3]
            total_opaque = np.sum(alpha > 100)
            if total_opaque > 10:
                rgb = tile[:, :, :3]
                # Detect orange (basketball hoop rim or brown court wood)
                orange_pixels = np.sum((rgb[:, :, 0] > 180) & (rgb[:, :, 1] > 60) & (rgb[:, :, 1] < 150) & (rgb[:, :, 2] < 80))
                # Detect white (court lines or backboard)
                white_pixels = np.sum((rgb[:, :, 0] > 200) & (rgb[:, :, 1] > 200) & (rgb[:, :, 2] > 200) & (alpha > 200))
                # Detect dark poles (R < 100, G < 100, B < 100)
                dark_pixels = np.sum((rgb[:, :, 0] < 100) & (rgb[:, :, 1] < 100) & (rgb[:, :, 2] < 100) & (alpha > 200))
                
                # Check if it has a mix of orange and dark (pole/hoop)
                if orange_pixels > 5 or white_pixels > 5 or dark_pixels > 5:
                    print(f"Tile ({c}, {r}): opaque={total_opaque:4d}, orange={orange_pixels:3d}, white={white_pixels:3d}, dark={dark_pixels:3d}")

if __name__ == "__main__":
    main()
