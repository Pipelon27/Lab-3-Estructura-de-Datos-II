"""
src/tilemap.py  —  Tile-based floor renderer with prop placement
================================================================
Each Floor gets a TileMap that:
  1. Pre-renders floor tiles into a cached surface
  2. Places prop sprites from JSON layouts
  3. Provides collision rects for solid props
  4. Draws props with Y-sorting (correct overlap)
"""

from __future__ import annotations
import json, os
import pygame
from settings import TILE_SIZE

LAYOUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "layouts")


class Prop:
    """A placed prop sprite with collision info."""

    __slots__ = ("surface", "rect", "collision", "layer", "name")

    def __init__(self, surface: pygame.Surface, world_x: int, world_y: int,
                 collision: str = "none", layer: str = "below",
                 name: str = ""):
        self.surface   = surface
        self.rect      = pygame.Rect(world_x, world_y,
                                     surface.get_width(), surface.get_height())
        self.collision = collision   # "solid" | "partial" | "none"
        self.layer     = layer       # "below" | "above"
        self.name      = name

    @property
    def collision_rect(self) -> pygame.Rect | None:
        if self.collision == "solid":
            return self.rect
        if self.collision == "partial":
            # Smaller hitbox (bottom 60%)
            h = max(4, int(self.rect.height * 0.6))
            return pygame.Rect(self.rect.x, self.rect.bottom - h,
                               self.rect.width, h)
        return None


class TileMap:
    """Tile-based renderer for one floor."""

    def __init__(self, width: int, height: int):
        self.width  = width
        self.height = height
        self.ground_surface: pygame.Surface | None = None
        self.props: list[Prop] = []
        self._collision_rects: list[pygame.Rect] = []
        self._dirty = True

    # ── ground layer ──────────────────────────────────────────

    def build_ground(self, rooms, asset_manager):
        """Pre-render all room floor tiles into one cached surface."""
        self.ground_surface = pygame.Surface(
            (self.width, self.height), pygame.SRCALPHA)
        self.ground_surface.fill((0, 0, 0, 0))

        for room in rooms.values():
            tile = asset_manager.get_room_floor_tile(room.id)
            if tile is None:
                # Fallback: fill with room color
                pygame.draw.rect(self.ground_surface, room.color, room.rect)
                continue
            # Tile the floor inside the room rect
            rx, ry, rw, rh = room.rect
            for ty in range(ry, ry + rh, TILE_SIZE):
                for tx in range(rx, rx + rw, TILE_SIZE):
                    self.ground_surface.blit(tile, (tx, ty))

    # ── props ─────────────────────────────────────────────────

    def load_room_props(self, room, asset_manager):
        """Load and place props for a room from its JSON layout."""
        layout_path = os.path.join(LAYOUT_DIR, f"{room.id}.json")
        if not os.path.isfile(layout_path):
            return

        with open(layout_path, "r", encoding="utf-8") as f:
            layout = json.load(f)

        sprites = asset_manager.load_room_sprites(room.id)
        rx, ry = room.rect.x, room.rect.y

        for entry in layout.get("props", []):
            fname = entry.get("sprite", "")
            surf = sprites.get(fname)
            if surf is None:
                continue
            gx = entry.get("gx", 0)
            gy = entry.get("gy", 0)
            world_x = rx + gx * TILE_SIZE
            world_y = ry + gy * TILE_SIZE
            collision = entry.get("collision", "none")
            layer = entry.get("layer", "below")

            prop = Prop(surf, world_x, world_y, collision, layer, fname)
            self.props.append(prop)

        self._dirty = True

    def get_collision_rects(self) -> list[pygame.Rect]:
        """Return collision rects for all solid/partial props."""
        if self._dirty:
            self._collision_rects = []
            for p in self.props:
                cr = p.collision_rect
                if cr is not None:
                    self._collision_rects.append(cr)
            self._dirty = False
        return self._collision_rects

    # ── drawing ───────────────────────────────────────────────

    def draw_ground(self, screen: pygame.Surface, camera):
        """Blit the pre-rendered ground surface."""
        if self.ground_surface is None:
            return
        sw, sh = screen.get_width(), screen.get_height()
        ox, oy = int(camera.offset.x), int(camera.offset.y)
        # Only blit the visible portion
        src_rect = pygame.Rect(ox, oy, sw, sh)
        src_rect.clamp_ip(pygame.Rect(0, 0, self.width, self.height))
        screen.blit(self.ground_surface, (0, 0), src_rect)

    def draw_props_below(self, screen: pygame.Surface, camera):
        """Draw props on the 'below' layer (rendered before player)."""
        sw, sh = screen.get_width(), screen.get_height()
        for prop in self.props:
            if prop.layer != "below":
                continue
            dr = camera.apply_rect(prop.rect)
            if dr.right < 0 or dr.left > sw or dr.bottom < 0 or dr.top > sh:
                continue
            screen.blit(prop.surface, dr)

    def draw_props_above(self, screen: pygame.Surface, camera):
        """Draw props on the 'above' layer (rendered after player)."""
        sw, sh = screen.get_width(), screen.get_height()
        for prop in self.props:
            if prop.layer != "above":
                continue
            dr = camera.apply_rect(prop.rect)
            if dr.right < 0 or dr.left > sw or dr.bottom < 0 or dr.top > sh:
                continue
            screen.blit(prop.surface, dr)
