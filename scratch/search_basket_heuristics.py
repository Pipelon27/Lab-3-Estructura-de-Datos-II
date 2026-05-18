from PIL import Image
import numpy as np

def main():
    img_path = "assets/13_School_32x32.png"
    img = Image.open(img_path)
    arr = np.array(img)  # WxHx4 RGBA
    h, w, c = arr.shape
    tile_size = 32
    cols = w // tile_size
    rows = h // tile_size

    print("Scanning non-empty rows and checking color channels...")
    for r in range(rows):
        row_arr = arr[r*tile_size:(r+1)*tile_size, :, :]
        alpha = row_arr[:, :, 3]
        total_opaque = np.sum(alpha > 50)
        if total_opaque > 100:
            # Get some color stats
            rgb = row_arr[:, :, :3]
            # Basketball court lines are usually white or black.
            # Hoops are orange (R > 180, G is 70-130, B < 50)
            orange_pixels = np.sum((rgb[:, :, 0] > 180) & (rgb[:, :, 1] > 60) & (rgb[:, :, 1] < 150) & (rgb[:, :, 2] < 80))
            # White backboard / lines
            white_pixels = np.sum((rgb[:, :, 0] > 200) & (rgb[:, :, 1] > 200) & (rgb[:, :, 2] > 200) & (alpha > 200))
            # Let's print row with some info
            print(f"Row {r:03d}: opaque={total_opaque:05d}, orange={orange_pixels:04d}, white={white_pixels:04d}")

if __name__ == "__main__":
    main()
