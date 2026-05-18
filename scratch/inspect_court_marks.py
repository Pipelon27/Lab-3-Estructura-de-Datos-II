from PIL import Image
import numpy as np

def main():
    img_path = "assets/13_School_32x32.png"
    img = Image.open(img_path)
    arr = np.array(img)
    tile_size = 32

    print("Analyzing white pixel counts in columns 18-29:")
    for r in range(75, 115):
        white_in_row = 0
        for c in range(18, 30):
            tile = arr[r*tile_size:(r+1)*tile_size, c*tile_size:(c+1)*tile_size, :]
            alpha = tile[:, :, 3]
            rgb = tile[:, :, :3]
            # White pixels
            white = np.sum((rgb[:, :, 0] > 200) & (rgb[:, :, 1] > 200) & (rgb[:, :, 2] > 200) & (alpha > 100))
            white_in_row += white
        if white_in_row > 100:
            print(f"Row {r:03d}: Total White Pixels in Cols 18-29 = {white_in_row}")

if __name__ == "__main__":
    main()
