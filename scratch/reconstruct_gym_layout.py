import os
from PIL import Image

def main():
    img_path = "assets/13_School_32x32.png"
    img = Image.open(img_path)
    tile_size = 32

    # Let's create a test canvas of the basketball court area.
    # The court in map.py has size 1360 x 850 (at 220, 180).
    # In terms of 32x32 tiles, that's 42 tiles wide and 26 tiles high.
    # Let's create a test image representing this.
    court_w = 42 * tile_size
    court_h = 26 * tile_size
    canvas = Image.new("RGBA", (court_w, court_h), (176, 110, 66, 255))

    # Let's paste the court lines from rows 79-82, columns 18-29.
    # That's a 12x4 block of tiles!
    # Let's paste it repeatedly or centered to see how it looks!
    lines_w = 12 * tile_size
    lines_h = 4 * tile_size
    lines_crop = img.crop((18 * tile_size, 79 * tile_size, 30 * tile_size, 83 * tile_size))
    
    # Paste centered on the canvas
    px = (court_w - lines_w) // 2
    py = (court_h - lines_h) // 2
    canvas.paste(lines_crop, (px, py), lines_crop)

    # Let's also try other line blocks! What about rows 90-93, columns 18-29?
    # Let's see what is in rows 90-93, columns 18-29.
    lines_crop2 = img.crop((18 * tile_size, 90 * tile_size, 30 * tile_size, 94 * tile_size))
    canvas.paste(lines_crop2, (px, py + 6 * tile_size), lines_crop2)

    # Let's try some hoops!
    # Where are the hoops? Let's check:
    # Hoop 1: Candidate at c=22, r=84 to c=24, r=86?
    hoop_crop1 = img.crop((22 * tile_size, 84 * tile_size, 25 * tile_size, 87 * tile_size))
    canvas.paste(hoop_crop1, (50, 50), hoop_crop1)

    # Hoop 2: Candidate at c=25, r=84 to c=27, r=86?
    hoop_crop2 = img.crop((25 * tile_size, 84 * tile_size, 28 * tile_size, 87 * tile_size))
    canvas.paste(hoop_crop2, (150, 50), hoop_crop2)

    # Hoop 3: Candidate at c=30, r=84 to c=32, r=87?
    hoop_crop3 = img.crop((30 * tile_size, 84 * tile_size, 32 * tile_size, 87 * tile_size))
    canvas.paste(hoop_crop3, (250, 50), hoop_crop3)

    os.makedirs("artifacts", exist_ok=True)
    canvas.save("artifacts/reconstructed_court.png")
    print("Reconstructed court saved to artifacts/reconstructed_court.png")

if __name__ == "__main__":
    main()
