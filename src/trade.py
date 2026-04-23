"""
src/trade.py  —  Item trading system
======================================
Handles item exchanges between the player and an NPC.
Trade success depends on the NPC's relationship stats with the
player (friendship and trust affect willingness).
"""

from __future__ import annotations

import pygame
from settings import (
    UI_BG, UI_PANEL, UI_BORDER, UI_ACCENT,
    UI_TEXT, UI_TEXT_DIM, WHITE, BLACK,
    NOTIF_SUCCESS, NOTIF_WARNING, NOTIF_ERROR,
    SCREEN_WIDTH, SCREEN_HEIGHT,
    ItemCategory,
)


class TradeSystem:
    """Full-screen trade interface between player and NPC.

    Workflow
    --------
    1. ``start_trade(player, npc, inventory, npc_items, relationship)``
    2. Player navigates with ↑/↓, selects offer/request with ENTER
    3. ``confirm_trade()`` evaluates willingness and executes
    """

    def __init__(self):
        self.active       = False
        self.player       = None
        self.npc          = None
        self.inventory    = None
        self.npc_items:   list[dict] = []
        self.relationship = None        # RelationshipEdge

        # UI state
        self._panel  = "player"          # "player" | "npc"
        self._sel_p  = 0                 # player-side cursor
        self._sel_n  = 0                 # npc-side cursor
        self._offer:  dict | None = None # item player offers
        self._request: dict | None = None # item player requests
        self._message = ""
        self._result: str | None = None  # "done" / "cancel"

    # ── lifecycle ─────────────────────────────────────────────

    def start_trade(self, player, npc, inventory, npc_items: list[dict],
                    relationship=None):
        """Open the trade screen.

        *npc_items* is a list of dicts: ``{"name", "category", "description"}``.
        """
        self.active       = True
        self.player       = player
        self.npc          = npc
        self.inventory    = inventory
        self.npc_items    = npc_items
        self.relationship = relationship
        self._panel       = "player"
        self._sel_p       = 0
        self._sel_n       = 0
        self._offer       = None
        self._request     = None
        self._message     = "Select an item to offer, then one to request."
        self._result      = None

    # ── input ─────────────────────────────────────────────────

    def handle_input(self, event: pygame.event.Event):
        if event.type != pygame.KEYDOWN or not self.active:
            return

        if event.key == pygame.K_ESCAPE:
            self._result = "cancel"
            self.active  = False
            return

        if event.key == pygame.K_TAB:
            self._panel = "npc" if self._panel == "player" else "player"
            return

        if event.key == pygame.K_UP:
            if self._panel == "player":
                self._sel_p = max(0, self._sel_p - 1)
            else:
                self._sel_n = max(0, self._sel_n - 1)
        elif event.key == pygame.K_DOWN:
            if self._panel == "player":
                self._sel_p = min(len(self.inventory.items) - 1, self._sel_p)
            else:
                self._sel_n = min(len(self.npc_items) - 1, self._sel_n)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._select_item()
        elif event.key == pygame.K_t:
            self._confirm_trade()

    def handle_click(self, pos: tuple[int, int]):
        """Handle mouse click in trade screen (not used yet)."""
        pass

    def _select_item(self):
        """Mark the currently highlighted item as offer or request."""
        if self._panel == "player" and self.inventory.items:
            item = self.inventory.items[self._sel_p]
            self._offer = {"name": item.name, "category": item.category.value}
            self._message = f"Offering: {item.name}.  TAB → NPC side, pick request."
        elif self._panel == "npc" and self.npc_items:
            item = self.npc_items[self._sel_n]
            self._request = item
            self._message = f"Requesting: {item['name']}.  Press T to trade."

    def _confirm_trade(self):
        """Evaluate willingness and execute the trade."""
        if not self._offer or not self._request:
            self._message = "Select both an offer AND a request first."
            return

        willingness = self._evaluate_willingness()

        if willingness >= 50:
            # Execute trade
            self.inventory.remove_item(self._offer["name"], 1)
            self.inventory.add_item(
                self._request["name"],
                ItemCategory(self._request.get("category", "special")),
                self._request.get("description", ""),
            )
            # Improve relationship
            if self.relationship:
                self.relationship.modify("friendship", 5)
                self.relationship.modify("trust", 3)

            self._message = "Trade successful! 🤝"
            self._result  = "done"
            self.active   = False
        else:
            self._message = f"{self.npc.name} refused the trade. (Willingness: {willingness}%)"
            # Slightly decrease relationship on push
            if self.relationship:
                self.relationship.modify("trust", -2)

    def _evaluate_willingness(self) -> int:
        """Return 0–100 willingness based on relationship stats."""
        if not self.relationship:
            return 50     # neutral if unknown

        base = 30
        base += self.relationship.friendship * 0.3
        base += self.relationship.trust * 0.2
        base -= self.relationship.suspicion * 0.15

        # Player's trade bonus (Lena skill)
        bonus = getattr(self.player, "trade_bonus", 0)
        base += bonus

        return int(max(0, min(100, base)))

    # ── update ────────────────────────────────────────────────

    def update(self) -> str | None:
        """Returns ``"done"`` / ``"cancel"`` when trade ends."""
        return self._result

    # ── drawing ───────────────────────────────────────────────

    def draw(self, screen: pygame.Surface):
        if not self.active and self._result is None:
            return

        screen.fill(UI_BG)

        font_title = pygame.font.SysFont("arial", 32, bold=True)
        font_item  = pygame.font.SysFont("arial", 22)
        font_sm    = pygame.font.SysFont("arial", 16)

        npc_name = self.npc.name if self.npc else "NPC"

        # Title
        screen.blit(
            font_title.render(f"Trade with {npc_name}", True, UI_ACCENT),
            (30, 15),
        )

        half_w = SCREEN_WIDTH // 2 - 20
        panel_h = SCREEN_HEIGHT - 160

        # ── Player panel ──
        p_rect = pygame.Rect(10, 60, half_w, panel_h)
        sel_col_p = UI_ACCENT if self._panel == "player" else UI_BORDER
        pygame.draw.rect(screen, UI_PANEL, p_rect, border_radius=8)
        pygame.draw.rect(screen, sel_col_p, p_rect, 2, border_radius=8)
        screen.blit(font_item.render("Your Items", True, WHITE), (20, 68))

        y = 100
        for i, item in enumerate(self.inventory.items):
            is_sel = (self._panel == "player" and i == self._sel_p)
            col = UI_ACCENT if is_sel else UI_TEXT
            prefix = "►" if is_sel else " "
            offered = " [OFFER]" if (self._offer and self._offer["name"] == item.name) else ""
            line = f"{prefix} {item.name} x{item.quantity}{offered}"
            screen.blit(font_sm.render(line, True, col), (20, y))
            y += 24

        # ── NPC panel ──
        n_rect = pygame.Rect(SCREEN_WIDTH // 2 + 10, 60, half_w, panel_h)
        sel_col_n = UI_ACCENT if self._panel == "npc" else UI_BORDER
        pygame.draw.rect(screen, UI_PANEL, n_rect, border_radius=8)
        pygame.draw.rect(screen, sel_col_n, n_rect, 2, border_radius=8)
        screen.blit(font_item.render(f"{npc_name}'s Items", True, WHITE),
                    (SCREEN_WIDTH // 2 + 20, 68))

        y = 100
        for i, item in enumerate(self.npc_items):
            is_sel = (self._panel == "npc" and i == self._sel_n)
            col = UI_ACCENT if is_sel else UI_TEXT
            prefix = "►" if is_sel else " "
            requested = " [REQUEST]" if (self._request and self._request["name"] == item["name"]) else ""
            line = f"{prefix} {item['name']}{requested}"
            screen.blit(font_sm.render(line, True, col),
                        (SCREEN_WIDTH // 2 + 20, y))
            y += 24

        # ── Message ──
        msg_col = NOTIF_SUCCESS if "successful" in self._message else UI_TEXT
        screen.blit(font_item.render(self._message, True, msg_col),
                    (30, SCREEN_HEIGHT - 80))

        # Controls
        screen.blit(font_sm.render(
            "TAB Switch  |  ENTER Select  |  T Confirm Trade  |  ESC Cancel",
            True, UI_TEXT_DIM),
            (SCREEN_WIDTH // 2 - 220, SCREEN_HEIGHT - 30))
