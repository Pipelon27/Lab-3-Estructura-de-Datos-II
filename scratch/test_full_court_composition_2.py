import os
from PIL import Image

def main():
    img_path = "assets/13_School_32x32.png"
    img = Image.open(img_path)
    tile_size = 32

    # Court size in tiles: 12 wide, 8 high
    c_w = 12 * tile_size
    c_h = 8 * tile_size
    
    # We create a background canvas with the wood floor color (176, 110, 66)
    canvas = Image.new("RGBA", (c_w + 128, c_h + 256), (176, 110, 66, 255))

    # Composite top half court lines (rows 75-78, columns 18-29)
    top_lines = img.crop((18 * tile_size, 75 * tile_size, 30 * tile_size, 79 * tile_size))
    canvas.paste(top_lines, (64, 128), top_lines)

    # Composite bottom half court lines (rows 79-82, columns 18-29)
    bottom_lines = img.crop((18 * tile_size, 79 * tile_size, 30 * tile_size, 83 * tile_size))
    canvas.paste(bottom_lines, (64, 128 + 4 * tile_size), bottom_lines)

    # Let's add hoops!
    # Let's paste hoop A at the top center of the court (above the top half lines)
    # The court lines start at column 18 and end at 29.
    # Center column is (18 + 29) / 2 = 23.5.
    # The hoops are 3 tiles wide, so they span columns 21-23, rows 90-92 for the top hoop,
    # and columns 21-23, rows 93-95 for the bottom hoop.
    # Wait, let's paste the top hoop:
    h1 = Image.new("RGBA", (3 * tile_size, 3 * tile_size))
    for r_offset, r in enumerate(range(90, 93)):
        for c_offset, c in enumerate(range(21, 24)):
            tile = img.crop((c * tile_size, r * tile_size, (c + 1) * tile_size, (r + 1) * tile_size))
            h1.paste(tile, (c_offset * tile_size, r_offset * tile_size), tile)
    canvas.paste(h1, (64 + 4 * tile_size + 16, 128 - 2 * tile_size), h1)

    # Let's paste the bottom hoop:
    h2 = Image.new("RGBA", (3 * tile_size, 3 * tile_size))
    for r_offset, r in enumerate(range(93, 96)):
        for c_offset, c in enumerate(range(21, 24)):
            tile = img.crop((c * tile_size, r * tile_size, (c + 1) * tile_size, (r + 1) * tile_size))
            h2.paste(tile, (c_offset * tile_size, r_offset * tile_size), tile)
    canvas.paste(h2, (64 + 4 * tile_size + 16, 128 + 7 * tile_size), h2)

    os.makedirs("artifacts", exist_ok=True)
    canvas.save("artifacts/full_court_test_2.png")
    print("Full court composition test 2 saved to artifacts/full_court_test_2.png")

if __name__ == "__main__":
    main()
