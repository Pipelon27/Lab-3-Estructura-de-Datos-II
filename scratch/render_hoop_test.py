import os
from PIL import Image

def main():
    img_path = "assets/13_School_32x32.png"
    img = Image.open(img_path)
    tile_size = 32

    os.makedirs("artifacts", exist_ok=True)

    # Crop 1: columns 21-23, rows 90-92 (Downwards / South facing hoop?)
    # Remember: top-to-bottom of the crop is: row 90 (bottom/base), row 91 (mid), row 92 (top)
    # Wait, in the image, row 90 is at the top of these three rows, row 92 is at the bottom.
    # Let's crop it exactly as it appears in the tileset:
    # Row 90 (first), Row 91 (second), Row 92 (third).
    h1 = Image.new("RGBA", (3 * tile_size, 3 * tile_size))
    for r_offset, r in enumerate(range(90, 93)):
        for c_offset, c in enumerate(range(21, 24)):
            tile = img.crop((c * tile_size, r * tile_size, (c + 1) * tile_size, (r + 1) * tile_size))
            h1.paste(tile, (c_offset * tile_size, r_offset * tile_size), tile)
    h1.save("artifacts/hoop_test_90_92_c21_23.png")

    # Crop 2: columns 24-26, rows 90-92
    h2 = Image.new("RGBA", (3 * tile_size, 3 * tile_size))
    for r_offset, r in enumerate(range(90, 93)):
        for c_offset, c in enumerate(range(24, 27)):
            tile = img.crop((c * tile_size, r * tile_size, (c + 1) * tile_size, (r + 1) * tile_size))
            h2.paste(tile, (c_offset * tile_size, r_offset * tile_size), tile)
    h2.save("artifacts/hoop_test_90_92_c24_26.png")

    # What about columns 21-23, rows 93-95? Let's check!
    h3 = Image.new("RGBA", (3 * tile_size, 3 * tile_size))
    for r_offset, r in enumerate(range(93, 96)):
        for c_offset, c in enumerate(range(21, 24)):
            tile = img.crop((c * tile_size, r * tile_size, (c + 1) * tile_size, (r + 1) * tile_size))
            h3.paste(tile, (c_offset * tile_size, r_offset * tile_size), tile)
    h3.save("artifacts/hoop_test_93_95_c21_23.png")

    # What about columns 25-27, rows 93-95?
    h4 = Image.new("RGBA", (3 * tile_size, 3 * tile_size))
    for r_offset, r in enumerate(range(93, 96)):
        for c_offset, c in enumerate(range(25, 28)):
            tile = img.crop((c * tile_size, r * tile_size, (c + 1) * tile_size, (r + 1) * tile_size))
            h4.paste(tile, (c_offset * tile_size, r_offset * tile_size), tile)
    h4.save("artifacts/hoop_test_93_95_c25_27.png")

    print("Hoop test crops saved!")

if __name__ == "__main__":
    main()
