"""
src/dialogue.py  —  Dialogue system with decision tree
========================================================
**Custom data-structure**: n-ary decision tree where each node is
a dialogue line and its children are the player's reply options.

Choosing a reply navigates down the tree and may trigger
*consequences* (reputation changes, NPC stat changes, items,
mission unlocks).
"""

from __future__ import annotations

import json
import os
import pygame
from settings import (
    UI_BG, UI_PANEL, UI_BORDER, UI_ACCENT,
    UI_TEXT, UI_TEXT_DIM, WHITE, BLACK,
    NOTIF_SUCCESS,
    SCREEN_WIDTH, SCREEN_HEIGHT,
    DATA_DIR,
    Character,
)


# ══════════════════════════════════════════════════════════════
#  DIALOGUE NODE  (n-ary tree node)
# ══════════════════════════════════════════════════════════════

class DialogueNode:
    """A single node in the dialogue tree.

    Attributes
    ----------
    id          : unique identifier
    speaker     : NPC name or "Player"
    text        : what this character says
    choices     : list[DialogueNode]  children = player reply options
    consequences : dict               applied when this node is reached
        Possible keys:
        - "reputation_changes": {"group": delta, …}
        - "npc_stat_changes":   {"npc_id": {"stat": delta, …}, …}
        - "item_received":      {"name": …, "category": …}
        - "mission_unlock":     "mission_id"
        - "xp":                 int
        - "reveal_mask":        "npc_id"
    is_player_choice : bool   True when this is a selectable reply
    """

    def __init__(self, node_id: str = "", speaker: str = "",
                 text: str = "", consequences: dict | None = None,
                 is_player_choice: bool = False):
        self.id               = node_id
        self.speaker          = speaker
        self.text             = text
        self.consequences     = consequences or {}
        self.is_player_choice = is_player_choice
        self.children:  list[DialogueNode] = []
        self.parent:    DialogueNode | None = None

    def add_child(self, child: DialogueNode) -> DialogueNode:
        child.parent = self
        self.children.append(child)
        return child

    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def depth(self) -> int:
        d, n = 0, self
        while n.parent is not None:
            d += 1
            n = n.parent
        return d

    # ── serialisation ─────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "speaker": self.speaker,
            "text": self.text,
            "consequences": self.consequences,
            "is_player_choice": self.is_player_choice,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, d: dict) -> DialogueNode:
        node = cls(
            node_id=d.get("id", ""),
            speaker=d.get("speaker", ""),
            text=d.get("text", ""),
            consequences=d.get("consequences", {}),
            is_player_choice=d.get("is_player_choice", False),
        )
        for child_data in d.get("children", []):
            node.add_child(cls.from_dict(child_data))
        return node

    def __repr__(self):
        return f"DialogueNode({self.id}, '{self.speaker}', children={len(self.children)})"


# ══════════════════════════════════════════════════════════════
#  DIALOGUE TREE  (wraps the root node)
# ══════════════════════════════════════════════════════════════

class DialogueTree:
    """An n-ary dialogue/decision tree.

    Navigation: the system walks from root towards leaves.
    At each "NPC speaks" node, the children represent choices
    the player can pick.  Choosing one moves to that child's
    first NPC-speak child, and so on.
    """

    def __init__(self, root: DialogueNode):
        self.root    = root
        self.current = root

    def get_current_text(self) -> tuple[str, str]:
        """Return ``(speaker, text)`` for the current node."""
        return self.current.speaker, self.current.text

    def get_choices(self) -> list[DialogueNode]:
        """Return available player choices (children flagged as choices)."""
        return [c for c in self.current.children if c.is_player_choice]

    def get_npc_continuation(self) -> DialogueNode | None:
        """If there is exactly one non-choice child, return it (auto-advance)."""
        non_choice = [c for c in self.current.children if not c.is_player_choice]
        return non_choice[0] if len(non_choice) == 1 else None

    def make_choice(self, index: int) -> dict:
        """Navigate to choice *index*.  Returns its consequences dict."""
        choices = self.get_choices()
        if 0 <= index < len(choices):
            self.current = choices[index]
            return dict(self.current.consequences)
        return {}

    def advance(self) -> bool:
        """Try to auto-advance to the next NPC line.
        Returns *False* if at a leaf (dialogue over)."""
        cont = self.get_npc_continuation()
        if cont:
            self.current = cont
            return True
        # If no continuation and no choices, dialogue ends
        if not self.get_choices():
            return False
        return True         # choices exist — wait for player

    def is_finished(self) -> bool:
        return self.current.is_leaf()

    def reset(self):
        self.current = self.root


