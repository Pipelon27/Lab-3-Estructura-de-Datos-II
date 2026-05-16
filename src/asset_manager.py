"""
src/asset_manager.py  —  Sprite loading, caching, zone management
==================================================================
Loads spritesheets and per-room singles from BehindTheSmile_Assets.
Provides tile lookup, zone-based caching, and unloading.
"""

from __future__ import annotations
import os
import pygame
from settings import TILE_SIZE

ASSET_BASE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "assets", "BehindTheSmile_Assets", "BehindTheSmile_Assets",
)

# ── Floor-tile presets  (col, row) in Room_Builder sheet ──────
# Inspected visually — each row-pair is a colour set.
FLOOR_PRESETS = {
    "wood_warm":    (1, 9),
    "wood_dark":    (1, 11),
    "wood_red":     (1, 13),
    "tile_cream":   (1, 5),
    "tile_mint":    (1, 7),
    "tile_warm":    (1, 3),
    "tile_gray":    (1, 15),
    "tile_khaki":   (1, 17),
    "tile_olive":   (1, 19),
    "brick_red":    (11, 3),
    "stone_gray":   (13, 5),
    "checker":      (11, 5),
    "herringbone":  (13, 7),
    "concrete":     (1, 21),
}

# ── Room → asset folder mapping ──────────────────────────────
ROOM_ASSET_FOLDER = {
    # floor 1
    "f1_computer_lab":    "floor1/computer_lab",
    "f1_infirmary":       "floor1/nurse",
    "f1_auditorium":      "floor1/auditorium",
    "f1_library":         "floor1/library",
    "f1_cafeteria":       "floor1/cafeteria",
    "f1_counselor":       "common",
    "f1_main_hall":       "common",
    "f1_reception":       "common",
    # floor 2
    "f2_art_room":        "floor2/art_room",
    "f2_music_room":      "floor2/music_room",
    "f2_science_lab":     "floor2/science",
    "f2_conference":      "floor2/conference",
    "f2_director":        "common",
    "f2_admin":           "common",
    "f2_corridor":        "common",
    "f2_classrooms":      "common",
    # basement
    "b_smile_club":       "basement/meeting_room",
    "b_server_room":      "basement/servers",
    "b_surveillance":     "basement/security_room",
    "b_detention":        "basement/cells",
    "b_terminal":         "basement/final_terminal",
    # rooftop
    "rt_terrace":         "common",
    "rt_benches":         "common",
}

# ── Room → floor tile preset ─────────────────────────────────
ROOM_FLOOR_TILE = {
    "f1_computer_lab":  "tile_gray",
    "f1_infirmary":     "tile_mint",
    "f1_auditorium":    "wood_dark",
    "f1_library":       "wood_warm",
    "f1_cafeteria":     "checker",
    "f1_counselor":     "wood_warm",
    "f1_main_hall":     "tile_cream",
    "f1_reception":     "tile_cream",
    "f1_stairs_2f":     "stone_gray",
    "f1_basement_stairs": "stone_gray",
    "f2_art_room":      "wood_red",
    "f2_music_room":    "wood_dark",
    "f2_science_lab":   "tile_gray",
    "f2_conference":    "wood_warm",
    "f2_director":      "wood_red",
    "f2_admin":         "tile_khaki",
    "f2_corridor":      "tile_cream",
    "f2_classrooms":    "tile_cream",
    "f2_roof_stairs":   "stone_gray",
    "f2_stairs_1f":     "stone_gray",
    "b_smile_club":     "concrete",
    "b_server_room":    "tile_gray",
    "b_surveillance":   "tile_gray",
    "b_detention":      "concrete",
    "b_terminal":       "tile_gray",
    "b_stairs_up":      "stone_gray",
    "rt_stairs_down":   "stone_gray",
    "rt_terrace":       "stone_gray",
    "rt_benches":       "stone_gray",
}


class AssetManager:
    """Central loader for all game sprites."""

    def __init__(self):
        self._zone_cache: dict[str, dict[str, pygame.Surface]] = {}
        self._sheet_cache: dict[str, dict[tuple, pygame.Surface]] = {}
        self._floor_tile_cache: dict[str, pygame.Surface] = {}

        # Pre-load the two main spritesheets
        self.room_builder = self._load_sheet(
            os.path.join(ASSET_BASE, "campus", "Room_Builder_free_32x32.png"))
        self.interiors = self._load_sheet(
            os.path.join(ASSET_BASE, "campus", "Interiors_free_32x32.png"))

    # ── spritesheet slicing ───────────────────────────────────

    def _load_sheet(self, path: str) -> dict[tuple, pygame.Surface]:
        if path in self._sheet_cache:
            return self._sheet_cache[path]
        sheet = pygame.image.load(path).convert_alpha()
        cols = sheet.get_width() // TILE_SIZE
        rows = sheet.get_height() // TILE_SIZE
        tiles: dict[tuple, pygame.Surface] = {}
        for r in range(rows):
            for c in range(cols):
                rect = pygame.Rect(c * TILE_SIZE, r * TILE_SIZE,
                                   TILE_SIZE, TILE_SIZE)
                tiles[(c, r)] = sheet.subsurface(rect).copy()
        self._sheet_cache[path] = tiles
        return tiles

    # ── tile helpers ──────────────────────────────────────────

    def get_floor_tile(self, preset_name: str) -> pygame.Surface | None:
        """Get a 32×32 floor tile by preset name."""
        if preset_name in self._floor_tile_cache:
            return self._floor_tile_cache[preset_name]
        coord = FLOOR_PRESETS.get(preset_name)
        if coord is None:
            return None
        tile = self.room_builder.get(coord)
        if tile:
            self._floor_tile_cache[preset_name] = tile
        return tile

    def get_room_floor_tile(self, room_id: str) -> pygame.Surface | None:
        """Get the floor tile assigned to a specific room."""
        preset = ROOM_FLOOR_TILE.get(room_id)
        if preset:
            return self.get_floor_tile(preset)
        return self.get_floor_tile("tile_cream")  # fallback

    # ── per-room singles ──────────────────────────────────────

    def load_room_sprites(self, room_id: str) -> dict[str, pygame.Surface]:
        """Load all single-sprite PNGs for a room."""
        folder = ROOM_ASSET_FOLDER.get(room_id)
        if not folder:
            return {}
        cache_key = f"{room_id}:{folder}"
        if cache_key in self._zone_cache:
            return self._zone_cache[cache_key]

        sprites: dict[str, pygame.Surface] = {}
        full_path = os.path.join(ASSET_BASE, folder)
        if os.path.isdir(full_path):
            for fname in sorted(os.listdir(full_path)):
                if fname.lower().endswith(".png"):
                    fp = os.path.join(full_path, fname)
                    sprites[fname] = pygame.image.load(fp).convert_alpha()
        self._zone_cache[cache_key] = sprites
        return sprites

    def unload_zone(self, room_id: str):
        """Free cached sprites for a room."""
        folder = ROOM_ASSET_FOLDER.get(room_id, "")
        key = f"{room_id}:{folder}"
        self._zone_cache.pop(key, None)

    # ── interiors sheet helpers ───────────────────────────────

    def get_interior(self, col: int, row: int) -> pygame.Surface | None:
        """Get a tile from the Interiors spritesheet."""
        return self.interiors.get((col, row))
