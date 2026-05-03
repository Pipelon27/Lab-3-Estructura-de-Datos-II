"""
src/phone.py  —  In-game smartphone (GTA V style)
==================================================
22% screen width · 9:16 aspect ratio · bottom-right
Slide-from-below + scale animation (0.9→1.0, 200 ms)
4 apps:  Academic | Social | Messages | Schedule
12-px grid · click-outside to close · no game pause
"""

from __future__ import annotations

import math
import pygame
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable

from settings import SCREEN_WIDTH, SCREEN_HEIGHT, WHITE, BLACK


# ═══════════════════════════════════════════════════════════════
#  LAYOUT  (8-px grid)
# ═══════════════════════════════════════════════════════════════

_MR = max(24, int(SCREEN_WIDTH  * 0.025))   # right margin  ≈ 32 px
_MB = max(16, int(SCREEN_HEIGHT * 0.028))   # bottom margin ≈ 20 px

PHONE_W = int(SCREEN_WIDTH * 0.22)          # ≈ 281 px
PHONE_H = int(PHONE_W * 16 / 9)            # 9:16  ≈ 498 px
PHONE_X = SCREEN_WIDTH  - PHONE_W - _MR
PHONE_Y = SCREEN_HEIGHT - PHONE_H - _MB

_BZ     = 8    # bezel
_STAT_H = 28   # status-bar height
_NAV_H  = 48   # nav-bar height
_PAD    = 12   # content padding
_GAP    = 8    # gap between cards

# content rect inside phone surface
_CX = _BZ
_CY = _BZ + _STAT_H
_CW = PHONE_W - _BZ * 2
_CH = PHONE_H - _BZ * 2 - _STAT_H - _NAV_H

# animation
_DUR_OPEN  = 0.20   # s
_DUR_CLOSE = 0.15   # s
_SLIDE_PX  = 80     # px from below


# ═══════════════════════════════════════════════════════════════
#  COLOUR PALETTE
# ═══════════════════════════════════════════════════════════════

PH_BODY      = (10,  10,  16)
PH_SCREEN    = (16,  16,  26)
PH_CARD      = (24,  24,  38)
PH_CARD2     = (30,  30,  48)
PH_STAT_BG   = ( 8,   8,  13)
PH_NAV_BG    = (12,  12,  20)
PH_BD        = (46,  46,  70)
PH_BD_LT     = (68,  68,  98)

PH_CYAN      = ( 90, 195, 255)
PH_CYAN_DIM  = ( 45,  98, 128)
PH_GREEN     = ( 76, 200, 130)
PH_AMBER     = (240, 185,  60)
PH_RED       = (220,  60,  80)
PH_PINK      = (255,  95, 145)

PH_TEXT      = (235, 235, 242)
PH_TEXT_S    = (145, 145, 165)
PH_TEXT_D    = ( 85,  85, 108)

PH_ANON_BG   = (28,  14,  14)
PH_ANON_BD   = (90,  35,  35)
PH_MENC_BG   = (14,  26,  38)
PH_MENC_BD   = PH_CYAN

PH_BUB_P     = (45, 100, 195)   # player bubble
PH_BUB_N     = (32,  32,  52)   # NPC bubble

_SC = {"pending": PH_TEXT_D, "in_progress": PH_AMBER, "completed": PH_GREEN}
_SL = {"pending": "Pendiente", "in_progress": "En progreso", "completed": "Completada"}


# ═══════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

@dataclass
class SocialPost:
    id: str
    author: str
    author_npc_id: Optional[str]
    content: str
    timestamp: str
    is_anonymous: bool
    likes: int = 0
    mentions: list = field(default_factory=list)
    image_tag: Optional[str] = None
    affects_reputation: bool = False
    reputation_target: Optional[str] = None
    _liked: bool = False


@dataclass
class TextMessage:
    id: str
    sender_npc_id: str
    sender_name: str
    content: str
    timestamp: str
    is_read: bool = False
    is_player: bool = False
    attachment: Optional[str] = None
    reply_options: list = field(default_factory=list)


@dataclass
class AcademicTask:
    id: str
    title: str
    description: str
    issuer: str
    status: str          # "pending" | "in_progress" | "completed"
    deadline: Optional[str] = None
    progress: float = 0.0
    is_main_mission: bool = False


@dataclass
class ScheduleEvent:
    hour: int            # 0-23
    name: str
    location: str
    description: str


# ═══════════════════════════════════════════════════════════════
#  ENUMS
# ═══════════════════════════════════════════════════════════════

class PhoneState(Enum):
    CLOSED  = 0
    OPENING = 1
    OPEN    = 2
    CLOSING = 3


class PhoneApp(Enum):
    ACADEMIC = "academic"
    SOCIAL   = "social"
    MESSAGES = "messages"
    SCHEDULE = "schedule"