# ══════════════════════════════════════════════════════════════
#  DIALOGUE SYSTEM  (manages active dialogue + drawing)
# ══════════════════════════════════════════════════════════════

class DialogueSystem:
    """High-level system that loads trees from JSON and drives the
    dialogue UI during the DIALOGUE game state."""

    def __init__(self):
        self.trees:   dict[str, DialogueTree] = {}
        self.active_tree: DialogueTree | None = None
        self.npc      = None
        self.player   = None
        self.reputation = None

        self._finished = False
        
        # NPC Avatars
        self.avatars = {}
        self._load_avatars()

    # ── loading ───────────────────────────────────────────────

    def load_dialogues_from_json(self):
        """Load dialogue trees from ``data/dialogues.json``."""
        path = os.path.join(DATA_DIR, "dialogues.json")
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            for entry in data.get("dialogues", []):
                tree_id = entry.get("id", "")
                root    = DialogueNode.from_dict(entry.get("tree", {}))
                self.trees[tree_id] = DialogueTree(root)
        except (FileNotFoundError, json.JSONDecodeError):
            self._create_defaults()

    def _create_defaults(self):
        """Fallback dialogue trees if JSON is missing."""
        # ── Marcus (Aiden) ──
        root = DialogueNode("m_root", "Marcus Rivera",
                            "Hey, you're the new kid right? Welcome to Ravenside!")
        c1 = DialogueNode("m_c1", "Player", "Thanks! What's this place like?",
                          is_player_choice=True)
        c2 = DialogueNode("m_c2", "Player", "Yeah. Who runs things around here?",
                          is_player_choice=True)
        c1r = DialogueNode("m_c1r", "Marcus Rivera",
                           "It's… mostly fine. Just watch out for the Smile Club.",
                           consequences={"reputation_changes": {"athletes": 5}})
        c2r = DialogueNode("m_c2r", "Marcus Rivera",
                           "Director Walsh is in charge. But Dylan Brooks acts like he owns the halls.",
                           consequences={"xp": 10})
        root.add_child(c1)
        root.add_child(c2)
        c1.add_child(c1r)
        c2.add_child(c2r)
        self.trees["dlg_marcus_aiden"] = DialogueTree(root)

        # ── Marcus (Lena) ──
        root2 = DialogueNode("m2_root", "Marcus Rivera",
                             "Oh hey — you must be Aiden's sister. I'm Marcus.")
        c2a = DialogueNode("m2_c1", "Player", "I'm Lena. What do you know about the network here?",
                           is_player_choice=True)
        c2b = DialogueNode("m2_c2", "Player", "Nice to meet you. Any tips for a new student?",
                           is_player_choice=True)
        c2a_r = DialogueNode("m2_c1r", "Marcus Rivera",
                             "Network? Sophie Chen in the tech club knows way more than me.",
                             consequences={"mission_unlock": "mission_strange_rumours"})
        c2b_r = DialogueNode("m2_c2r", "Marcus Rivera",
                             "Stay low, make friends, and don't attract the wrong attention.",
                             consequences={"reputation_changes": {"athletes": 3}})
        root2.add_child(c2a)
        root2.add_child(c2b)
        c2a.add_child(c2a_r)
        c2b.add_child(c2b_r)
        self.trees["dlg_marcus_lena"] = DialogueTree(root2)

        # ── Sophie (both) ──
        root3 = DialogueNode("s_root", "Sophie Chen",
                             "Hey. You're asking about the school's systems? Be careful who you trust.")
        sc1 = DialogueNode("s_c1", "Player", "I think something shady is going on. Can you help?",
                           is_player_choice=True, consequences={"xp": 15})
        sc2 = DialogueNode("s_c2", "Player", "Never mind, forget I asked.",
                           is_player_choice=True)
        sc1r = DialogueNode("s_c1r", "Sophie Chen",
                            "Meet me in the Computer Lab. I'll show you what I found.",
                            consequences={"reputation_changes": {"tech_club": 10}})
        sc2r = DialogueNode("s_c2r", "Sophie Chen",
                            "Suit yourself. But the truth doesn't stay hidden forever.")
        root3.add_child(sc1)
        root3.add_child(sc2)
        sc1.add_child(sc1r)
        sc2.add_child(sc2r)
        self.trees["dlg_sophie_aiden"] = DialogueTree(root3)
        # Reuse for Lena (shallow copy of tree structure)
        self.trees["dlg_sophie_lena"] = DialogueTree(DialogueNode.from_dict(root3.to_dict()))

        # Generic fallbacks for remaining NPCs
        for npc_id in ("dylan", "emma", "jake", "mia", "walsh", "tyler", "ava", "lucas", "zoe", "noah"):
            for char in ("aiden", "lena"):
                key = f"dlg_{npc_id}_{char}"
                if key not in self.trees:
                    r = DialogueNode(f"{npc_id}_root", npc_id.title(),
                                    "I don't have much to say right now.")
                    self.trees[key] = DialogueTree(r)

    # ── start / stop ──────────────────────────────────────────

    def start_dialogue(self, dialogue_id: str, npc, player, reputation):
        """Begin a dialogue sequence."""
        tree = self.trees.get(dialogue_id)
        if not tree:
            return

        tree.reset()
        self.active_tree = tree
        self.npc         = npc
        self.player      = player
        self.reputation  = reputation
        self._choice_index = 0
        self._all_consequences = []
        self._finished = False
        self._result   = None

    # ── input ─────────────────────────────────────────────────

    def handle_input(self, event: pygame.event.Event):
        if event.type != pygame.KEYDOWN or not self.active_tree:
            return

        choices = self.active_tree.get_choices()
        if choices:
            if event.key in (pygame.K_UP, pygame.K_w):
                self._choice_index = max(0, self._choice_index - 1)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self._choice_index = min(len(choices) - 1, self._choice_index + 1)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                cons = self.active_tree.make_choice(self._choice_index)
                if cons:
                    self._all_consequences.append(cons)
                self._choice_index = 0
                if not self.active_tree.advance():
                    self._finish()
        else:
            # No choices — advance on any key
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if not self.active_tree.advance():
                    self._finish()

    def handle_controller(self, controller):
        """Handle Xbox controller input for dialogue navigation.

        D-pad (cruzeta) up/down: Navigate choices up/down
        A button: Confirm selection / Advance
        B button: Cancel/Exit (if applicable)
        """
        if not self.active_tree:
            return

        choices = self.active_tree.get_choices()
        if choices:
            # D-pad vertical for navigation (cruzeta)
            menu_dir = controller.get_menu_direction()
            if menu_dir == -1:
                self._choice_index = max(0, self._choice_index - 1)
            elif menu_dir == 1:
                self._choice_index = min(len(choices) - 1, self._choice_index + 1)

            # A button to confirm
            if controller.is_confirm_pressed():
                cons = self.active_tree.make_choice(self._choice_index)
                if cons:
                    self._all_consequences.append(cons)
                self._choice_index = 0
                if not self.active_tree.advance():
                    self._finish()
        else:
            # No choices — A button to advance
            if controller.is_confirm_pressed():
                if not self.active_tree.advance():
                    self._finish()

    def _finish(self):
        """End the dialogue, merging all consequences."""
        self._finished = True
        merged: dict = {}
        for cons in self._all_consequences:
            for key, val in cons.items():
                if key in merged and isinstance(val, dict):
                    merged[key].update(val)
                else:
                    merged[key] = val
        self._result = merged
        self.active_tree = None

    # ── update ────────────────────────────────────────────────

    def update(self) -> dict | None:
        """Returns merged consequences dict when dialogue ends."""
        if self._finished:
            r = self._result
            self._result   = None
            self._finished = False
            return r
        return None

        return None

    def _load_avatars(self):
        """Pre-load realistic NPC portraits."""
        try:
            path = "assets/Imagenes realistas personajes/"
            # Scan directory for all PNGs
            if os.path.exists(path):
                for f in os.listdir(path):
                    if f.endswith(".png"):
                        name = f.replace(".png", "")
                        # Store by name (e.g. "Oscar Jimenez")
                        img = pygame.image.load(os.path.join(path, f)).convert_alpha()
                        self.avatars[name] = img
        except:
            pass

    # ── drawing ───────────────────────────────────────────────

    def draw(self, screen: pygame.Surface):
        if not self.active_tree:
            return

        font_name = pygame.font.SysFont("arial", 22, bold=True)
        font_text = pygame.font.SysFont("arial", 20)
        font_choice = pygame.font.SysFont("arial", 20)

        speaker, text = self.active_tree.get_current_text()
        choices = self.active_tree.get_choices()

        # ── dialogue box (bottom of screen) ──
        player_character = getattr(self.player, "character", None)
        player_name = None
        if player_character == Character.AIDEN:
            player_name = "Aiden"
        elif player_character == Character.LENA:
            player_name = "Lena"

        display_speaker = speaker
        is_player_line = False

        if speaker == "Player":
            if player_name:
                display_speaker = player_name
            is_player_line = True
        elif player_name and speaker in ("Aiden", "Lena"):
            # Dialogue assets may always reference Aiden; swap to current protagonist
            if speaker != player_name:
                display_speaker = player_name
            is_player_line = True
        elif player_name and speaker.lower() == player_name.lower():
            is_player_line = True

        is_npc = not is_player_line

        avatar_lookup = {
            "Aiden": "Aiden Parker",
            "Lena": "Lena Aiden",
        }
        avatar_name = avatar_lookup.get(display_speaker, display_speaker)

        has_realistic = avatar_name in self.avatars
        # Show portrait for NPCs, and also for the player if we have a realistic avatar
        show_portrait = is_npc or (is_player_line and has_realistic)

        box_w_offset = 140 if show_portrait else 0

        box_h = 180 if choices else 130
        # If is NPC or player has portrait, move the box right to make room on the left
        box_x = 30 + box_w_offset if show_portrait else 30
        # Move up (from -20 to -60)
        # Reduced width by ~100px to match UI layout (ending where purple line was)
        box = pygame.Rect(box_x, SCREEN_HEIGHT - box_h - 60,
                          SCREEN_WIDTH - 160 - box_w_offset, box_h)
        pygame.draw.rect(screen, UI_PANEL, box, border_radius=12)
        pygame.draw.rect(screen, UI_ACCENT, box, 2, border_radius=12)

        # Speaker name
        screen.blit(font_name.render(display_speaker, True, UI_ACCENT),
                    (box.x + 18, box.y + 12))

        # Text (with word wrap)
        self._draw_wrapped(screen, font_text, text, UI_TEXT,
                           box.x + 18, box.y + 42, box.width - 36)

        # NPC/Player Portrait on the left (Template for all characters with avatars)
        if show_portrait:
            av_radius = 72
            # Positioned to the left of the box, attached
            av_cx = box.left - 87
            av_cy = box.centery
            
            # Circular frame (Light Blue UI_ACCENT)
            pygame.draw.circle(screen, UI_ACCENT, (av_cx, av_cy), av_radius + 4)
            pygame.draw.circle(screen, BLACK, (av_cx, av_cy), av_radius)
            
            if has_realistic:
                # Draw realistic image
                av_img = self.avatars[avatar_name]
                size = av_radius * 2
                av_surf = pygame.Surface((size, size), pygame.SRCALPHA)
                pygame.draw.circle(av_surf, (255, 255, 255), (av_radius, av_radius), av_radius)
                scaled = pygame.transform.smoothscale(av_img, (size, size))
                av_surf.blit(scaled, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
                screen.blit(av_surf, (av_cx - av_radius, av_cy - av_radius))
            else:
                # Fallback: Draw initials in a stylized circle
                pygame.draw.circle(screen, (40, 50, 70), (av_cx, av_cy), av_radius - 2)
                display_name = display_speaker if display_speaker else speaker
                initial = display_name[0].upper() if display_name else "?"
                f_init = pygame.font.SysFont("arial", 48, bold=True)
                txt = f_init.render(initial, True, UI_ACCENT)
                screen.blit(txt, txt.get_rect(center=(av_cx, av_cy)))

        # Choices
        if choices:
            cy = box.y + 90
            for i, ch in enumerate(choices):
                is_sel = (i == self._choice_index)
                col = UI_ACCENT if is_sel else UI_TEXT_DIM
                prefix = "►" if is_sel else "  "
                screen.blit(font_choice.render(f"{prefix} {ch.text}", True, col),
                            (box.x + 30, cy))
                cy += 26

        # Subtitle bar (always visible — accessibility)
        sub_bar = pygame.Rect(0, SCREEN_HEIGHT - 18, SCREEN_WIDTH, 18)
        pygame.draw.rect(screen, BLACK, sub_bar)
        sub_font = pygame.font.SysFont("arial", 14)
        screen.blit(sub_font.render(f"[{display_speaker}] {text}", True, WHITE),
                    (10, SCREEN_HEIGHT - 17))

    @staticmethod
    def _draw_wrapped(screen, font, text, colour, x, y, max_w):
        """Render text with simple word-wrap."""
        words = text.split()
        line  = ""
        for word in words:
            test = f"{line} {word}".strip()
            tw, _ = font.size(test)
            if tw > max_w:
                screen.blit(font.render(line, True, colour), (x, y))
                y += font.get_linesize()
                line = word
            else:
                line = test
        if line:
            screen.blit(font.render(line, True, colour), (x, y))
