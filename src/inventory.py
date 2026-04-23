"""
src/inventory.py  —  Categorised item inventory (custom list)
==============================================================
The inventory is backed by a plain Python **list** (no external
library).  Items are grouped by ``ItemCategory`` and support
stacking, usage callbacks, and serialisation for network sync.
"""

from __future__ import annotations

import pygame
from settings import (
    ItemCategory,
    UI_BG, UI_PANEL, UI_BORDER, UI_ACCENT,
    UI_TEXT, UI_TEXT_DIM, WHITE,
    NOTIF_SUCCESS, NOTIF_WARNING,
    SCREEN_WIDTH, SCREEN_HEIGHT,
)


# ══════════════════════════════════════════════════════════════
#  ITEM
# ══════════════════════════════════════════════════════════════

class Item:
    """A single inventory item.

    Parameters
    ----------
    name        : display name
    category    : ItemCategory enum
    description : tooltip text
    stackable   : whether multiple units occupy one slot
    quantity    : current stack count
    usable      : can the player "use" this item?
    use_effect  : dict of stat changes when used (e.g. {"health": 20})
    """

    def __init__(self, name: str, category: ItemCategory,
                 description: str = "", stackable: bool = True,
                 quantity: int = 1, usable: bool = False,
                 use_effect: dict | None = None):
        self.name        = name
        self.category    = category
        self.description = description
        self.stackable   = stackable
        self.quantity    = quantity
        self.usable      = usable
        self.use_effect  = use_effect or {}

    def to_dict(self) -> dict:
        """Serialise for network / JSON."""
        return {
            "name":        self.name,
            "category":    self.category.value,
            "description": self.description,
            "stackable":   self.stackable,
            "quantity":    self.quantity,
            "usable":      self.usable,
            "use_effect":  self.use_effect,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Item:
        """Deserialise from a dict."""
        return cls(
            name        = data["name"],
            category    = ItemCategory(data["category"]),
            description = data.get("description", ""),
            stackable   = data.get("stackable", True),
            quantity    = data.get("quantity", 1),
            usable      = data.get("usable", False),
            use_effect  = data.get("use_effect", {}),
        )

    def __repr__(self):
        return f"Item({self.name} x{self.quantity})"


# ══════════════════════════════════════════════════════════════
#  INVENTORY  (list-based, custom implementation)
# ══════════════════════════════════════════════════════════════

class Inventory:
    """Player inventory backed by a Python list.

    Provides add / remove / use / search / filter operations.

    Attributes
    ----------
    items       : list[Item]
    max_capacity : maximum number of distinct item slots
    selected     : index currently highlighted in the UI
    """

    MAX_CAPACITY = 30

    def __init__(self, max_capacity: int = MAX_CAPACITY):
        self.items:       list[Item] = []
        self.max_capacity = max_capacity
        self.selected     = 0

    # ── core operations ───────────────────────────────────────

    def add_item(self, name: str, category: ItemCategory,
                 description: str = "", quantity: int = 1,
                 stackable: bool = True, usable: bool = False,
                 use_effect: dict | None = None) -> bool:
        """Add an item (or stack onto existing).  Returns *True* on success."""
        # Try stacking first
        if stackable:
            for item in self.items:
                if item.name == name and item.stackable:
                    item.quantity += quantity
                    return True

        # New slot
        if len(self.items) >= self.max_capacity:
            return False

        self.items.append(Item(
            name, category, description,
            stackable, quantity, usable, use_effect,
        ))
        return True

    def add_item_obj(self, item: Item) -> bool:
        """Add a pre-built Item object."""
        return self.add_item(
            item.name, item.category, item.description,
            item.quantity, item.stackable, item.usable, item.use_effect,
        )

    def remove_item(self, name: str, quantity: int = 1) -> bool:
        """Remove *quantity* units of *name*.  Returns *True* on success."""
        for i, item in enumerate(self.items):
            if item.name == name:
                if item.quantity > quantity:
                    item.quantity -= quantity
                    return True
                elif item.quantity == quantity:
                    self.items.pop(i)
                    if self.selected >= len(self.items) and self.selected > 0:
                        self.selected -= 1
                    return True
                else:
                    return False          # not enough
        return False

    def use_item(self, name: str, player) -> bool:
        """Use an item, applying its effect to *player*.  Returns *True* on success."""
        for item in self.items:
            if item.name == name and item.usable:
                for stat, value in item.use_effect.items():
                    cur = getattr(player, stat, None)
                    if cur is not None:
                        setattr(player, stat, cur + value)
                self.remove_item(name, 1)
                return True
        return False

    def has_item(self, name: str, quantity: int = 1) -> bool:
        """Check whether the inventory contains ≥ *quantity* of *name*."""
        for item in self.items:
            if item.name == name and item.quantity >= quantity:
                return True
        return False

    def get_item(self, name: str) -> Item | None:
        for item in self.items:
            if item.name == name:
                return item
        return None

    def get_by_category(self, category: ItemCategory) -> list[Item]:
        """Return all items of a given category."""
        return [it for it in self.items if it.category == category]

    def count(self) -> int:
        """Total number of distinct item slots used."""
        return len(self.items)

    def clear(self):
        self.items.clear()
        self.selected = 0

    # ── serialisation ─────────────────────────────────────────

    def to_list(self) -> list[dict]:
        return [it.to_dict() for it in self.items]

    def from_list(self, data: list[dict]):
        """Replace inventory contents from serialised data."""
        self.items = [Item.from_dict(d) for d in data]
        self.selected = 0

    # ── input handling (INVENTORY_SCREEN state) ───────────────

    def handle_input(self, event: pygame.event.Event):
        """Navigate the inventory list and use items."""
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_UP:
            self.selected = max(0, self.selected - 1)
        elif event.key == pygame.K_DOWN:
            self.selected = min(len(self.items) - 1, self.selected + 1)
        elif event.key == pygame.K_DELETE or event.key == pygame.K_BACKSPACE:
            if self.items:
                name = self.items[self.selected].name
                self.remove_item(name, 1)

    # ── drawing ───────────────────────────────────────────────

    def draw(self, screen: pygame.Surface):
        """Render the full-screen inventory panel."""
        screen.fill(UI_BG)

        font_title = pygame.font.SysFont("arial", 34, bold=True)
        font_item  = pygame.font.SysFont("arial", 22)
        font_desc  = pygame.font.SysFont("arial", 16)

        screen.blit(
            font_title.render(f"Inventory  ({self.count()}/{self.max_capacity})",
                              True, UI_ACCENT),
            (30, 20),
        )

        if not self.items:
            screen.blit(
                font_item.render("Your inventory is empty.", True, UI_TEXT_DIM),
                (30, 80),
            )
        else:
            y = 70
            for i, item in enumerate(self.items):
                is_sel  = (i == self.selected)
                colour  = UI_ACCENT if is_sel else UI_TEXT
                prefix  = "►" if is_sel else " "
                cat     = item.category.value.upper()
                line    = f"{prefix}  [{cat}] {item.name}  x{item.quantity}"
                surf    = font_item.render(line, True, colour)
                rx, ry  = 30, y

                if is_sel:
                    bg = pygame.Rect(rx - 4, ry - 2, SCREEN_WIDTH - 60, 28)
                    pygame.draw.rect(screen, UI_PANEL, bg, border_radius=5)
                    pygame.draw.rect(screen, colour, bg, 1, border_radius=5)
                    # description
                    screen.blit(
                        font_desc.render(item.description, True, UI_TEXT),
                        (30, SCREEN_HEIGHT - 70),
                    )

                screen.blit(surf, (rx, ry))
                y += 30

        hint = font_desc.render(
            "↑↓ Navigate  |  DEL Discard  |  ESC Close", True, UI_TEXT_DIM
        )
        screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 25)))

    def __repr__(self):
        return f"Inventory({self.count()} items)"
