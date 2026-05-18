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

    # Composite top half court lines (rows 79-82, columns 18-29)
    top_lines = img.crop((18 * tile_size, 79 * tile_size, 30 * tile_size, 83 * tile_size))
    canvas.paste(top_lines, (64, 128), top_lines)

    # Composite bottom half court lines (rows 90-93, columns 18-29)
    # Wait, let's see if rows 90-93 are indeed the bottom half!
    # Let's crop columns 18-29, rows 90-93 (which we noticed have white lines)
    # Wait! In our identify output, row 90-92 had c=18..20 as Hoop Prop/lines?
    # Let's check!
    bottom_lines = img.crop((18 * tile_size, 90 * tile_size, 30 * tile_size, 94 * tile_size))
    canvas.paste(bottom_lines, (64, 128 + 4 * tile_size), bottom_lines)

    # Let's add hoops!
    # Where are the hoops? Let's check which tiles are the hoops!
    # In rows 84-86:
    # Hoop facing down (south hoop): backboard at top, rim in middle, pole/base at bottom?
    # Wait, in the tileset:
    # Column 22, 23, 24?
    # Let's see:
    # c=22, r=84 is top-left, c=23, r=84 is top-center, c=24, r=84 is top-right?
    # Or c=21, r=84 to c=23, r=86?
    # Let's try pasting some candidate hoops at the top and bottom!
    
    # Let's paste hoop A at the top center of the court (e.g. above the top half lines)
    # Court center column is c_w // 2 = 6 * tile_size.
    # The hoop is 3 tiles wide, so it should be pasted at 64 + 4.5 * tile_size = 64 + 144 = 208 px.
    # Let's paste columns 21-23, rows 90-92 at the top!
    h1 = Image.new("RGBA", (3 * tile_size, 3 * tile_size))
    for r_offset, r in enumerate(range(90, 93)):
        for c_offset, c in enumerate(range(21, 24)):
            tile = img.crop((c * tile_size, r * tile_size, (c + 1) * tile_size, (r + 1) * tile_size))
            h1.paste(tile, (c_offset * tile_size, r_offset * tile_size), tile)
    canvas.paste(h1, (64 + 4 * tile_size + 16, 128 - 2 * tile_size), h1)

    # Let's paste hoop B at the bottom center of the court
    h2 = Image.new("RGBA", (3 * tile_size, 3 * tile_size))
    for r_offset, r in enumerate(range(93, 96)):
        for c_offset, c in enumerate(range(21, 24)):
            tile = img.crop((c * tile_size, r * tile_size, (c + 1) * tile_size, (r + 1) * tile_size))
            h2.paste(tile, (c_offset * tile_size, r_offset * tile_size), tile)
    canvas.paste(h2, (64 + 4 * tile_size + 16, 128 + 7 * tile_size), h2)

    os.makedirs("artifacts", exist_ok=True)
    canvas.save("artifacts/full_court_test.png")
    print("Full court composition test saved to artifacts/full_court_test.png")

if __name__ == "__main__":
    main()
