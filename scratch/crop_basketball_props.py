import os
from PIL import Image

def main():
    img_path = "assets/13_School_32x32.png"
    img = Image.open(img_path)
    w, h = img.size
    tile_size = 32

    output_dir = "artifacts/cropped_props"
    os.makedirs(output_dir, exist_ok=True)

    # Let's crop and save rows 70 to 94, columns 18 to 29 (which have a lot of white/court-like pixels)
    # And also rows 80 to 93, columns 18 to 31 (where basketball hoops/props might be)
    for r in range(60, 95):
        for c in range(32):
            tile = img.crop((c * tile_size, r * tile_size, (c + 1) * tile_size, (r + 1) * tile_size))
            # Only save non-empty tiles
            alpha = tile.split()[-1]
            # Get bounding box of non-transparent area
            bbox = alpha.getbbox()
            if bbox:
                tile.save(os.path.join(output_dir, f"tile_c{c:02d}_r{r:03d}.png"))

    print("Cropped non-empty tiles saved to artifacts/cropped_props/")

if __name__ == "__main__":
    main()
