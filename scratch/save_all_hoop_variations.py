import os
from PIL import Image, ImageDraw, ImageFont

def main():
    img_path = "assets/13_School_32x32.png"
    img = Image.open(img_path)
    tile_size = 32

    # We want to try various 3x3 blocks:
    # 1. c=21-23, r=90-92
    # 2. c=24-26, r=90-92
    # 3. c=21-23, r=93-95
    # 4. c=24-26, r=93-95
    # 5. c=27-29, r=90-92
    # 6. c=27-29, r=93-95
    # 7. c=21-23, r=84-86 (Wait, c=21-23 r=84-86 could be the top hoop!)
    # Let's check r=84-86, columns 21-23 and columns 24-26!
    # In identify output, c=22,23,24 r=84 had orange/white!
    # And c=25,26,27 r=84-86 had orange/white!
    
    variations = [
        ("c21-23, r84-86", 21, 84),
        ("c24-26, r84-86", 24, 84),
        ("c21-23, r90-92", 21, 90),
        ("c24-26, r90-92", 24, 90),
        ("c21-23, r93-95", 21, 93),
        ("c24-26, r93-95", 24, 93),
    ]

    sheet_w = len(variations) * 128 + 100
    sheet_h = 256
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (176, 110, 66, 255)) # Gym wood floor background
    draw = ImageDraw.Draw(sheet)
    
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    for idx, (label, start_c, start_r) in enumerate(variations):
        x = idx * 128 + 50
        y = 50
        
        # Draw label
        draw.text((x, 15), label, fill=(255, 255, 255, 255), font=font)
        
        # Paste 3x3 block
        for r_offset in range(3):
            r = start_r + r_offset
            for c_offset in range(3):
                c = start_c + c_offset
                tile = img.crop((c * tile_size, r * tile_size, (c + 1) * tile_size, (r + 1) * tile_size))
                sheet.paste(tile, (x + c_offset * tile_size, y + r_offset * tile_size), tile)

    os.makedirs("artifacts", exist_ok=True)
    sheet.save("artifacts/all_hoop_variations.png")
    print("All hoop variations saved to artifacts/all_hoop_variations.png")

if __name__ == "__main__":
    main()
