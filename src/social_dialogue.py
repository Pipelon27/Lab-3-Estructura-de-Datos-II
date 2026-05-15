"""
src/social_dialogue.py  —  Social interaction state machine
=============================================================
Core dialogue manager for NPC social interactions.
Drives the 3-option choice cycle, enforces stability rules,
and manages state transitions through the interaction flow.
"""

from __future__ import annotations

import random
from enum import Enum, auto
import pygame
from settings import SOCIAL_COOLDOWN, GameState


class InteractionState(Enum):
    """States of a social interaction."""
    IDLE = auto()              # No active interaction
    APPROACHING = auto()       # Player in range, prompt shown
    ACTIVE = auto()            # UI open, waiting for input
    WAITING_CHOICE = auto()    # Player selecting option
    SHOWING_REACTION = auto()  # NPC reacting to player's choice
    RESOLVING = auto()         # Applying consequences / timer
    CLOSING = auto()           # Fading out


class SocialDialogueManager:
    """Manages active NPC social interactions with state machine & stability rules.

    Responsibilities:
    - Own the active conversation state (singleton lock)
    - Generate contextual NPC opening lines
    - Generate NPC reaction lines after player choice
    - Handle 3-option response cycle
    - Apply interaction consequences via ReputationManager
    - Enforce stability rules (cooldowns, locks, etc.)

    Only ONE interaction can be active at a time.
    """

    # ── NPC OPENING LINES ──────────────────────────────────────
    # Keyed by (group, emotional_state)
    NPC_LINES = {
        # Athletes
        ("athletes", "neutral"):  [
            "You again? What do you want?",
            "Hey. Need something?",
            "Sup. Make it quick.",
            "I was just thinking about practice… what's up?",
        ],
        ("athletes", "open"):     [
            "Oh hey! Good to see you.",
            "What's going on? I've got a minute.",
            "You caught me at a good time!",
        ],
        ("athletes", "nervous"):  [
            "Stay back, okay?",
            "I don't want any trouble…",
            "Please, just leave me alone.",
        ],
        ("athletes", "hostile"):  [
            "Back off. I'm serious.",
            "Get away from me right now.",
        ],

        # Tech Club
        ("tech_club", "neutral"): [
            "Hello. Can I help you with something?",
            "Yes? I'm a bit busy but go ahead.",
            "Oh — I didn't see you there.",
        ],
        ("tech_club", "open"):    [
            "Good to see you! What's going on?",
            "Oh, it's you. I was hoping you'd stop by.",
            "Hey! What can I do for you?",
        ],
        ("tech_club", "nervous"): [
            "I… I'm not sure I want to talk right now.",
            "Um, could you give me a moment?",
        ],
        ("tech_club", "hostile"): [
            "I really don't want to talk to you.",
            "Please, just go.",
        ],

        # Populars
        ("populars", "neutral"):  [
            "What? Can you not?",
            "Is there a reason you're talking to me?",
            "Ugh, what now?",
        ],
        ("populars", "open"):     [
            "Oh hey! How are you?",
            "Oh hi! You're actually kind of fun to talk to.",
            "Hey there! What's new?",
        ],
        ("populars", "nervous"):  [
            "I'm super busy right now, so…",
            "Can this wait? I have places to be.",
        ],
        ("populars", "hostile"):  [
            "Get away from me!",
            "Don't talk to me.",
        ],

        # Academics
        ("academics", "neutral"): [
            "Yes? Did you need something?",
            "I'm in the middle of reading, but… what is it?",
            "Hello. This better be important.",
        ],
        ("academics", "open"):    [
            "Oh, it's you! I'm glad you're here.",
            "Good timing — I could use a break. What's up?",
            "Hey! I was just thinking about you.",
        ],
        ("academics", "nervous"): [
            "I… what do you want?",
            "Can we talk about this later? Please?",
        ],
        ("academics", "hostile"): [
            "I really don't want to see you right now.",
            "Leave me alone.",
        ],

        # Rebels
        ("rebels", "neutral"):    [
            "What? What do you want?",
            "Yeah? Speak up.",
            "You interrupting something?",
        ],
        ("rebels", "open"):       [
            "Hey, you! I'm actually glad to see you.",
            "What's happening? It's been a minute.",
            "Oh, it's you. Cool.",
        ],
        ("rebels", "nervous"):    [
            "Don't… don't come any closer.",
            "Please, just go. I'm asking nicely.",
        ],
        ("rebels", "hostile"):    [
            "Get lost.",
            "I said leave me alone!",
        ],

        # Outsiders
        ("outsiders", "neutral"): [
            "Hi? Can I help you?",
            "Oh… um, what's up?",
            "I wasn't expecting anyone. What is it?",
        ],
        ("outsiders", "open"):    [
            "Oh hey! I'm really happy to see you.",
            "What's new? I've been hoping someone would come by.",
            "Oh! You actually came to talk to me?",
        ],
        ("outsiders", "nervous"): [
            "Oh no… is something wrong?",
            "I didn't expect this at all…",
        ],
        ("outsiders", "hostile"): [
            "Please leave me alone.",
            "I don't want to deal with this right now.",
        ],
    }

    # ── NPC REACTION LINES ─────────────────────────────────────
    # Keyed by (group, action)  — emotional_state not needed here,
    # player already sees the outcome in the delta display.
    REACTION_LINES = {
        # RESPOND reactions
        ("athletes", "respond"):    [
            "That's actually pretty cool of you.",
            "Huh, didn't expect that. Respect.",
            "Okay, I appreciate that.",
        ],
        ("tech_club", "respond"):   [
            "That's… really thoughtful. Thank you.",
            "Oh! I wasn't expecting that. Nice.",
            "Appreciated. Genuinely.",
        ],
        ("populars", "respond"):    [
            "Okay, I'll give you that. Good answer.",
            "Hmm. Maybe you're not so bad.",
            "That was… actually kind of sweet.",
        ],
        ("academics", "respond"):   [
            "That's a genuinely good point. I respect it.",
            "Okay, okay. Well said.",
            "I didn't expect that. Thank you.",
        ],
        ("rebels", "respond"):      [
            "Hah. Alright, I see you.",
            "That's fair. I can respect that.",
            "Okay, cool. You're alright.",
        ],
        ("outsiders", "respond"):   [
            "Oh wow, really? That's… that means a lot.",
            "Thank you. I needed to hear that.",
            "I… I wasn't expecting that. Thanks.",
        ],

        # IGNORE reactions
        ("athletes", "ignore"):     [
            "Seriously? Whatever, man.",
            "Cool, just pretend I don't exist.",
            "Wow. Okay. Nice.",
        ],
        ("tech_club", "ignore"):    [
            "…Okay then.",
            "That was rude. Just so you know.",
            "Fine. I'll remember this.",
        ],
        ("populars", "ignore"):     [
            "Excuse me?! The nerve.",
            "Don't think I'll forget this.",
            "Wow. Okay. Bye.",
        ],
        ("academics", "ignore"):    [
            "That was completely unnecessary.",
            "…I see how it is.",
            "Noted. Very mature.",
        ],
        ("rebels", "ignore"):       [
            "Oh, that's how we're doing this?",
            "Cool. Whatever.",
            "Yeah, figures.",
        ],
        ("outsiders", "ignore"):    [
            "Oh… okay. That's fine.",
            "I guess I shouldn't be surprised.",
            "…That hurt a little. Not that you care.",
        ],

        # INTIMIDATE reactions
        ("athletes", "intimidate"): [
            "Hey! That is NOT okay!",
            "Back off or this gets physical.",
            "You really want to go there?",
        ],
        ("tech_club", "intimidate"):[
            "W-whoa, that's way out of line!",
            "That's… that's really not cool.",
            "Leave me alone or I'm reporting this!",
        ],
        ("populars", "intimidate"): [
            "How DARE you! Do you know who I am?",
            "You are DONE at this school.",
            "That was a huge mistake. Trust me.",
        ],
        ("academics", "intimidate"):[
            "That is completely unacceptable behavior!",
            "I'm reporting this to the administration.",
            "Are you serious right now?!",
        ],
        ("rebels", "intimidate"):   [
            "Oh you think that scares me?",
            "Try it. See what happens.",
            "Yeah, you should go.",
        ],
        ("outsiders", "intimidate"):[
            "Please… please just stop.",
            "Why are you doing this?",
            "Just leave me alone…",
        ],
    }

    def __init__(self):
        self.state = InteractionState.IDLE
        self._active_npc = None          # Current NPC (singleton lock)
        self._player = None              # Reference to player for distance checks
        self._selected_option_idx = 0    # 0 = IGNORE, 1 = RESPOND, 2 = INTIMIDATE
        self._available_options = ["ignore", "respond", "intimidate"]
        self._npc_line = ""              # Current NPC opening line
        self._reaction_line = ""         # NPC reaction after player choice
        self._cooldown_timer: dict[str, float] = {}  # npc_id → remaining cooldown
        self._resolving_timer = 0.0      # Timer during RESOLVING/SHOWING_REACTION state
        self._visible = False             # UI visibility flag
        self.reputation_manager = None   # Will be set by Game
        self.social_ui = None            # Will be set by Game
        self.conversation_active = False # Global lock for interaction

    # ── PUBLIC API ─────────────────────────────────────────────

    def try_start(self, npc, player) -> bool:
        """Attempt to start an interaction with an NPC.

        Checks:
        - No active interaction
        - NPC cooldown expired
        - Player is close enough

        Returns True if interaction started, False otherwise.
        """
        if self.conversation_active:
            print("[SocialSystem] Interaction blocked: conversation already active")
            return False

        if self.state != InteractionState.IDLE:
            print(f"[SocialSystem] Interaction blocked: state is {self.state.name}, not IDLE")
            return False

        # Validate external dependencies
        if npc is None:
            print("[SocialSystem] Interaction blocked: NPC is None")
            return False

        if self.social_ui is None:
            print("[SocialSystem] Interaction blocked: Missing social UI")
            return False

        if self.reputation_manager is None:
            print("[SocialSystem] Interaction blocked: Missing reputation manager")
            return False

        # Check cooldown
        if npc.id in self._cooldown_timer and self._cooldown_timer[npc.id] > 0:
            return False

        # Set as active
        self._active_npc = npc
        self._player = player
        self._selected_option_idx = 0
        self._npc_line = self._generate_npc_line(npc)

        print(f"[SocialSystem] Attempting interaction with {npc.name}")

        # Generate options with deltas using dry_run (NO mutation)
        options_data = self._get_options_with_deltas()

        # Update state lock
        self.conversation_active = True
        self.state = InteractionState.ACTIVE
        self._visible = True

        print("[SocialSystem] Dialogue UI created")

        # Show UI with the NPC opening line
        if self.social_ui:
            self.social_ui.show(npc, options_data)
            self.social_ui.set_npc_line(self._npc_line)

        return True

    def force_close(self):
        """Safe cleanup — called on ESC, death, or state change.

        Resets all state without applying consequences.
        """
        if self.social_ui:
            self.social_ui.hide()
        self.state = InteractionState.IDLE
        self._active_npc = None
        self._player = None
        self._visible = False
        self._selected_option_idx = 0
        self.conversation_active = False
        print("[SocialSystem] Dialogue closed successfully")

    def confirm_choice(self):
        """Player confirmed their selected option.

        Triggers:
        1. NPC memory update
        2. Reputation delta application (real mutation)
        3. Individual NPC stat update
        4. Show NPC reaction line
        5. Transition to SHOWING_REACTION
        """
        if not self._active_npc:
            return

        action = self._available_options[self._selected_option_idx]

        # Update NPC social memory
        self._active_npc.update_social_memory(action)

        # Apply group reputation consequences (real mutation)
        deltas = []
        if self.reputation_manager:
            deltas = self.reputation_manager.apply_interaction(
                self._active_npc.group.value, action, self._active_npc.id,
                dry_run=False
            )
            # Apply individual NPC personal stat changes
            self.reputation_manager.apply_individual_npc_stats(self._active_npc, action)

        # Generate NPC reaction line
        self._reaction_line = self._generate_reaction_line(self._active_npc, action)

        # Switch UI to reaction phase
        if self.social_ui:
            self.social_ui.show_response(self._reaction_line, deltas)

        # Transition to showing reaction (player reads it, then closes)
        self.state = InteractionState.SHOWING_REACTION
        self._resolving_timer = 2.5  # Seconds to display the reaction before auto-close

        # Log for debugging
        print(f"[SOCIAL] {self._active_npc.name} ({action}) — {self._active_npc.group.value}")
        print(f"[SOCIAL] NPC says: \"{self._reaction_line}\"")

    def handle_input(self, event: pygame.event.Event) -> bool:
        """Process input during interaction.

        W/S/UP/DOWN: move cursor
        E / RETURN / ENTER: confirm choice
        MOUSE LEFT CLICK: select and confirm
        ESC: handled by game loop (force_close)

        Returns True if input was handled, False otherwise.
        """
        # During reaction phase: any key or click closes
        if self.state == InteractionState.SHOWING_REACTION:
            if event.type == pygame.KEYDOWN and event.key in (
                pygame.K_RETURN, pygame.K_e, pygame.K_SPACE
            ):
                self._begin_close()
                return True
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._begin_close()
                return True
            return False

        if self.state != InteractionState.ACTIVE:
            return False

        # Mouse Support
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.social_ui:
                idx = self.social_ui.get_clicked_option(event.pos)
                if idx is not None:
                    self._selected_option_idx = idx
                    self.confirm_choice()
                    return True
            return False

        if event.type != pygame.KEYDOWN:
            return False

        key = event.key

        # W / UP — move selection up
        if key in (pygame.K_w, pygame.K_UP):
            self._selected_option_idx = (self._selected_option_idx - 1) % len(self._available_options)
            if self.social_ui:
                self.social_ui.set_selected(self._selected_option_idx)
            return True

        # S / DOWN — move selection down
        elif key in (pygame.K_s, pygame.K_DOWN):
            self._selected_option_idx = (self._selected_option_idx + 1) % len(self._available_options)
            if self.social_ui:
                self.social_ui.set_selected(self._selected_option_idx)
            return True

        # E / RETURN / ENTER — confirm
        elif key in (pygame.K_e, pygame.K_RETURN, pygame.K_KP_ENTER):
            self.confirm_choice()
            return True

        return False

    def update(self, dt: float):
        """Tick timers and manage state transitions.

        Called once per frame from Game.update().
        """
        # Decrement all active cooldowns
        for npc_id in list(self._cooldown_timer.keys()):
            self._cooldown_timer[npc_id] -= dt
            if self._cooldown_timer[npc_id] <= 0:
                del self._cooldown_timer[npc_id]

        # Auto-close after the reaction display timer expires
        if self.state == InteractionState.SHOWING_REACTION:
            self._resolving_timer -= dt
            if self._resolving_timer <= 0:
                self._begin_close()
            return

        # Handle legacy RESOLVING state (kept for safety)
        if self.state == InteractionState.RESOLVING:
            self._resolving_timer -= dt
            if self._resolving_timer <= 0:
                self.state = InteractionState.CLOSING

        # Handle CLOSING state
        if self.state == InteractionState.CLOSING:
            if self._active_npc:
                npc_id = self._active_npc.id
                self._cooldown_timer[npc_id] = SOCIAL_COOLDOWN

            self.force_close()

    # ── PRIVATE HELPERS ────────────────────────────────────

    def _begin_close(self):
        """Start the closing sequence — apply cooldown then force_close."""
        if self._active_npc:
            self._cooldown_timer[self._active_npc.id] = SOCIAL_COOLDOWN
        self.force_close()

    def _generate_npc_line(self, npc) -> str:
        """Generate a contextual NPC opening line based on group & emotional state."""
        key = (npc.group.value, npc.emotional_state)
        lines = self.NPC_LINES.get(key, [])

        if not lines:
            # Fallback to neutral
            key = (npc.group.value, "neutral")
            lines = self.NPC_LINES.get(key, ["Hey there."])

        return random.choice(lines) if lines else "Hey there."

    def _generate_reaction_line(self, npc, action: str) -> str:
        """Generate the NPC's reaction after the player chooses an action."""
        key = (npc.group.value, action)
        lines = self.REACTION_LINES.get(key, [])
        return random.choice(lines) if lines else "..."

    def _get_options_with_deltas(self) -> list[dict]:
        """Build option list with reputation delta preview (DRY RUN — no mutation).

        Returns list of dicts: {"label": str, "action": str, "deltas": list[ReputationDelta]}
        """
        if not self._active_npc or not self.reputation_manager:
            return []

        group = self._active_npc.group.value
        options = []

        for action in self._available_options:
            try:
                # dry_run=True — preview only, NO stat mutation
                deltas = self.reputation_manager.apply_interaction(
                    group, action, dry_run=True
                )
            except Exception as e:
                print(f"[SocialSystem] Failed generating deltas: {e}")
                deltas = []

            options.append({
                "label": action.capitalize(),
                "action": action,
                "deltas": deltas,
            })

        return options

    def is_visible(self) -> bool:
        """Check if the interaction UI should be visible."""
        return self._visible and self.state in (
            InteractionState.ACTIVE,
            InteractionState.WAITING_CHOICE,
            InteractionState.SHOWING_REACTION,
            InteractionState.RESOLVING,
        )

    def get_active_npc(self):
        """Return the currently active NPC, if any."""
        return self._active_npc

    def get_state(self) -> InteractionState:
        """Return current interaction state."""
        return self.state
