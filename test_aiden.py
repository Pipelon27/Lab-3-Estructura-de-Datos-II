import pygame
import sys
import os

# Initialize pygame
pygame.init()
screen = pygame.display.set_mode((800, 600))
pygame.display.set_caption("Test Aiden Sprite")

from src.player import Aiden

# Create Aiden
aiden = Aiden(400, 300)

print(f"Aiden created successfully.")
print(f"Loaded animations: {list(aiden.animations.keys())}")
if aiden.image:
    print(f"Default image size: {aiden.image.get_size()}")
else:
    print("Warning: aiden.image is None")

pygame.quit()
