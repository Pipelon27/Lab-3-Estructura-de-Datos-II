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
    IDLE             = auto()   # No active interaction
    APPROACHING      = auto()   # Player in range, prompt shown
    ACTIVE           = auto()   # UI open, waiting for input
    WAITING_CHOICE   = auto()   # Player selecting option
    SHOWING_REACTION = auto()   # NPC reacting to player's choice
    RESOLVING        = auto()   # Applying consequences / timer
    CLOSING          = auto()   # Fading out


class SocialDialogueManager:
    """Manages active NPC social interactions with state machine & stability rules.

    Only ONE interaction can be active at a time.
    """

    # ── NPC OPENING LINES ──────────────────────────────────────
    # Keyed by (group, emotional_state).
    # These are lines the NPC initiates — they have something to say.
    NPC_LINES = {

        # ── ATHLETES ──────────────────────────────────────────
        ("athletes", "neutral"): [
            "Yo, you catch the game yesterday? We absolutely crushed it.",
            "I've been in the zone all week. Coach has us running drills nonstop.",
            "Hey. You got a sec? I need someone to vent to about practice.",
            "Don't tell the others, but I actually pulled a muscle last Tuesday.",
            "I've been trying to stay focused, but it's hard with everything going on.",
            "We've got regionals coming up. I'm honestly nervous but don't repeat that.",
            "You look like someone who actually listens. Most people here just want to talk about themselves.",
            "I was just thinking about switching positions. Coach doesn't know yet.",
        ],
        ("athletes", "open"): [
            "Hey! I was hoping to run into you. How's your week going?",
            "Oh nice, it's you. I've been meaning to say — you're actually pretty cool.",
            "Good timing! I just had a great practice. I'm feeling unstoppable right now.",
            "Hey! I've been thinking about what you said last time. You had a point.",
            "You always show up when I need a break from the pressure. What's up?",
        ],
        ("athletes", "nervous"): [
            "I… I just need some space right now, okay?",
            "Things have been rough. I don't really want to get into it.",
            "Please don't make a scene. I'm already dealing with enough.",
            "Just… stay back. I'm not in a good place today.",
        ],
        ("athletes", "hostile"): [
            "I told you, back off. I mean it.",
            "You really don't want to push this right now.",
            "Get away from me before I make you.",
        ],

        # ── TECH CLUB ─────────────────────────────────────────
        ("tech_club", "neutral"): [
            "Oh — sorry, I was in the middle of something. What's up?",
            "I just found a bug in my code that's been driving me insane for three days. THREE DAYS.",
            "Have you ever thought about how the school Wi-Fi is probably logging everything we do?",
            "I'm working on a project that could honestly change how we do everything here.",
            "I've been meaning to talk to someone about this — do you know much about encryption?",
            "I was running simulations and I think there's a pattern in how the teachers grade.",
            "You look like you might actually understand what I'm about to say. Ready?",
            "I mapped out the entire social hierarchy of this school using a weighted graph. Wanna see?",
        ],
        ("tech_club", "open"): [
            "Oh great, you're here! I need a second opinion on something.",
            "I was literally just thinking about you. Come look at this — it's wild.",
            "Hey! I finished the project. It works. It actually works. I'm freaking out.",
            "You're one of the few people here who doesn't make me feel like I'm talking to a wall.",
            "Good timing! I need someone to test something. It's not dangerous. Probably.",
        ],
        ("tech_club", "nervous"): [
            "I… I don't think I should be talking right now. Someone might see.",
            "Can you come back later? I think I'm being watched.",
            "I messed something up and I'm trying not to make it worse.",
        ],
        ("tech_club", "hostile"): [
            "I have nothing to say to you.",
            "Please just leave. I'm not kidding.",
            "Don't make me block you IRL too.",
        ],

        # ── POPULARS ──────────────────────────────────────────
        ("populars", "neutral"): [
            "Okay so you will NOT believe what I just heard in the hallway.",
            "I'm trying to decide between two outfits for the thing on Friday. Thoughts?",
            "Honestly? I'm exhausted. Everyone expects me to be 'on' all the time.",
            "Did you hear what happened at Dylan's last weekend? It was a lot.",
            "I feel like no one actually talks to me anymore. They just talk AT me, you know?",
            "I'm throwing something together this weekend. Nothing big. Are you free?",
            "Everyone assumes I have it all together. It's genuinely exhausting.",
            "I saw you around and honestly thought — that person looks real. Not fake.",
        ],
        ("populars", "open"): [
            "Oh my god, YOU. I need to tell you everything right now.",
            "There you are! I've been looking for someone who won't just agree with everything I say.",
            "Okay I'm glad it's you. I can actually be honest with you.",
            "You have no idea how much better you make my day by just existing nearby.",
            "Finally, someone I can actually talk to. Everyone else is so exhausting.",
        ],
        ("populars", "nervous"): [
            "I'm kind of in the middle of something… it's complicated.",
            "I can't talk right now. There are people watching.",
            "Please don't start drama right now. I'm barely holding it together.",
        ],
        ("populars", "hostile"): [
            "Excuse me? Do you know who you're talking to?",
            "I don't have time for this. Or you.",
            "Walk away. Now. Before I make this a thing.",
        ],

        # ── ACADEMICS ─────────────────────────────────────────
        ("academics", "neutral"): [
            "Can I ask you something? Do you actually retain information better by reading or listening?",
            "I've been trying to figure out if the finals will cover chapter twelve or not.",
            "I honestly think the education system here is fundamentally broken. Can I explain why?",
            "I was reading about cognitive load theory and now I can't stop applying it to everything.",
            "I need someone to quiz me. Are you any good at chemistry?",
            "Do you think ambition is something you're born with, or something you build?",
            "I got a 97 on the last test and I'm still bothered about the three I missed.",
            "I've been tracking everyone's grade patterns on the bulletin board. Not in a weird way.",
        ],
        ("academics", "open"): [
            "Oh good, you're here. I've been wanting to talk to someone with actual depth.",
            "I trust your opinion. What do you think about what's been going on lately?",
            "I've been thinking about you — in a completely academic, observational way. You're interesting.",
            "I feel like I can actually be honest around you. That's rare.",
            "You showed up right when I needed someone to talk to. Funny how that works.",
        ],
        ("academics", "nervous"): [
            "I'm… I'm under a lot of pressure right now. Can we talk later?",
            "I don't really want to get into it. Things are complicated.",
            "Just give me some space, okay? Please.",
        ],
        ("academics", "hostile"): [
            "I have nothing productive to say to you right now.",
            "Please go away. I'm serious.",
            "You've made your position clear. I've made mine.",
        ],

        # ── REBELS ────────────────────────────────────────────
        ("rebels", "neutral"): [
            "You see what the administration put up on the bulletin board? Classic manipulation.",
            "I've been thinking — what if everything we're being taught here is just… conditioning?",
            "I painted something on the east wall last night. Don't tell anyone. But also, tell everyone.",
            "I don't trust most people. But you seem like you actually think for yourself.",
            "Everyone's pretending to be okay. You can see it, right? In their faces?",
            "I've been writing something. It's angry. I think it's good.",
            "Do you ever feel like you're the only one who sees how fake all of this is?",
            "I found something I probably wasn't supposed to find. I'm still processing it.",
        ],
        ("rebels", "open"): [
            "Okay you're one of the good ones. I don't say that often.",
            "You came back. I honestly didn't think you would.",
            "I've been wanting to show you something. Don't freak out.",
            "I trust you more than most people here. That means something, coming from me.",
            "Good, it's you. I've been thinking about our last conversation.",
        ],
        ("rebels", "nervous"): [
            "Not now. Seriously. Not right now.",
            "I think someone's been watching me. Just… go.",
            "I can't talk right now. Something's going on.",
        ],
        ("rebels", "hostile"): [
            "You really want to do this? Right here?",
            "I'm not interested in anything you have to say.",
            "Get out of my face.",
        ],

        # ── OUTSIDERS ─────────────────────────────────────────
        ("outsiders", "neutral"): [
            "Oh… I wasn't expecting anyone to come over. Um, hi.",
            "I was just sitting here watching everyone and wondering if any of it is real.",
            "You know, I've been at this school for months and you might be the first person to just… walk up to me.",
            "I was reading something that made me cry a little. Don't judge me.",
            "I don't really fit anywhere here. But I've kind of made peace with that. Maybe.",
            "I was thinking about going home early. Not for any reason. Just to be somewhere quieter.",
            "Sometimes I wonder if anyone would notice if I just… disappeared for a day.",
            "I wrote a poem today. I don't know if it's good. I don't think I care.",
        ],
        ("outsiders", "open"): [
            "Oh! You came back. I didn't think you'd actually come back.",
            "I've been thinking about you. In a good way. Not a weird way. Sorry.",
            "You're one of maybe three people here who's ever made me feel normal.",
            "I was hoping I'd see you today. I have something I wanted to say.",
            "Hey. I'm really glad you're here right now. Genuinely.",
        ],
        ("outsiders", "nervous"): [
            "Is something wrong? Did someone send you?",
            "I… I'm not really in a good place to talk right now.",
            "Please don't make this a thing. I just want to be left alone today.",
        ],
        ("outsiders", "hostile"): [
            "I said leave me alone. I meant it.",
            "Please. Just. Go.",
            "I don't have anything to say to you.",
        ],
    }

    # ── NPC REACTION LINES ─────────────────────────────────────
    # What the NPC says AFTER the player chooses their response.
    REACTION_LINES = {
        # RESPOND — player is kind/engaged
        ("athletes", "respond"): [
            "That's actually… really cool of you. Not what I expected.",
            "Okay. Yeah. I respect that. Seriously.",
            "You know, most people don't listen like that. It means something.",
            "Huh. Thanks. I needed to hear something real today.",
        ],
        ("tech_club", "respond"): [
            "That was genuinely thoughtful. Thank you.",
            "Wow, okay. You actually got it. Most people don't.",
            "I wasn't expecting that kind of answer. I really wasn't.",
            "You're one of the few people here worth talking to.",
        ],
        ("populars", "respond"): [
            "Okay wait — that was actually a real thing to say. I'm a little surprised.",
            "Hmm. Maybe I misjudged you. Maybe.",
            "That's… honestly kind of sweet. Don't tell anyone I said that.",
            "You know, most people just say what they think I want to hear. You didn't.",
        ],
        ("academics", "respond"): [
            "That's a genuinely good point. I didn't consider that angle.",
            "Okay, I respect that answer. That took thought.",
            "You know, a real conversation is rare here. Thank you.",
            "I'm going to think about what you just said for a while.",
        ],
        ("rebels", "respond"): [
            "Hah. Yeah. You get it.",
            "That's the most honest thing anyone's said to me all week.",
            "Okay, I see you. You're alright.",
            "I don't say this much, but — I appreciate that.",
        ],
        ("outsiders", "respond"): [
            "Oh wow. That… that actually means a lot to me.",
            "I wasn't expecting anyone to say something like that. Thank you.",
            "That's the nicest thing anyone's said to me in a long time.",
            "I think I needed that more than I realized.",
        ],

        # IGNORE — player dismisses the NPC
        ("athletes", "ignore"): [
            "Wow. Okay. Pretend I don't exist, sure.",
            "That's cool. I'll remember that.",
            "Seriously? I was actually trying to talk to you.",
            "Cool. We're done here then.",
        ],
        ("tech_club", "ignore"): [
            "…Noted. This interaction has been logged.",
            "That was rude. Just so you know.",
            "Okay. I'll just… go back to my code.",
            "Fine. I'll remember this next time you need something.",
        ],
        ("populars", "ignore"): [
            "Excuse me?! Rude.",
            "Oh, so we're doing that? Fine. I have receipts.",
            "Don't think I won't tell everyone about this.",
            "The audacity. Genuinely.",
        ],
        ("academics", "ignore"): [
            "That was completely unnecessary.",
            "…I see. Duly noted.",
            "I've catalogued worse. But this was still rude.",
            "You know, social capital is finite. Just saying.",
        ],
        ("rebels", "ignore"): [
            "Oh, that's how we're playing it? Sure.",
            "Cool. Whatever. Your loss.",
            "Yeah, figures. Nobody actually cares.",
            "Fine. I don't need you either.",
        ],
        ("outsiders", "ignore"): [
            "Oh… okay. Sorry for bothering you.",
            "I guess I shouldn't have said anything.",
            "That… that kind of hurt. It's fine. I'm fine.",
            "I knew I shouldn't have said anything.",
        ],

        # INTIMIDATE — player is aggressive
        ("athletes", "intimidate"): [
            "You REALLY want to try that with me?",
            "Back off before this becomes a problem for YOU.",
            "That is not okay. Not even close.",
            "Try that again and we'll see how it ends.",
        ],
        ("tech_club", "intimidate"): [
            "That… that is completely out of line!",
            "I'm reporting this. I have logs.",
            "You realize I can make your life very complicated, right?",
            "Wow. Okay. You're on a list now.",
        ],
        ("populars", "intimidate"): [
            "Do you have ANY idea what I can do to your reputation?",
            "You are SO done here. Enjoy the consequences.",
            "How DARE you. This is not over.",
            "That was a catastrophically bad idea. For you.",
        ],
        ("academics", "intimidate"): [
            "That behavior is completely unacceptable and I won't stand for it!",
            "I am documenting this. All of it.",
            "You realize there are consequences for this, right?",
            "This is going to the administration. Today.",
        ],
        ("rebels", "intimidate"): [
            "Oh, you think that works on me? Try again.",
            "Go ahead. I've dealt with worse than you.",
            "You should walk away right now. Seriously.",
            "I don't scare easy. You picked the wrong one.",
        ],
        ("outsiders", "intimidate"): [
            "Please… please just stop.",
            "Why are you doing this to me?",
            "That was really cruel. I hope you know that.",
            "I just… I just wanted to talk.",
        ],
    }

    def __init__(self):
        self.state = InteractionState.IDLE
        self._active_npc    = None
        self._player        = None
        self._selected_option_idx  = 0
        self._available_options    = ["respond", "ignore", "intimidate"]
        self._npc_line      = ""
        self._reaction_line = ""
        self._cooldown_timer: dict[str, float] = {}
        self._resolving_timer = 0.0
        self._visible       = False
        self.reputation_manager = None
        self.social_ui      = None
        self.conversation_active = False

    # ── PUBLIC API ─────────────────────────────────────────────

    def try_start(self, npc, player) -> bool:
        """Attempt to start an interaction with an NPC.

        Returns True if interaction started, False otherwise.
        """
        if self.conversation_active:
            print("[SocialSystem] Interaction blocked: conversation already active")
            return False

        if self.state != InteractionState.IDLE:
            print(f"[SocialSystem] Interaction blocked: state={self.state.name}")
            return False

        if npc is None:
            return False
        if self.social_ui is None:
            print("[SocialSystem] Interaction blocked: Missing social UI")
            return False
        if self.reputation_manager is None:
            print("[SocialSystem] Interaction blocked: Missing reputation manager")
            return False

        # Check cooldown
        if self._cooldown_timer.get(npc.id, 0) > 0:
            remaining = self._cooldown_timer[npc.id]
            print(f"[SocialSystem] Cooldown active for {npc.name}: {remaining:.1f}s left")
            return False

        # Lock in
        self._active_npc = npc
        self._player     = player
        self._selected_option_idx = 0
        self._npc_line   = self._generate_npc_line(npc)

        options_data = self._get_options_with_deltas()   # dry_run — no mutation

        self.conversation_active = True
        self.state   = InteractionState.ACTIVE
        self._visible = True

        if self.social_ui:
            self.social_ui.show(npc, options_data)
            self.social_ui.set_npc_line(self._npc_line)

        print(f"[SocialSystem] Started interaction with {npc.name} ({npc.group.value})")
        return True

    def force_close(self):
        """Safe cleanup — called on ESC, death, or state change."""
        if self.social_ui:
            self.social_ui.hide()
        self.state   = InteractionState.IDLE
        self._active_npc = None
        self._player     = None
        self._visible    = False
        self._selected_option_idx = 0
        self.conversation_active  = False
        print("[SocialSystem] Dialogue closed")

    def confirm_choice(self):
        """Player confirmed their selected option."""
        if not self._active_npc:
            return

        action = self._available_options[self._selected_option_idx]

        # Update NPC social memory
        self._active_npc.update_social_memory(action)

        # Apply group reputation consequences (real mutation)
        deltas = []
        if self.reputation_manager:
            deltas = self.reputation_manager.apply_interaction(
                self._active_npc.group.value, action,
                npc_id=self._active_npc.id,
                dry_run=False,
            )
            self.reputation_manager.apply_individual_npc_stats(self._active_npc, action)

        # NPC reaction
        self._reaction_line = self._generate_reaction_line(self._active_npc, action)
        if self.social_ui:
            self.social_ui.show_response(self._reaction_line, deltas)

        self.state = InteractionState.SHOWING_REACTION
        self._resolving_timer = 2.5

        print(f"[SOCIAL] {self._active_npc.name} <- {action} -> \"{self._reaction_line}\"")

    def handle_input(self, event: pygame.event.Event) -> bool:
        """Process input during interaction."""

        # Reaction phase: any confirm key/click dismisses
        if self.state == InteractionState.SHOWING_REACTION:
            if event.type == pygame.KEYDOWN and event.key in (
                pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_e, pygame.K_SPACE
            ):
                self._begin_close()
                return True
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._begin_close()
                return True
            return False

        if self.state != InteractionState.ACTIVE:
            return False

        # Mouse click on option button
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

        if key in (pygame.K_w, pygame.K_UP):
            self._selected_option_idx = (self._selected_option_idx - 1) % len(self._available_options)
            if self.social_ui:
                self.social_ui.set_selected(self._selected_option_idx)
            return True

        if key in (pygame.K_s, pygame.K_DOWN):
            self._selected_option_idx = (self._selected_option_idx + 1) % len(self._available_options)
            if self.social_ui:
                self.social_ui.set_selected(self._selected_option_idx)
            return True

        if key in (pygame.K_e, pygame.K_RETURN, pygame.K_KP_ENTER):
            self.confirm_choice()
            return True

        return False

    def handle_controller(self, controller):
        """Handle Xbox controller input during social interaction."""
        if not self._active_npc:
            return

        # Reaction phase: A or B button dismisses the dialogue
        if self.state == InteractionState.SHOWING_REACTION:
            if controller.is_confirm_pressed() or controller.is_cancel_pressed():
                self._begin_close()
            return

        if self.state != InteractionState.ACTIVE:
            return

        # D-pad Up / Down / LS Up / Down for menu selection
        menu_v = controller.get_menu_direction()
        if menu_v != 0:
            self._selected_option_idx = (self._selected_option_idx + menu_v) % len(self._available_options)
            if self.social_ui:
                self.social_ui.set_selected(self._selected_option_idx)

        # A button to confirm
        if controller.is_confirm_pressed():
            self.confirm_choice()

        # B button to exit dialogue immediately
        if controller.is_cancel_pressed():
            self._begin_close()

    def update(self, dt: float):
        """Tick cooldowns and state transitions. Called every frame unconditionally."""
        # Decrement cooldowns
        for npc_id in list(self._cooldown_timer):
            self._cooldown_timer[npc_id] -= dt
            if self._cooldown_timer[npc_id] <= 0:
                del self._cooldown_timer[npc_id]
                print(f"[SocialSystem] Cooldown expired for npc={npc_id}")

        # Auto-close reaction screen after timer
        if self.state == InteractionState.SHOWING_REACTION:
            self._resolving_timer -= dt
            if self._resolving_timer <= 0:
                self._begin_close()
            return

        # Legacy RESOLVING → CLOSING
        if self.state == InteractionState.RESOLVING:
            self._resolving_timer -= dt
            if self._resolving_timer <= 0:
                self.state = InteractionState.CLOSING

        if self.state == InteractionState.CLOSING:
            if self._active_npc:
                self._cooldown_timer[self._active_npc.id] = SOCIAL_COOLDOWN
            self.force_close()

    # ── PRIVATE HELPERS ────────────────────────────────────────

    def _begin_close(self):
        """Start the closing sequence with cooldown."""
        if self._active_npc:
            self._cooldown_timer[self._active_npc.id] = SOCIAL_COOLDOWN
        self.force_close()

    def _generate_npc_line(self, npc) -> str:
        """Pick a random opening line based on group & emotional state."""
        key   = (npc.group.value, npc.emotional_state)
        lines = self.NPC_LINES.get(key) or self.NPC_LINES.get((npc.group.value, "neutral"), ["Hey."])
        return random.choice(lines)

    def _generate_reaction_line(self, npc, action: str) -> str:
        """Pick a random NPC reaction after the player chooses an action."""
        key   = (npc.group.value, action)
        lines = self.REACTION_LINES.get(key, ["..."])
        return random.choice(lines)

    def _get_options_with_deltas(self) -> list[dict]:
        """Build option list with reputation delta preview — dry_run, NO mutation."""
        if not self._active_npc or not self.reputation_manager:
            return []

        group   = self._active_npc.group.value
        options = []
        for action in self._available_options:
            try:
                deltas = self.reputation_manager.apply_interaction(
                    group, action, dry_run=True
                )
            except Exception as exc:
                print(f"[SocialSystem] Preview delta error: {exc}")
                deltas = []
            options.append({"label": action.capitalize(), "action": action, "deltas": deltas})
        return options

    # ── QUERIES ────────────────────────────────────────────────

    def is_visible(self) -> bool:
        return self._visible and self.state in (
            InteractionState.ACTIVE,
            InteractionState.WAITING_CHOICE,
            InteractionState.SHOWING_REACTION,
            InteractionState.RESOLVING,
        )

    def get_active_npc(self):
        return self._active_npc

    def get_state(self) -> InteractionState:
        return self.state