# ═══════════════════════════════════════════════════════════════
#  PHONE
# ═══════════════════════════════════════════════════════════════

class Phone:
    """GTA V-style smartphone overlay."""

    _APPS = [
        (PhoneApp.ACADEMIC, "📚", "Académico"),
        (PhoneApp.SOCIAL,   "📢", "Social"),
        (PhoneApp.MESSAGES, "💬", "Mensajes"),
        (PhoneApp.SCHEDULE, "🕐", "Horario"),
    ]

    # ------------------------------------------------------------------
    def __init__(self, screen: pygame.Surface,
                 time_source: Optional[Callable[[], float]] = None,
                 player_name: str = "player"):
        self.screen      = screen
        self.time_source = time_source      # () → float minutes of day
        self.player_name = player_name.lower()

        self.state      = PhoneState.CLOSED
        self._anim_t    = 0.0
        self.is_visible = False

        self.current_app   = PhoneApp.ACADEMIC
        self._scroll       = {app: 0 for app in PhoneApp}
        self.social_filter = "all"           # "all" | "anonymous" | "mentions"
        self.active_chat: Optional[str]    = None   # npc_id
        self.active_task: Optional[object] = None

        # Data
        self.social_posts:    list[SocialPost]              = []
        self.messages:        dict[str, list[TextMessage]]  = {}
        self.academic_tasks:  list[AcademicTask]            = []
        self.schedule_events: list[ScheduleEvent]           = []
        self.unread_count     = 0
        self.show_unread      = False

        # Off-screen surface for smooth animation
        self._surf = pygame.Surface((PHONE_W, PHONE_H))

        # Fonts
        self._f_stat  = pygame.font.SysFont("arial", 10, bold=True)
        self._f_sec   = pygame.font.SysFont("arial", 12, bold=True)
        self._f_title = pygame.font.SysFont("arial", 12, bold=True)
        self._f_body  = pygame.font.SysFont("arial", 11)
        self._f_sub   = pygame.font.SysFont("arial", 10)
        self._f_badge = pygame.font.SysFont("arial",  9, bold=True)
        try:
            self._f_ico = pygame.font.SysFont("seguiemj", 15)
        except Exception:
            self._f_ico = self._f_sec

        # Click rects (phone-surface local coords, set each frame)
        self._nav_rects:    list[tuple[pygame.Rect, PhoneApp]] = []
        self._task_rects:   list[tuple[pygame.Rect, object]]   = []
        self._post_rects:   list[tuple[pygame.Rect, object]]   = []
        self._like_rects:   list[tuple[pygame.Rect, object]]   = []
        self._chat_rects:   list[tuple[pygame.Rect, str]]      = []
        self._filter_rects: list[tuple[pygame.Rect, str]]      = []
        self._reply_rects:  list[tuple[pygame.Rect, str]]      = []
        self._back_rect: Optional[pygame.Rect]                 = None

    # ──────────────────────────────────────────────────────────
    #  PUBLIC API
    # ──────────────────────────────────────────────────────────

    def toggle_phone(self):
        if self.state in (PhoneState.CLOSED, PhoneState.CLOSING):
            self.state = PhoneState.OPENING
            self._anim_t = 0.0
            self.is_visible = True
        else:
            self.state = PhoneState.CLOSING
            self._anim_t = 1.0

    def close(self):
        if self.state in (PhoneState.OPEN, PhoneState.OPENING):
            self.state = PhoneState.CLOSING
            self._anim_t = 1.0

    def update(self, dt: float):
        if self.state == PhoneState.OPENING:
            self._anim_t = min(1.0, self._anim_t + dt / _DUR_OPEN)
            if self._anim_t >= 1.0:
                self.state = PhoneState.OPEN
        elif self.state == PhoneState.CLOSING:
            self._anim_t = max(0.0, self._anim_t - dt / _DUR_CLOSE)
            if self._anim_t <= 0.0:
                self.state = PhoneState.CLOSED
                self.is_visible = False

    # Data helpers
    def add_social_post(self, post: SocialPost):
        self.social_posts.insert(0, post)

    def add_text_message(self, npc_id: str, msg: TextMessage):
        self.messages.setdefault(npc_id, []).append(msg)
        if not msg.is_read and not msg.is_player:
            self.unread_count += 1
            self.show_unread   = True

    def add_academic_task(self, task: AcademicTask):
        self.academic_tasks.append(task)

    def update_academic_task(self, task_id: str, **kwargs):
        for t in self.academic_tasks:
            if t.id == task_id:
                for k, v in kwargs.items():
                    if hasattr(t, k):
                        setattr(t, k, v)
                break

    def set_schedule_events(self, events: list):
        self.schedule_events = events

    def get_unread_messages_count(self) -> int:
        return sum(1 for ml in self.messages.values()
                   for m in ml if not m.is_read and not m.is_player)

    def mark_messages_read(self, npc_id: str):
        for m in self.messages.get(npc_id, []):
            m.is_read = True

    # ──────────────────────────────────────────────────────────
    #  DRAW
    # ──────────────────────────────────────────────────────────

    def draw(self):
        if not self.is_visible and self.state == PhoneState.CLOSED:
            return

        p     = self._ease_out(self._anim_t)
        slide  = int((1.0 - p) * _SLIDE_PX)
        scale  = 0.90 + 0.10 * p

        self._render_to_surface()

        sw = int(PHONE_W * scale)
        sh = int(PHONE_H * scale)
        if sw > 0 and sh > 0:
            scaled = pygame.transform.smoothscale(self._surf, (sw, sh))
            bx = PHONE_X + (PHONE_W - sw) // 2
            by = PHONE_Y + (PHONE_H - sh) // 2 + slide
            self.screen.blit(scaled, (bx, by))

    def _render_to_surface(self):
        s = self._surf
        s.fill(PH_BODY)

        # phone body
        self._rrect(s, PH_BODY, pygame.Rect(0, 0, PHONE_W, PHONE_H), 16, PH_BD, 1)
        # screen glass
        self._rrect(s, PH_SCREEN, pygame.Rect(_BZ, _BZ, _CW, PHONE_H - _BZ * 2), 12)
        # notch
        nw = PHONE_W // 3
        pygame.draw.rect(s, PH_BODY, ((PHONE_W - nw) // 2, _BZ, nw, 10), border_radius=5)

        self._draw_status_bar(s)

        old = s.get_clip()
        s.set_clip((_CX, _CY, _CW, _CH))
        self._draw_content(s)
        s.set_clip(old)

        self._draw_nav_bar(s)

    # ── Status bar ─────────────────────────────────────────────────

    def _draw_status_bar(self, s):
        pygame.draw.rect(s, PH_STAT_BG, (_BZ, _BZ, _CW, _STAT_H))

        if self.time_source:
            mins = int(self.time_source()) % 1440
            h, m = divmod(mins, 60)
            sfx = "am" if h < 12 else "pm"
            h12 = h % 12 or 12
            ts = f"{h12}:{m:02d}{sfx}"
        else:
            ts = "00:00"

        t = self._f_stat.render(ts, True, PH_TEXT)
        s.blit(t, t.get_rect(midleft=(_BZ + 4, _BZ + _STAT_H // 2)))

        sig = self._f_stat.render("●●●  ▓", True, PH_TEXT_S)
        s.blit(sig, sig.get_rect(midright=(_BZ + _CW - 4, _BZ + _STAT_H // 2)))

    # ── Nav bar ────────────────────────────────────────────────────

    def _draw_nav_bar(self, s):
        ny = PHONE_H - _BZ - _NAV_H
        pygame.draw.rect(s, PH_NAV_BG, (_BZ, ny, _CW, _NAV_H))
        pygame.draw.line(s, PH_BD, (_BZ, ny), (_BZ + _CW, ny))

        self._nav_rects = []
        iw = _CW // len(self._APPS)
        for i, (app, icon, label) in enumerate(self._APPS):
            ix = _BZ + i * iw
            active = (app == self.current_app)
            if active:
                pygame.draw.rect(s, PH_CYAN, (ix + 4, ny + 2, iw - 8, 2), border_radius=1)

            col_ico = PH_CYAN if active else PH_TEXT_D
            col_lbl = PH_CYAN if active else PH_TEXT_S

            try:
                ico = self._f_ico.render(icon, True, col_ico)
            except Exception:
                ico = self._f_title.render(label[:2], True, col_ico)
            s.blit(ico, ico.get_rect(center=(ix + iw // 2, ny + _NAV_H // 2 - 7)))

            lbl = self._f_sub.render(label, True, col_lbl)
            s.blit(lbl, lbl.get_rect(center=(ix + iw // 2, ny + _NAV_H - 10)))

            if app == PhoneApp.MESSAGES:
                u = self.get_unread_messages_count()
                if u > 0:
                    self._badge(s, str(min(u, 9)), ix + iw - 14, ny + 6)

            self._nav_rects.append((pygame.Rect(ix, ny, iw, _NAV_H), app))

    # ── Content dispatch ───────────────────────────────────────────

    def _draw_content(self, s):
        {
            PhoneApp.ACADEMIC: self._app_academic,
            PhoneApp.SOCIAL:   self._app_social,
            PhoneApp.MESSAGES: self._app_messages,
            PhoneApp.SCHEDULE: self._app_schedule,
        }.get(self.current_app, lambda *_: None)(s, _CX, _CY, _CW, _CH)

    # ══════════════════════════════════════════════════════════
    #  APP — ACADEMIC
    # ══════════════════════════════════════════════════════════

    def _app_academic(self, s, cx, cy, cw, ch):
        self._task_rects = []
        self._back_rect  = None

        if self.active_task:
            self._academic_detail(s, cx, cy, cw, ch, self.active_task)
            return

        y = cy + _PAD
        self._text(s, "Portal Académico", self._f_sec, PH_CYAN, cx + _PAD, y)
        y += 16

        p = sum(1 for t in self.academic_tasks if t.status == "pending")
        i = sum(1 for t in self.academic_tasks if t.status == "in_progress")
        d = sum(1 for t in self.academic_tasks if t.status == "completed")
        self._text(s, f"{p} pend.  {i} en progreso  {d} hechas",
                   self._f_sub, PH_TEXT_S, cx + _PAD, y)
        y += 13

        pygame.draw.line(s, PH_BD, (cx + _PAD, y), (cx + cw - _PAD, y))
        y += _GAP

        sc = self._scroll[PhoneApp.ACADEMIC]
        IH = 58
        yoff = y - sc

        for task in self.academic_tasks:
            if yoff + IH < cy:
                yoff += IH + _GAP
                continue
            if yoff > cy + ch:
                break

            card = pygame.Rect(cx + _PAD, yoff, cw - _PAD * 2, IH)
            self._rrect(s, PH_CARD, card, 8)

            col = _SC.get(task.status, PH_TEXT_D)
            pygame.draw.rect(s, col, (card.x, card.y + 4, 3, IH - 8), border_radius=2)

            tx, ty2 = card.x + 10, card.y + 6
            self._clip_text(s, task.title, self._f_title, PH_TEXT, tx, ty2, cw - _PAD * 2 - 20)
            ty2 += 14
            self._text(s, f"de {task.issuer}", self._f_sub, PH_TEXT_S, tx, ty2)

            if task.deadline:
                dl = self._f_sub.render(f"⏰ {task.deadline}", True, PH_AMBER)
                s.blit(dl, (card.right - dl.get_width() - 6, card.y + 6))

            bx2, bary = tx, card.bottom - 10
            bw = card.w - 20
            pygame.draw.rect(s, PH_BD, (bx2, bary, bw, 4), border_radius=2)
            fw = int(bw * max(0.0, min(1.0, task.progress)))
            if fw > 0:
                pygame.draw.rect(s, col, (bx2, bary, fw, 4), border_radius=2)
            if task.status == "completed":
                ck = self._f_sub.render("✓", True, PH_GREEN)
                s.blit(ck, (card.right - 14, card.bottom - 14))

            self._task_rects.append((card, task))
            yoff += IH + _GAP

    def _academic_detail(self, s, cx, cy, cw, ch, task):
        br = pygame.Rect(cx + _PAD, cy + _PAD, 54, 20)
        self._rrect(s, PH_CARD2, br, 6)
        bk = self._f_sub.render("← Volver", True, PH_CYAN)
        s.blit(bk, bk.get_rect(center=br.center))
        self._back_rect = br

        y = cy + _PAD + 28
        col = _SC.get(task.status, PH_TEXT_D)
        slbl = _SL.get(task.status, "")
        sr = pygame.Rect(cx + _PAD, y, 82, 18)
        pygame.draw.rect(s, col, sr, border_radius=4, width=1)
        sl = self._f_sub.render(slbl, True, col)
        s.blit(sl, sl.get_rect(center=sr.center))
        y += 24

        self._text(s, task.title, self._f_title, PH_TEXT, cx + _PAD, y)
        y += 16
        self._text(s, f"Por: {task.issuer}", self._f_sub, PH_TEXT_S, cx + _PAD, y)
        y += 13
        if task.deadline:
            self._text(s, f"Entrega: {task.deadline}", self._f_sub, PH_AMBER, cx + _PAD, y)
            y += 13
        y += _GAP
        pygame.draw.line(s, PH_BD, (cx + _PAD, y), (cx + cw - _PAD, y))
        y += _GAP
        y = self._wrap_text(s, task.description, self._f_body, PH_TEXT_S,
                            cx + _PAD, y, cw - _PAD * 2, 13)
        y += _GAP
        if task.status != "completed":
            self._text(s, f"Progreso: {int(task.progress * 100)}%",
                       self._f_sub, PH_TEXT_S, cx + _PAD, y)
            y += 13
            bw = cw - _PAD * 2
            pygame.draw.rect(s, PH_BD, (cx + _PAD, y, bw, 6), border_radius=3)
            fw = int(bw * task.progress)
            if fw > 0:
                pygame.draw.rect(s, col, (cx + _PAD, y, fw, 6), border_radius=3)

    # ══════════════════════════════════════════════════════════
    #  APP — SOCIAL
    # ══════════════════════════════════════════════════════════

    def _app_social(self, s, cx, cy, cw, ch):
        self._post_rects  = []
        self._like_rects  = []
        self._filter_rects= []

        y = cy + _PAD
        self._text(s, "EscuelaNet", self._f_sec, PH_PINK, cx + _PAD, y)
        y += 16

        # Filter tabs
        filters = [("all", "Todo"), ("anonymous", "Anónimos"), ("mentions", "Menciones")]
        tw = (cw - _PAD * 2) // len(filters)
        for i, (fid, flbl) in enumerate(filters):
            tr = pygame.Rect(cx + _PAD + i * tw, y, tw - 2, 18)
            active_f = (fid == self.social_filter)
            self._rrect(s, PH_CARD2 if active_f else PH_CARD, tr, 5)
            if active_f:
                pygame.draw.rect(s, PH_PINK, tr, border_radius=5, width=1)
            fl = self._f_sub.render(flbl, True, PH_PINK if active_f else PH_TEXT_S)
            s.blit(fl, fl.get_rect(center=tr.center))
            self._filter_rects.append((tr, fid))
        y += 24

        pygame.draw.line(s, PH_BD, (cx + _PAD, y), (cx + cw - _PAD, y))
        y += _GAP

        player = self.player_name
        posts = [p for p in self.social_posts if
                 self.social_filter == "all" or
                 (self.social_filter == "anonymous" and p.is_anonymous) or
                 (self.social_filter == "mentions" and
                  player in [m.lower() for m in p.mentions])]

        sc = self._scroll[PhoneApp.SOCIAL]
        PH = 72
        yoff = y - sc

        for post in posts:
            if yoff + PH < cy:
                yoff += PH + _GAP
                continue
            if yoff > cy + ch:
                break

            is_m = player in [m.lower() for m in post.mentions]
            if is_m:
                bg, bd = PH_MENC_BG, PH_MENC_BD
            elif post.is_anonymous:
                bg, bd = PH_ANON_BG, PH_ANON_BD
            else:
                bg, bd = PH_CARD, PH_BD

            card = pygame.Rect(cx + _PAD, yoff, cw - _PAD * 2, PH)
            self._rrect(s, bg, card, 8, bd, 1)

            # Author
            a_str = "Anónimo" if post.is_anonymous else post.author
            a_col = PH_TEXT_D if post.is_anonymous else PH_TEXT
            at = self._f_title.render(a_str, True, a_col)
            s.blit(at, (card.x + 8, card.y + 6))

            # Timestamp
            ts_s = self._f_sub.render(post.timestamp, True, PH_TEXT_D)
            s.blit(ts_s, (card.right - ts_s.get_width() - 6, card.y + 7))

            # Content
            self._clip_text(s, post.content, self._f_body, PH_TEXT,
                            card.x + 8, card.y + 20, cw - _PAD * 2 - 16)

            # Second line of content
            if len(post.content) > 38:
                cont2 = post.content[38:72] + ("…" if len(post.content) > 72 else "")
                self._clip_text(s, cont2, self._f_body, PH_TEXT_S,
                                card.x + 8, card.y + 32, cw - _PAD * 2 - 16)

            # Like btn
            lk_col = PH_PINK if post._liked else PH_TEXT_D
            lk = self._f_sub.render(f"♥ {post.likes}", True, lk_col)
            lk_r = pygame.Rect(card.x + 8, card.bottom - 16, 48, 14)
            s.blit(lk, lk_r.topleft)
            self._like_rects.append((lk_r, post))

            if is_m:
                mb = self._f_sub.render("@ te mencionó", True, PH_CYAN)
                s.blit(mb, (card.right - mb.get_width() - 6, card.bottom - 16))

            self._post_rects.append((card, post))
            yoff += PH + _GAP

    # ══════════════════════════════════════════════════════════
    #  APP — MESSAGES
    # ══════════════════════════════════════════════════════════

    def _app_messages(self, s, cx, cy, cw, ch):
        self._chat_rects  = []
        self._back_rect   = None
        self._reply_rects = []

        y = cy + _PAD
        self._text(s, "Mensajes", self._f_sec, PH_CYAN, cx + _PAD, y)
        y += 16
        pygame.draw.line(s, PH_BD, (cx + _PAD, y), (cx + cw - _PAD, y))
        y += _GAP

        if self.active_chat is not None:
            self._chat_view(s, cx, y, cw, cy + ch - y)
        else:
            self._conv_list(s, cx, y, cw, cy + ch - y)

    def _conv_list(self, s, cx, y, cw, avail_h):
        if not self.messages:
            self._text(s, "Sin mensajes.", self._f_body, PH_TEXT_D, cx + _PAD, y + 20)
            return

        sc = self._scroll[PhoneApp.MESSAGES]
        IH = 52
        yoff = y - sc

        for npc_id, msgs in self.messages.items():
            if not msgs:
                continue
            last   = msgs[-1]
            unread = sum(1 for m in msgs if not m.is_read and not m.is_player)

            card = pygame.Rect(cx + _PAD, yoff, cw - _PAD * 2, IH)
            if card.bottom < y or card.top > y + avail_h:
                yoff += IH + _GAP
                continue

            self._rrect(s, PH_CARD2 if unread else PH_CARD, card, 8)

            # Avatar
            avc = (card.x + 22, card.centery)
            pygame.draw.circle(s, PH_CYAN_DIM, avc, 16)
            init = self._f_title.render(last.sender_name[0].upper(), True, PH_TEXT)
            s.blit(init, init.get_rect(center=avc))

            # Name + preview
            self._text(s, last.sender_name, self._f_title, PH_TEXT, card.x + 44, card.y + 7)
            prev = last.content[:24] + ("…" if len(last.content) > 24 else "")
            self._text(s, prev, self._f_sub, PH_TEXT_S, card.x + 44, card.y + 22)

            if unread > 0:
                self._badge(s, str(min(unread, 9)), card.right - 18, card.y + 8)

            self._chat_rects.append((card, npc_id))
            yoff += IH + _GAP

    def _chat_view(self, s, cx, y, cw, avail_h):
        msgs = self.messages.get(self.active_chat, [])
        npc_name = msgs[0].sender_name if msgs else "Chat"

        # Back btn
        br = pygame.Rect(cx + _PAD, y, 40, 18)
        self._rrect(s, PH_CARD2, br, 5)
        bk = self._f_sub.render("←", True, PH_CYAN)
        s.blit(bk, bk.get_rect(center=br.center))
        self._back_rect = br

        nm = self._f_title.render(npc_name, True, PH_TEXT)
        s.blit(nm, nm.get_rect(midleft=(br.right + 6, br.centery)))
        y += 26

        pygame.draw.line(s, PH_BD, (cx + _PAD, y), (cx + cw - _PAD, y))
        y += _GAP

        # Reply options at bottom
        reply_opts = []
        if msgs:
            last_npc = [m for m in msgs if not m.is_player]
            if last_npc:
                reply_opts = last_npc[-1].reply_options or []

        reply_h = (len(reply_opts) * 22 + _PAD) if reply_opts else 0
        chat_area_h = avail_h - (y - (y)) - reply_h  # fix: use full remaining
        chat_area_h = avail_h - reply_h

        # Bubbles (scroll from bottom up)
        sc = self._scroll[PhoneApp.MESSAGES]
        BH = 30
        total = len(msgs) * (BH + _GAP)
        start_y = y + max(0, chat_area_h - total) - sc

        for msg in msgs:
            my = start_y
            mw = cw - _PAD * 2 - 16
            is_p = msg.is_player
            bg   = PH_BUB_P if is_p else PH_BUB_N
            words = msg.content.split()
            line, lines = "", []
            for w in words:
                test = (line + " " + w).strip()
                if self._f_body.size(test)[0] <= mw - 16:
                    line = test
                else:
                    if line:
                        lines.append(line)
                    line = w
            if line:
                lines.append(line)

            bh = max(BH, len(lines) * 13 + 10)
            bw = min(mw, max(60, max((self._f_body.size(l)[0] for l in lines), default=60) + 16))

            if is_p:
                bx = cx + cw - _PAD - bw
            else:
                bx = cx + _PAD

            bub = pygame.Rect(bx, my, bw, bh)
            corner = 10
            self._rrect(s, bg, bub, corner)

            for li, ln in enumerate(lines):
                lt = self._f_body.render(ln, True, PH_TEXT)
                s.blit(lt, (bub.x + 8, bub.y + 5 + li * 13))

            # Timestamp
            ts_s = self._f_sub.render(msg.timestamp, True, PH_TEXT_D)
            if is_p:
                s.blit(ts_s, (bub.left - ts_s.get_width() - 4, bub.centery))
            else:
                s.blit(ts_s, (bub.right + 4, bub.centery))

            start_y += bh + _GAP

        # Reply options
        if reply_opts:
            ry = y + chat_area_h
            self._reply_rects = []
            for i, opt in enumerate(reply_opts[:3]):
                rr = pygame.Rect(cx + _PAD, ry + i * 22, cw - _PAD * 2, 20)
                self._rrect(s, PH_CARD2, rr, 5, PH_CYAN, 1)
                ot = self._f_sub.render(opt[:38], True, PH_CYAN)
                s.blit(ot, ot.get_rect(midleft=(rr.x + 6, rr.centery)))
                self._reply_rects.append((rr, opt))

    # ══════════════════════════════════════════════════════════
    #  APP — SCHEDULE
    # ══════════════════════════════════════════════════════════

    def _app_schedule(self, s, cx, cy, cw, ch):
        y = cy + _PAD
        self._text(s, "Horario Escolar", self._f_sec, PH_CYAN, cx + _PAD, y)
        y += 16
        pygame.draw.line(s, PH_BD, (cx + _PAD, y), (cx + cw - _PAD, y))
        y += _GAP

        cur_mins = int(self.time_source()) if self.time_source else -1
        cur_h    = cur_mins // 60 if cur_mins >= 0 else -1

        if not self.schedule_events:
            self._text(s, "Sin eventos programados.", self._f_body, PH_TEXT_D, cx + _PAD, y + 20)
            return

        sc   = self._scroll[PhoneApp.SCHEDULE]
        EH   = 52
        yoff = y - sc

        # Find current / next event
        cur_idx  = -1
        next_idx = -1
        for ei, ev in enumerate(self.schedule_events):
            if ev.hour <= cur_h:
                cur_idx = ei
            elif next_idx == -1:
                next_idx = ei

        for ei, ev in enumerate(self.schedule_events):
            if yoff + EH < cy:
                yoff += EH + _GAP
                continue
            if yoff > cy + ch:
                break

            is_cur  = (ei == cur_idx)
            is_next = (ei == next_idx)

            bd_col = PH_CYAN if is_cur else (PH_AMBER if is_next else PH_BD)
            bg_col = (16, 28, 40) if is_cur else ((26, 24, 14) if is_next else PH_CARD)

            card = pygame.Rect(cx + _PAD, yoff, cw - _PAD * 2, EH)
            self._rrect(s, bg_col, card, 8, bd_col, 1)

            # Hour badge
            h12 = ev.hour % 12 or 12
            sfx = "am" if ev.hour < 12 else "pm"
            hr_str = f"{h12}{sfx}"
            hr_s = self._f_title.render(hr_str, True, bd_col)
            s.blit(hr_s, (card.x + 8, card.y + 6))

            # Event name + location
            self._text(s, ev.name, self._f_title, PH_TEXT, card.x + 56, card.y + 6)
            self._text(s, ev.location, self._f_sub, PH_TEXT_S, card.x + 56, card.y + 22)

            if ev.description:
                self._clip_text(s, ev.description, self._f_sub, PH_TEXT_D,
                                card.x + 56, card.y + 34, cw - _PAD * 2 - 60)

            if is_cur:
                tag = self._f_badge.render("AHORA", True, PH_CYAN)
                s.blit(tag, (card.right - tag.get_width() - 6, card.y + 6))
            elif is_next:
                tag = self._f_badge.render("PRÓXIMO", True, PH_AMBER)
                s.blit(tag, (card.right - tag.get_width() - 6, card.y + 6))

            yoff += EH + _GAP

    # ══════════════════════════════════════════════════════════
    #  HUD ICON  (called from ui.py draw_hud)
    # ══════════════════════════════════════════════════════════

    def draw_hud_icon(self, screen: pygame.Surface, rect: pygame.Rect,
                      unread: int = 0):
        """Draw phone HUD icon (call this from UI.draw_hud)."""
        # Body
        pygame.draw.rect(screen, (22, 22, 32), rect, border_radius=7)
        pygame.draw.rect(screen, PH_CYAN, rect, border_radius=7, width=2)
        # Screen
        scr = rect.inflate(-8, -10)
        scr.y += 2
        pygame.draw.rect(screen, (12, 12, 20), scr, border_radius=4)
        # Home button dot
        hb_x, hb_y = rect.centerx, rect.bottom - 5
        pygame.draw.circle(screen, PH_CYAN, (hb_x, hb_y), 3)
        # Badge
        if unread > 0:
            bx = rect.right - 8
            by = rect.top - 2
            pygame.draw.circle(screen, PH_RED, (bx, by), 7)
            bt = pygame.font.SysFont("arial", 9, bold=True).render(
                str(min(unread, 9)), True, WHITE)
            screen.blit(bt, bt.get_rect(center=(bx, by)))
        # Hover glow
        if rect.collidepoint(pygame.mouse.get_pos()):
            glow = rect.inflate(6, 6)
            pygame.draw.rect(screen, (255, 220, 80), glow, border_radius=9, width=2)

    # ══════════════════════════════════════════════════════════
    #  INPUT HANDLING
    # ══════════════════════════════════════════════════════════

    def handle_input(self, event: pygame.event.Event) -> bool:
        """Return True if event was consumed."""
        if not self.is_visible:
            return False

        if event.type == pygame.MOUSEWHEEL:
            self._scroll[self.current_app] = max(
                0, self._scroll[self.current_app] - event.y * 20)
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self._on_click(event.pos)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.close()
                return True
            if event.key == pygame.K_UP:
                self._scroll[self.current_app] = max(
                    0, self._scroll[self.current_app] - 30)
                return True
            if event.key == pygame.K_DOWN:
                self._scroll[self.current_app] += 30
                return True

        return False

    def _on_click(self, screen_pos: tuple) -> bool:
        """Map screen click to phone-local coords and dispatch."""
        if self.state != PhoneState.OPEN:
            return False

        p = self._ease_out(self._anim_t)
        scale = 0.90 + 0.10 * p
        sw = int(PHONE_W * scale)
        sh = int(PHONE_H * scale)
        bx = PHONE_X + (PHONE_W - sw) // 2
        by = PHONE_Y + (PHONE_H - sh) // 2

        phone_rect = pygame.Rect(bx, by, sw, sh)
        if not phone_rect.collidepoint(screen_pos):
            self.close()
            return True

        # Convert to local coords
        lx = int((screen_pos[0] - bx) / scale)
        ly = int((screen_pos[1] - by) / scale)
        local = (lx, ly)

        # Back button
        if self._back_rect and self._back_rect.collidepoint(local):
            self.active_task = None
            self.active_chat = None
            return True

        # Nav bar
        for rect, app in self._nav_rects:
            if rect.collidepoint(local):
                self.current_app = app
                self._scroll[app] = 0
                return True

        # App-specific
        if self.current_app == PhoneApp.ACADEMIC:
            for rect, task in self._task_rects:
                if rect.collidepoint(local):
                    self.active_task = task
                    return True

        elif self.current_app == PhoneApp.SOCIAL:
            for rect, fid in self._filter_rects:
                if rect.collidepoint(local):
                    self.social_filter = fid
                    self._scroll[PhoneApp.SOCIAL] = 0
                    return True
            for rect, post in self._like_rects:
                if rect.collidepoint(local):
                    if not post._liked:
                        post._liked = True
                        post.likes += 1
                    return True

        elif self.current_app == PhoneApp.MESSAGES:
            for rect, npc_id in self._chat_rects:
                if rect.collidepoint(local):
                    self.active_chat = npc_id
                    self.mark_messages_read(npc_id)
                    self._scroll[PhoneApp.MESSAGES] = 0
                    return True
            for rect, opt in self._reply_rects:
                if rect.collidepoint(local):
                    self._send_reply(opt)
                    return True

        return True   # consumed (anywhere on phone)

    def _send_reply(self, text: str):
        """Record a player reply in the active chat."""
        if not self.active_chat:
            return
        npc_msgs = self.messages.get(self.active_chat, [])
        reply_id = f"reply_{len(npc_msgs)}"
        msg = TextMessage(
            id=reply_id,
            sender_npc_id="player",
            sender_name="Tú",
            content=text,
            timestamp="ahora",
            is_read=True,
            is_player=True,
        )
        self.messages.setdefault(self.active_chat, []).append(msg)

    # ══════════════════════════════════════════════════════════
    #  UTILITIES
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _ease_out(t: float) -> float:
        return 1.0 - (1.0 - t) ** 3

    def _rrect(self, surf, color, rect, radius, border_color=None, bw=0):
        pygame.draw.rect(surf, color, rect, border_radius=radius)
        if border_color and bw > 0:
            pygame.draw.rect(surf, border_color, rect,
                             border_radius=radius, width=bw)

    def _text(self, surf, text, font, color, x, y):
        t = font.render(str(text), True, color)
        surf.blit(t, (x, y))

    def _clip_text(self, surf, text, font, color, x, y, max_w):
        t = font.render(str(text), True, color)
        if t.get_width() > max_w:
            clip = surf.get_clip()
            surf.set_clip(pygame.Rect(x, y, max_w, t.get_height()).clip(clip))
            surf.blit(t, (x, y))
            surf.set_clip(clip)
        else:
            surf.blit(t, (x, y))

    def _wrap_text(self, surf, text, font, color, x, y, max_w, line_h) -> int:
        words = str(text).split()
        line = ""
        for w in words:
            test = (line + " " + w).strip()
            if font.size(test)[0] <= max_w:
                line = test
            else:
                if line:
                    self._text(surf, line, font, color, x, y)
                    y += line_h
                line = w
        if line:
            self._text(surf, line, font, color, x, y)
            y += line_h
        return y

    def _badge(self, surf, text, cx, cy):
        pygame.draw.circle(surf, PH_RED, (cx, cy), 7)
        t = self._f_badge.render(str(text), True, WHITE)
        surf.blit(t, t.get_rect(center=(cx, cy)))
