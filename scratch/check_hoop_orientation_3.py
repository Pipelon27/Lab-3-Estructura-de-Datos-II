from PIL import Image
import numpy as np

def main():
    img_path = "assets/13_School_32x32.png"
    img = Image.open(img_path)
    tile_size = 32

    # Let's inspect hoop candidates c=25..27, r=93..95
    print("--- Visualizing hoop_test_93_95_c25_27.png ---")
    for r_offset, r in enumerate(range(93, 96)):
        print(f"Row {r}:")
        for c in range(25, 28):
            tile = img.crop((c * tile_size, r * tile_size, (c + 1) * tile_size, (r + 1) * tile_size))
            alpha = np.array(tile)[:, :, 3]
            # Downsample to 8x8 ASCII for printing
            for y in range(0, 32, 4):
                line = ""
                for x in range(0, 32, 4):
                    val = alpha[y, x]
                    if val > 150:
                        line += "#"
                    elif val > 50:
                        line += "."
                    else:
                        line += " "
                print(f"  Col {c} y={y:02d}: {line}")

if __name__ == "__main__":
    main()
