import os
from PIL import Image, ImageDraw

def main():
    img_path = "assets/Baloncesto.png"
    img = Image.open(img_path)
    w, h = img.size
    
    # Create a test background
    debug_img = Image.new("RGBA", (w, h), (30, 40, 50, 255))
    debug_img.paste(img, (0, 0), img)
    
    draw = ImageDraw.Draw(debug_img)
    grid_size = 32
    
    # Draw vertical grid lines
    for x in range(0, w, grid_size):
        draw.line([(x, 0), (x, h)], fill=(128, 128, 128, 100), width=1)
        # Label column
        draw.text((x + 2, 2), str(x // grid_size), fill=(255, 255, 255, 150))
        
    # Draw horizontal grid lines
    for y in range(0, h, grid_size):
        draw.line([(0, y), (w, y)], fill=(128, 128, 128, 100), width=1)
        # Label row
        draw.text((2, y + 2), str(y // grid_size), fill=(255, 255, 255, 150))

    os.makedirs("artifacts", exist_ok=True)
    debug_img.save("artifacts/baloncesto_grid.png")
    print("Baloncesto grid saved to artifacts/baloncesto_grid.png")

if __name__ == "__main__":
    main()
