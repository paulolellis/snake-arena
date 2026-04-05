"""
Snake Arena — Smooth Edition
Fine hex/square grid, spline-rendered snakes that grow in width,
proximity-based pickups, 60 FPS with interpolated movement.
Customizable key bindings. Player labels on snakes.
"""

import pygame
import random
import math
import sys
import json
import os
from enum import Enum, auto
from collections import deque

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CELL = 4                          # 5x smaller than original
MIN_COLS, MIN_ROWS = 120, 80
PANEL_H = 70
FPS = 60
GAME_TPS = 16                    # game logic ticks per second
TICK_INTERVAL = 1.0 / GAME_TPS
PICKUP_RADIUS = 14               # pixel distance for food pickup
INITIAL_BODY_LEN = 18
FOOD_GROW = 5
WIDTH_GROW = 0.6
INITIAL_WIDTH = 5.0
MAX_WIDTH = 22.0

# Square directions
UP = (0, -1); DOWN = (0, 1); LEFT = (-1, 0); RIGHT = (1, 0)
DIRS = [UP, DOWN, LEFT, RIGHT]

# Colors
BG = (12, 12, 22)
WHITE = (255, 255, 255)
GRAY = (160, 160, 160)
DARK_GRAY = (80, 80, 80)
YELLOW = (255, 220, 50)
RED = (220, 50, 50)
MENU_BG = (10, 10, 20)
HIGHLIGHT = (80, 180, 255)

SNAKE_COLORS = [
    ((50, 200, 80), (30, 160, 60)),
    ((60, 130, 230), (40, 100, 190)),
    ((230, 160, 40), (190, 120, 20)),
    ((200, 60, 200), (160, 30, 160)),
    ((220, 60, 60), (180, 40, 40)),
    ((60, 210, 210), (30, 170, 170)),
    ((210, 210, 60), (170, 170, 30)),
    ((255, 130, 170), (210, 90, 130)),
    ((140, 100, 60), (100, 70, 40)),
    ((180, 180, 180), (130, 130, 130)),
]
MAX_SNAKES = len(SNAKE_COLORS)

# ---------------------------------------------------------------------------
# Key bindings — defaults closer to Enter for P1, customizable via JSON
# ---------------------------------------------------------------------------
# Square defaults:  P1=Arrows (near enter), P2=WASD, P3=IJKL, P4=Numpad
DEFAULT_SQ_KEYS = [
    {"up": "K_UP", "down": "K_DOWN", "left": "K_LEFT", "right": "K_RIGHT"},
    {"up": "K_w", "down": "K_s", "left": "K_a", "right": "K_d"},
    {"up": "K_i", "down": "K_k", "left": "K_j", "right": "K_l"},
    {"up": "K_KP8", "down": "K_KP5", "left": "K_KP4", "right": "K_KP6"},
]
# Hex defaults: P1=arrows+./comma  P2=QWADZX  P3=numpad
DEFAULT_HEX_KEYS = [
    {"E": "K_RIGHT", "W": "K_LEFT", "NE": "K_UP", "NW": "K_PERIOD",
     "SE": "K_DOWN", "SW": "K_COMMA"},
    {"E": "K_d", "W": "K_a", "NE": "K_w", "NW": "K_q",
     "SE": "K_x", "SW": "K_z"},
    {"E": "K_KP6", "W": "K_KP4", "NE": "K_KP9", "NW": "K_KP7",
     "SE": "K_KP3", "SW": "K_KP1"},
]

KEYBIND_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keybinds.json")


def _key_name_to_const(name: str) -> int:
    return getattr(pygame, name)


def load_keybinds():
    sq, hx = DEFAULT_SQ_KEYS, DEFAULT_HEX_KEYS
    if os.path.exists(KEYBIND_FILE):
        try:
            with open(KEYBIND_FILE) as f:
                data = json.load(f)
            sq = data.get("square", sq)
            hx = data.get("hex", hx)
        except Exception:
            pass
    return sq, hx


def save_keybinds(sq, hx):
    with open(KEYBIND_FILE, "w") as f:
        json.dump({"square": sq, "hex": hx}, f, indent=2)


def build_key_maps(raw_list):
    """Convert list of {dir_name: 'K_xxx'} dicts to [{pygame_key: dir_value}]."""
    result = []
    for player_map in raw_list:
        km = {}
        for dir_name, key_name in player_map.items():
            pygame_key = _key_name_to_const(key_name)
            # For square, convert string "up"/"down" etc. to tuple
            if dir_name == "up":
                km[pygame_key] = UP
            elif dir_name == "down":
                km[pygame_key] = DOWN
            elif dir_name == "left":
                km[pygame_key] = LEFT
            elif dir_name == "right":
                km[pygame_key] = RIGHT
            else:
                km[pygame_key] = dir_name  # hex direction string
        result.append(km)
    return result


# Hex direction data (even-r offset, pointy-top)
HEX_DIR_NAMES = ["E", "W", "NE", "NW", "SE", "SW"]
HEX_OFFSETS = {
    0: {"E": (1, 0), "W": (-1, 0), "NE": (0, -1), "NW": (-1, -1),
        "SE": (0, 1), "SW": (-1, 1)},
    1: {"E": (1, 0), "W": (-1, 0), "NE": (1, -1), "NW": (0, -1),
        "SE": (1, 1), "SW": (0, 1)},
}
HEX_REVERSE = {"E": "W", "W": "E", "NE": "SW", "SW": "NE", "NW": "SE", "SE": "NW"}


class GridMode(Enum):
    SQUARE = auto()
    HEX = auto()


# ---------------------------------------------------------------------------
# Catmull-Rom spline
# ---------------------------------------------------------------------------
def catmull_rom_chain(points, steps=3):
    if len(points) < 2:
        return list(points)
    if len(points) == 2:
        return list(points)
    result = []
    pts = [points[0]] + list(points) + [points[-1]]
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for t_idx in range(steps):
            t = t_idx / steps
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2*p1[0]) + (-p0[0]+p2[0])*t +
                        (2*p0[0]-5*p1[0]+4*p2[0]-p3[0])*t2 +
                        (-p0[0]+3*p1[0]-3*p2[0]+p3[0])*t3)
            y = 0.5 * ((2*p1[1]) + (-p0[1]+p2[1])*t +
                        (2*p0[1]-5*p1[1]+4*p2[1]-p3[1])*t2 +
                        (-p0[1]+3*p1[1]-3*p2[1]+p3[1])*t3)
            result.append((x, y))
    result.append(pts[-2])
    return result


def build_contour(spine, head_w, tail_ratio=0.25):
    if len(spine) < 2:
        return []
    n = len(spine)
    left, right = [], []
    for i in range(n):
        if i == 0:
            tx, ty = spine[1][0]-spine[0][0], spine[1][1]-spine[0][1]
        elif i == n-1:
            tx, ty = spine[-1][0]-spine[-2][0], spine[-1][1]-spine[-2][1]
        else:
            tx, ty = spine[i+1][0]-spine[i-1][0], spine[i+1][1]-spine[i-1][1]
        ln = math.hypot(tx, ty)
        nx, ny = (-ty/ln, tx/ln) if ln > 0.001 else (0, 1)
        frac = i / max(n-1, 1)
        if frac < 0.15:
            w = head_w * (0.7 + 0.3*(frac/0.15))
        elif frac < 0.3:
            w = head_w
        else:
            w = head_w * (1.0 - (1.0-tail_ratio)*((frac-0.3)/0.7))
        hw = w * 0.5
        left.append((spine[i][0]+nx*hw, spine[i][1]+ny*hw))
        right.append((spine[i][0]-nx*hw, spine[i][1]-ny*hw))
    right.reverse()
    return left + right


# ---------------------------------------------------------------------------
# Grid classes
# ---------------------------------------------------------------------------
class SquareGrid:
    mode = GridMode.SQUARE
    def __init__(self, c, r): self.cols, self.rows = c, r
    def directions(self): return list(DIRS)
    def offset(self, p, d): return (p[0]+d[0], p[1]+d[1])
    def reverse_dir(self, d): return (-d[0], -d[1])
    def is_reverse(self, a, b): return a == (-b[0], -b[1])
    def wrap(self, p): return (p[0]%self.cols, p[1]%self.rows)
    def in_bounds(self, p): return 0<=p[0]<self.cols and 0<=p[1]<self.rows
    def distance(self, a, b): return abs(a[0]-b[0])+abs(a[1]-b[1])
    def cell_to_pixel(self, p): return (p[0]*CELL+CELL*0.5, p[1]*CELL+CELL*0.5+PANEL_H)
    def direction_to_pixel_offset(self, d): return (float(d[0]), float(d[1]))
    def grid_pixel_size(self): return (self.cols*CELL, self.rows*CELL)

    def infer_direction(self, fr, to):
        d = (to[0]-fr[0], to[1]-fr[1])
        if d in DIRS: return d
        for di in DIRS:
            if self.wrap(self.offset(fr, di)) == to: return di
        return RIGHT

    def pick_start_direction(self, sx, sy, cx, cy):
        dx = 1 if cx>sx else -1 if cx<sx else 0
        dy = 1 if cy>sy else -1 if cy<sy else 0
        d = (dx,0) if abs(cx-sx)>=abs(cy-sy) else (0,dy)
        return d if d != (0,0) else RIGHT

    @staticmethod
    def grid_from_window(w, h):
        return max(MIN_COLS, w//CELL), max(MIN_ROWS, (h-PANEL_H)//CELL)


class HexGrid:
    mode = GridMode.HEX
    def __init__(self, c, r):
        self.cols, self.rows = c, r
        self.hex_size = CELL * 0.58
        self.hex_w = math.sqrt(3) * self.hex_size
        self.hex_h = 2 * self.hex_size
    def directions(self): return list(HEX_DIR_NAMES)
    def offset(self, p, d):
        dc, dr = HEX_OFFSETS[p[1]&1][d]; return (p[0]+dc, p[1]+dr)
    def reverse_dir(self, d): return HEX_REVERSE[d]
    def is_reverse(self, a, b): return a == HEX_REVERSE.get(b)
    def wrap(self, p): return (p[0]%self.cols, p[1]%self.rows)
    def in_bounds(self, p): return 0<=p[0]<self.cols and 0<=p[1]<self.rows
    def _to_cube(self, c, r):
        q = c-(r+(r&1))//2; return (q, r, -q-r)
    def distance(self, a, b):
        aq,ar,as_ = self._to_cube(*a); bq,br,bs = self._to_cube(*b)
        return max(abs(aq-bq), abs(ar-br), abs(as_-bs))
    def cell_to_pixel(self, p):
        return (p[0]*self.hex_w+(p[1]&1)*self.hex_w*0.5+self.hex_w*0.5,
                p[1]*self.hex_h*0.75+self.hex_size+PANEL_H)
    def direction_to_pixel_offset(self, d):
        m = {"E":(1,0),"W":(-1,0),"NE":(0.5,-0.87),"NW":(-0.5,-0.87),
             "SE":(0.5,0.87),"SW":(-0.5,0.87)}
        return m.get(d,(1,0))
    def grid_pixel_size(self):
        return (int(self.cols*self.hex_w+self.hex_w*0.5+2),
                int(self.rows*self.hex_h*0.75+self.hex_size+2))
    def infer_direction(self, fr, to):
        for d in HEX_DIR_NAMES:
            if self.offset(fr, d) == to: return d
        for d in HEX_DIR_NAMES:
            if self.wrap(self.offset(fr, d)) == to: return d
        return "E"
    def pick_start_direction(self, sx, sy, cx, cy):
        return min(HEX_DIR_NAMES, key=lambda d: abs(self.offset((sx,sy),d)[0]-cx)+abs(self.offset((sx,sy),d)[1]-cy))
    @staticmethod
    def grid_from_window(w, h):
        hs = CELL*0.58; hw = math.sqrt(3)*hs; hh = 2*hs
        return max(MIN_COLS, int(w/hw)-1), max(MIN_ROWS, int((h-PANEL_H)/(hh*0.75))-1)


# ---------------------------------------------------------------------------
# Specials
# ---------------------------------------------------------------------------
class SpecialType(Enum):
    FOOD=auto(); SPEED_BOOST=auto(); SLOW_ZONE=auto(); SHIELD=auto()
    REVERSE=auto(); MAGNET=auto(); BOMB=auto(); GHOST=auto(); GOLDEN_APPLE=auto()

SPECIAL_INFO = {
    SpecialType.FOOD:         ("Food",         (255,50,50),   "●", None),
    SpecialType.SPEED_BOOST:  ("Speed Boost",  (255,255,80),  "⚡", 80),
    SpecialType.SLOW_ZONE:    ("Slow",         (100,100,255), "❄", 80),
    SpecialType.SHIELD:       ("Shield",       (200,200,255), "🛡", None),
    SpecialType.REVERSE:      ("Reverse",      (255,100,255), "⟳", None),
    SpecialType.MAGNET:       ("Magnet",       (255,160,60),  "⊕", 100),
    SpecialType.BOMB:         ("Bomb",         (255,80,30),   "💣", None),
    SpecialType.GHOST:        ("Ghost",        (180,255,220), "👻", 80),
    SpecialType.GOLDEN_APPLE: ("Golden Apple", (255,215,0),   "★", None),
}


class Special:
    def __init__(self, kind, pos):
        self.kind, self.pos = kind, pos
        self.timer, self.pulse = 300, 0

    def draw(self, surf, font, grid):
        _, color, symbol, _ = SPECIAL_INFO[self.kind]
        self.pulse = (self.pulse + 0.05) % (2*math.pi)
        scale = 1.0 + 0.15*math.sin(self.pulse)
        px, py = grid.cell_to_pixel(self.pos)
        x, y = int(px), int(py)
        # Pickup aura
        pygame.draw.circle(surf, tuple(max(0,c-180) for c in color), (x,y), int(PICKUP_RADIUS*1.2), 1)
        r = int(6 * scale)
        if self.kind == SpecialType.FOOD:
            pygame.draw.circle(surf, color, (x,y), r)
        elif self.kind == SpecialType.GOLDEN_APPLE:
            pygame.draw.circle(surf, color, (x,y), r+1)
            for a in range(0,360,60):
                sx = x+int((r+4)*math.cos(math.radians(a+self.pulse*30)))
                sy = y+int((r+4)*math.sin(math.radians(a+self.pulse*30)))
                pygame.draw.circle(surf, WHITE, (sx,sy), 1)
        elif self.kind == SpecialType.BOMB:
            pygame.draw.circle(surf, (60,60,60), (x,y), r)
            pygame.draw.circle(surf, color, (x,y), r, 2)
        elif self.kind == SpecialType.SHIELD:
            pygame.draw.circle(surf, (150,150,255), (x,y), r)
            pygame.draw.circle(surf, color, (x,y), r, 2)
        else:
            pygame.draw.circle(surf, color, (x,y), r)
            pygame.draw.circle(surf, WHITE, (x,y), r, 1)


# ---------------------------------------------------------------------------
# Particle
# ---------------------------------------------------------------------------
class Particle:
    def __init__(self, x, y, color):
        self.x, self.y = float(x), float(y)
        a = random.uniform(0, 2*math.pi); s = random.uniform(1,4)
        self.vx, self.vy = math.cos(a)*s, math.sin(a)*s
        self.life = random.randint(10,25)
        self.color = color; self.r = random.randint(2,4)
    def update(self):
        self.x += self.vx; self.y += self.vy; self.life -= 1
        self.r = max(1, self.r-0.1)
    def draw(self, surf):
        if self.life > 0:
            al = max(0, min(255, self.life*12))
            c = tuple(min(255, int(ch*al/255)) for ch in self.color)
            pygame.draw.circle(surf, c, (int(self.x), int(self.y)), int(self.r))


# ---------------------------------------------------------------------------
# Snake
# ---------------------------------------------------------------------------
class Snake:
    def __init__(self, idx, start_pos, direction, is_ai, wrap_walls, grid):
        self.idx, self.is_ai, self.wrap_walls, self.grid = idx, is_ai, wrap_walls, grid
        self.body: deque[tuple[int,int]] = deque()
        self.direction = self.next_direction = direction
        self.alive, self.score = True, 0
        self.color, self.color2 = SNAKE_COLORS[idx]
        self.speed_mod, self.speed_mult = 0, 1.0
        self.shield, self.ghost_timer, self.magnet_timer = False, 0, 0
        self.tick_accum, self.width = 0.0, INITIAL_WIDTH
        self.name = f"AI-{idx+1}" if is_ai else f"P{idx+1}"
        self._prev_head_px = grid.cell_to_pixel(start_pos)
        pos, rev = start_pos, grid.reverse_dir(direction)
        for i in range(INITIAL_BODY_LEN):
            self.body.append(pos)
            if i < INITIAL_BODY_LEN - 1:
                pos = grid.offset(pos, rev)

    def ai_choose_direction(self, specials, snakes):
        if not self.alive: return
        head, g = self.body[0], self.grid
        targets = [s for s in specials if s.kind in
                   (SpecialType.FOOD, SpecialType.GOLDEN_APPLE, SpecialType.SHIELD,
                    SpecialType.SPEED_BOOST, SpecialType.MAGNET, SpecialType.GHOST)]
        if not targets: targets = specials
        if not targets: return
        best = min(targets, key=lambda s: g.distance(head, s.pos))
        rev = g.reverse_dir(self.direction)
        cands = [d for d in g.directions() if d != rev]
        occ = set()
        for s in snakes:
            if s.alive and s is not self: occ.update(s.body)
        occ.update(list(self.body)[1:])
        def safe(d):
            np = g.offset(head, d)
            if self.wrap_walls: np = g.wrap(np)
            elif not g.in_bounds(np): return False
            return np not in occ or self.ghost_timer > 0
        sf = [d for d in cands if safe(d)]
        if not sf: return
        def sc(d):
            np = g.offset(head, d)
            if self.wrap_walls: np = g.wrap(np)
            return g.distance(np, best.pos)
        self.next_direction = random.choice(sf) if random.random() < 0.06 else min(sf, key=sc)

    def update_direction(self, nd):
        if not self.grid.is_reverse(nd, self.direction):
            self.next_direction = nd

    def move(self):
        if not self.alive: return None
        self._prev_head_px = self.grid.cell_to_pixel(self.body[0])
        self.direction = self.next_direction
        np = self.grid.offset(self.body[0], self.direction)
        if self.wrap_walls:
            np = self.grid.wrap(np)
        elif not self.grid.in_bounds(np):
            if self.shield:
                self.shield = False
                self.direction = self.grid.reverse_dir(self.direction)
                self.next_direction = self.direction
                return self.body[0]
            self.alive = False; return None
        self.body.appendleft(np); self.body.pop()
        return np

    def grow(self, amt=FOOD_GROW):
        for _ in range(amt): self.body.append(self.body[-1])

    def grow_width(self, amt=WIDTH_GROW):
        self.width = min(MAX_WIDTH, self.width + amt)

    def shrink(self, amt=5):
        for _ in range(min(amt, len(self.body)-3)):
            if len(self.body) > 3: self.body.pop()
        self.width = max(INITIAL_WIDTH, self.width - amt*0.3)

    def reverse(self):
        self.body.reverse()
        if len(self.body) >= 2:
            self.direction = self.grid.infer_direction(self.body[1], self.body[0])
            self.next_direction = self.direction

    def draw(self, surf, label_font, interp=0.0):
        if not self.alive: return
        g = self.grid
        bl = list(self.body)
        step = max(1, len(bl)//60)
        sampled = bl[::step]
        if sampled[-1] != bl[-1]: sampled.append(bl[-1])
        pxpts = [g.cell_to_pixel(p) for p in sampled]
        if pxpts:
            ch, cy_ = pxpts[0]; ph, py_ = self._prev_head_px
            pxpts[0] = (ph+(ch-ph)*interp, py_+(cy_-py_)*interp)
        if len(pxpts) < 2: return
        spine = catmull_rom_chain(pxpts, steps=4)
        if len(spine) < 2: return
        w = self.width * (0.8 if self.ghost_timer > 0 else 1.0)
        contour = build_contour(spine, w)
        if len(contour) < 3: return

        body_col = self.color
        if self.ghost_timer > 0:
            body_col = tuple(min(255, c+60) for c in body_col)
        ic = [(int(x), int(y)) for x, y in contour]
        pygame.draw.polygon(surf, body_col, ic)
        # Stripe
        stripe_col = self.color2
        if self.ghost_timer > 0:
            stripe_col = tuple(min(255, c+60) for c in stripe_col)
        if w > 6:
            sp = [(int(p[0]),int(p[1])) for p in spine[::2]]
            if len(sp) >= 2:
                pygame.draw.lines(surf, stripe_col, False, sp, max(1, int(w*0.2)))
        # Outline
        pygame.draw.polygon(surf, tuple(max(0,c-40) for c in body_col), ic, 2)
        # Shield glow
        if self.shield:
            pygame.draw.circle(surf, (200,200,255), (int(spine[0][0]),int(spine[0][1])), int(w*0.8), 2)
        # Head
        hx, hy = spine[0]
        pygame.draw.circle(surf, body_col, (int(hx),int(hy)), int(w*0.5))
        pygame.draw.circle(surf, tuple(max(0,c-40) for c in body_col), (int(hx),int(hy)), int(w*0.5), 2)
        # Eyes
        dx, dy = g.direction_to_pixel_offset(self.direction)
        mg = math.hypot(dx, dy)
        if mg > 0: dx, dy = dx/mg, dy/mg
        esep = max(2, w*0.22); er = max(2, int(w*0.14)); pr = max(1, er//2)
        nx_, ny_ = -dy, dx
        for side in (-1, 1):
            ex = hx + nx_*esep*side + dx*w*0.2
            ey = hy + ny_*esep*side + dy*w*0.2
            pygame.draw.circle(surf, WHITE, (int(ex),int(ey)), er)
            pygame.draw.circle(surf, (20,20,20), (int(ex+dx*1.5),int(ey+dy*1.5)), pr)

        # ---- PLAYER LABEL above head (key feature for identification) ----
        lbl = label_font.render(self.name, True, self.color)
        lbl_x = int(hx) - lbl.get_width()//2
        lbl_y = int(hy) - int(w*0.5) - 14
        # Background pill for readability
        pill = pygame.Rect(lbl_x-3, lbl_y-1, lbl.get_width()+6, lbl.get_height()+2)
        pill_surf = pygame.Surface((pill.w, pill.h), pygame.SRCALPHA)
        pill_surf.fill((0, 0, 0, 140))
        surf.blit(pill_surf, pill.topleft)
        surf.blit(lbl, (lbl_x, lbl_y))

        # Pulsing ring for human players (not AI) to make them extra visible
        if not self.is_ai:
            pulse = 0.5 + 0.5*math.sin(pygame.time.get_ticks()*0.005)
            ring_r = int(w*0.6 + pulse*4)
            ring_col = tuple(min(255, c+80) for c in self.color)
            pygame.draw.circle(surf, ring_col, (int(hx),int(hy)), ring_r, 2)

        # Tail tip
        tx, ty = spine[-1]
        pygame.draw.circle(surf, body_col, (int(tx),int(ty)), max(1,int(w*0.12)))


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------
class Game:
    def __init__(self, num_humans, num_snakes, wrap_walls, cols, rows,
                 grid_mode, sq_keys, hex_keys):
        self.num_humans, self.num_snakes, self.wrap_walls = num_humans, num_snakes, wrap_walls
        self.grid = HexGrid(cols, rows) if grid_mode == GridMode.HEX else SquareGrid(cols, rows)
        self.sq_key_maps = build_key_maps(sq_keys)
        self.hex_key_maps = build_key_maps(hex_keys)
        self.snakes: list[Snake] = []
        self.specials: list[Special] = []
        self.particles: list[Particle] = []
        self.tick, self.game_over, self.winner = 0, False, None

        starts = self._gen_starts(num_snakes)
        for i in range(num_snakes):
            pos, d = starts[i]
            self.snakes.append(Snake(i, pos, d, i >= num_humans, wrap_walls, self.grid))
        for _ in range(3 + num_snakes):
            self._spawn_special(SpecialType.FOOD)

    def _gen_starts(self, count):
        g, margin = self.grid, max(INITIAL_BODY_LEN+4, 20)
        cx, cy = g.cols//2, g.rows//2
        starts = []
        for i in range(count):
            a = 2*math.pi*i/count
            sx = max(margin, min(g.cols-margin, int(cx+(cx-margin)*math.cos(a))))
            sy = max(margin, min(g.rows-margin, int(cy+(cy-margin)*math.sin(a))))
            starts.append(((sx,sy), g.pick_start_direction(sx,sy,cx,cy)))
        return starts

    def _free_cell(self):
        g = self.grid
        occ = set()
        for s in self.snakes: occ.update(s.body)
        for sp in self.specials: occ.add(sp.pos)
        for _ in range(500):
            p = (random.randint(0, g.cols-1), random.randint(0, g.rows-1))
            if p not in occ: return p
        return (random.randint(0, g.cols-1), random.randint(0, g.rows-1))

    def _spawn_special(self, kind=None):
        if kind is None:
            r = random.random()
            kind = (SpecialType.FOOD if r<.35 else SpecialType.SPEED_BOOST if r<.48 else
                    SpecialType.SLOW_ZONE if r<.58 else SpecialType.SHIELD if r<.67 else
                    SpecialType.REVERSE if r<.75 else SpecialType.MAGNET if r<.82 else
                    SpecialType.BOMB if r<.89 else SpecialType.GHOST if r<.95 else
                    SpecialType.GOLDEN_APPLE)
        self.specials.append(Special(kind, self._free_cell()))

    def _emit(self, pos, color, count=8):
        px, py = self.grid.cell_to_pixel(pos)
        for _ in range(count): self.particles.append(Particle(px, py, color))

    def handle_input(self, keys):
        is_hex = self.grid.mode == GridMode.HEX
        kms = self.hex_key_maps if is_hex else self.sq_key_maps
        for i, s in enumerate(self.snakes):
            if s.is_ai or not s.alive or i >= len(kms): continue
            for key, d in kms[i].items():
                if keys[key]: s.update_direction(d)

    def update(self):
        if self.game_over: return
        self.tick += 1; g = self.grid

        for s in self.snakes:
            if s.is_ai and s.alive: s.ai_choose_direction(self.specials, self.snakes)

        for s in self.snakes:
            if not s.alive: continue
            if s.speed_mod > 0:
                s.speed_mod -= 1
                if s.speed_mod == 0: s.speed_mult = 1.0
            if s.ghost_timer > 0: s.ghost_timer -= 1
            if s.magnet_timer > 0: s.magnet_timer -= 1
            s.tick_accum += s.speed_mult
            if s.tick_accum >= 1.0: s.tick_accum -= 1.0; s.move()
            if s.tick_accum >= 1.0: s.tick_accum -= 1.0; s.move()

        # Magnet
        for s in self.snakes:
            if s.alive and s.magnet_timer > 0:
                head = s.body[0]
                for sp in self.specials:
                    if sp.kind in (SpecialType.FOOD, SpecialType.GOLDEN_APPLE):
                        dist = g.distance(head, sp.pos)
                        if 1 < dist < 12:
                            best_nb, best_d = sp.pos, dist
                            for d in g.directions():
                                nb = g.offset(sp.pos, d)
                                if g.in_bounds(nb):
                                    nd = g.distance(head, nb)
                                    if nd < best_d: best_d, best_nb = nd, nb
                            sp.pos = best_nb

        # Proximity pickups
        for s in self.snakes:
            if not s.alive: continue
            hx, hy = g.cell_to_pixel(s.body[0])
            for sp in self.specials[:]:
                sx, sy = g.cell_to_pixel(sp.pos)
                if math.hypot(hx-sx, hy-sy) < PICKUP_RADIUS + s.width*0.3:
                    self._apply(s, sp); self.specials.remove(sp)

        # Collisions
        for s in self.snakes:
            if not s.alive: continue
            head = s.body[0]
            if head in list(s.body)[3:] and s.ghost_timer <= 0:
                if s.shield: s.shield = False; s.shrink(8)
                else: s.alive = False; self._emit(head, s.color, 20); continue
            for o in self.snakes:
                if o is s or not o.alive: continue
                hpx, hpy = g.cell_to_pixel(head)
                ob = list(o.body); chk = max(1, len(ob)//40)
                hit = False
                for seg in ob[::chk]:
                    spx, spy = g.cell_to_pixel(seg)
                    if math.hypot(hpx-spx, hpy-spy) < (s.width+o.width)*0.35:
                        hit = True; break
                if hit:
                    if s.ghost_timer > 0: continue
                    if s.shield: s.shield = False; o.shrink(8)
                    else: s.alive = False; self._emit(head, s.color, 20); break

        si = max(10, 30 - self.num_snakes*2)
        if self.tick % si == 0: self._spawn_special()
        if sum(1 for sp in self.specials if sp.kind == SpecialType.FOOD) < 3+self.num_snakes:
            self._spawn_special(SpecialType.FOOD)
        for sp in self.specials[:]:
            if sp.kind != SpecialType.FOOD:
                sp.timer -= 1
                if sp.timer <= 0: self.specials.remove(sp)
        for p in self.particles[:]:
            p.update()
            if p.life <= 0: self.particles.remove(p)

        alive = [s for s in self.snakes if s.alive]
        if len(alive) <= 1:
            self.game_over = True
            self.winner = alive[0] if alive else None

    def _apply(self, snake, sp):
        _, color, _, dur = SPECIAL_INFO[sp.kind]
        self._emit(sp.pos, color, 12)
        k = sp.kind
        if k == SpecialType.FOOD: snake.grow(FOOD_GROW); snake.grow_width(WIDTH_GROW); snake.score += 1
        elif k == SpecialType.GOLDEN_APPLE: snake.grow(FOOD_GROW*3); snake.grow_width(WIDTH_GROW*3); snake.score += 5
        elif k == SpecialType.SPEED_BOOST: snake.speed_mod = dur; snake.speed_mult = 1.8
        elif k == SpecialType.SLOW_ZONE: snake.speed_mod = dur; snake.speed_mult = 0.5
        elif k == SpecialType.SHIELD: snake.shield = True
        elif k == SpecialType.REVERSE: snake.reverse()
        elif k == SpecialType.MAGNET: snake.magnet_timer = dur
        elif k == SpecialType.BOMB:
            self._emit(sp.pos, (255,100,30), 30)
            for o in self.snakes:
                if not o.alive or o is snake: continue
                for seg in list(o.body):
                    if self.grid.distance(seg, sp.pos) < 8:
                        o.shrink(10); o.score = max(0, o.score-2); break
            snake.score += 2
        elif k == SpecialType.GHOST: snake.ghost_timer = dur

    def draw(self, surf, font, small_font, label_font, interp=0.0):
        g = self.grid; ww = surf.get_width()
        gw, gh = g.grid_pixel_size()
        surf.fill(BG)
        # No visible grid — clean look
        # Subtle wall border
        if not self.wrap_walls:
            pygame.draw.rect(surf, (100,30,30), (0,PANEL_H,gw,gh), 2)
        else:
            for x in range(0,gw,30):
                pygame.draw.line(surf,(30,60,90),(x,PANEL_H),(x+15,PANEL_H),1)
                pygame.draw.line(surf,(30,60,90),(x,PANEL_H+gh-1),(x+15,PANEL_H+gh-1),1)
            for y in range(PANEL_H,PANEL_H+gh,30):
                pygame.draw.line(surf,(30,60,90),(0,y),(0,y+15),1)
                pygame.draw.line(surf,(30,60,90),(gw-1,y),(gw-1,y+15),1)

        for sp in self.specials: sp.draw(surf, small_font, g)
        for s in self.snakes:
            if s.alive: s.draw(surf, label_font, interp)
        for p in self.particles: p.draw(surf)

        # Scoreboard
        pygame.draw.rect(surf, (20,20,35), (0,0,ww,PANEL_H))
        pygame.draw.line(surf, (60,60,80), (0,PANEL_H-1), (ww,PANEL_H-1))
        n = len(self.snakes)
        if n <= 5:
            pw = ww // max(n,1)
            for i, s in enumerate(self.snakes):
                self._panel(surf, s, i*pw+8, 4, pw, font, small_font)
        else:
            tn = (n+1)//2; bn = n-tn
            for i in range(tn):
                self._panel(surf, self.snakes[i], i*(ww//tn)+8, 2, ww//tn, font, small_font)
            for i in range(bn):
                self._panel(surf, self.snakes[tn+i], i*(ww//max(bn,1))+8, 36, ww//max(bn,1), font, small_font)

        if self.game_over:
            ov = pygame.Surface((gw,gh), pygame.SRCALPHA); ov.fill((0,0,0,150))
            surf.blit(ov, (0, PANEL_H))
            msg = f"{self.winner.name} WINS!" if self.winner else "DRAW!"
            col = self.winner.color if self.winner else WHITE
            txt = font.render(msg, True, col)
            surf.blit(txt, txt.get_rect(center=(gw//2, PANEL_H+gh//2-20)))
            r = small_font.render("SPACE = menu  |  ESC = quit", True, GRAY)
            surf.blit(r, r.get_rect(center=(gw//2, PANEL_H+gh//2+20)))

    def _panel(self, surf, s, x, y, w, font, sf):
        col = s.color if s.alive else DARK_GRAY
        tag = "AI" if s.is_ai else "YOU"
        pygame.draw.rect(surf, col, (x, y+2, 10, 10), border_radius=2)
        surf.blit(sf.render(f"{s.name} [{tag}]", True, col), (x+14, y))
        surf.blit(font.render(f"{s.score}  W:{s.width:.0f}", True, col), (x+14, y+14))
        ix = x + 130; iy = y + 20
        if s.shield: pygame.draw.circle(surf,(180,180,255),(ix,iy),5,2); ix+=14
        if s.ghost_timer>0: pygame.draw.circle(surf,(180,255,220),(ix,iy),5); ix+=14
        if s.magnet_timer>0: pygame.draw.circle(surf,(255,160,60),(ix,iy),5); ix+=14
        if s.speed_mod>0: pygame.draw.circle(surf,YELLOW if s.speed_mult>1 else (100,100,255),(ix,iy),5)
        if not s.alive: surf.blit(sf.render("DEAD",True,RED),(x+w-50,y+14))


# ---------------------------------------------------------------------------
# Key Bind Editor (in-menu)
# ---------------------------------------------------------------------------
class KeyBindEditor:
    """Simple overlay to remap keys for one player slot."""
    def __init__(self, player_idx, is_hex, raw_binds, font, small_font):
        self.player_idx = player_idx
        self.is_hex = is_hex
        self.raw_binds = raw_binds  # the list of dicts
        self.font, self.small_font = font, small_font
        self.dirs = list(raw_binds[player_idx].keys())
        self.current_dir_idx = 0
        self.waiting_key = False
        self.done = False

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if self.waiting_key:
            key_name = pygame.key.name(event.key)
            pg_name = f"K_{key_name}" if not key_name.startswith("[") else None
            # Try to find the pygame constant name
            for attr in dir(pygame):
                if attr.startswith("K_") and getattr(pygame, attr) == event.key:
                    pg_name = attr
                    break
            if pg_name:
                d = self.dirs[self.current_dir_idx]
                self.raw_binds[self.player_idx][d] = pg_name
            self.waiting_key = False
            self.current_dir_idx += 1
            if self.current_dir_idx >= len(self.dirs):
                self.done = True
            return
        if event.key == pygame.K_ESCAPE:
            self.done = True
            return
        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.waiting_key = True

    def draw(self, surf):
        w, h = surf.get_width(), surf.get_height()
        ov = pygame.Surface((w, h), pygame.SRCALPHA); ov.fill((0,0,0,200))
        surf.blit(ov, (0,0))
        cx, cy = w//2, h//2 - 80
        t = self.font.render(f"Rebind keys for P{self.player_idx+1}", True, HIGHLIGHT)
        surf.blit(t, t.get_rect(center=(cx, cy))); cy += 40

        for i, d in enumerate(self.dirs):
            cur_key = self.raw_binds[self.player_idx][d]
            col = YELLOW if i == self.current_dir_idx else WHITE
            if i == self.current_dir_idx and self.waiting_key:
                txt = f"{d}: [Press a key...]"
            elif i < self.current_dir_idx:
                txt = f"{d}: {cur_key}  ✓"
            else:
                txt = f"{d}: {cur_key}"
            r = self.small_font.render(txt, True, col)
            surf.blit(r, r.get_rect(center=(cx, cy))); cy += 24

        if not self.waiting_key and not self.done:
            h = self.small_font.render("ENTER = rebind next  |  ESC = cancel", True, GRAY)
            surf.blit(h, h.get_rect(center=(cx, cy+20)))


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
class Menu:
    def __init__(self, screen, font, small_font, title_font, sq_raw, hex_raw):
        self.screen, self.font, self.small_font, self.title_font = screen, font, small_font, title_font
        self.num_players, self.num_snakes = 1, 4
        self.wrap_walls, self.fullscreen = True, False
        self.grid_mode = GridMode.HEX
        self.sq_raw, self.hex_raw = sq_raw, hex_raw
        self.selected, self.options = 0, 7  # +1 for keybinds row
        self.key_editor = None

    def _max_humans(self):
        r = self.hex_raw if self.grid_mode == GridMode.HEX else self.sq_raw
        return len(r)

    def handle_event(self, event):
        if self.key_editor:
            self.key_editor.handle_event(event)
            if self.key_editor.done:
                self.key_editor = None
                save_keybinds(self.sq_raw, self.hex_raw)
            return None

        if event.type != pygame.KEYDOWN: return None
        k = event.key
        if k in (pygame.K_UP,): self.selected = (self.selected-1) % self.options
        elif k in (pygame.K_DOWN,): self.selected = (self.selected+1) % self.options
        elif k in (pygame.K_LEFT,): self._adj(-1)
        elif k in (pygame.K_RIGHT,): self._adj(1)
        elif k in (pygame.K_RETURN, pygame.K_SPACE):
            if self.selected == self.options - 1: return "start"
            elif self.selected == 5:  # keybinds
                raw = self.hex_raw if self.grid_mode == GridMode.HEX else self.sq_raw
                # Cycle through or start editor for P1 (user can re-enter for other players)
                pidx = min(self.num_players-1, 0)
                self.key_editor = KeyBindEditor(pidx, self.grid_mode==GridMode.HEX,
                                                raw, self.font, self.small_font)
            else:
                self._adj(1)
        elif k == pygame.K_TAB and self.selected == 5:
            # Tab to cycle player index for rebinding
            pass
        return None

    def _adj(self, d):
        s = self.selected
        if s == 0:
            self.num_players = max(1, min(self._max_humans(), min(self.num_snakes, self.num_players+d)))
        elif s == 1:
            self.num_snakes = max(1, min(MAX_SNAKES, self.num_snakes+d))
            self.num_players = min(self.num_players, self.num_snakes)
        elif s == 2: self.wrap_walls = not self.wrap_walls
        elif s == 3:
            self.grid_mode = GridMode.HEX if self.grid_mode == GridMode.SQUARE else GridMode.SQUARE
            self.num_players = min(self.num_players, self._max_humans())
        elif s == 4: self.fullscreen = not self.fullscreen
        elif s == 5:
            # Left/right to pick which player to rebind
            raw = self.hex_raw if self.grid_mode == GridMode.HEX else self.sq_raw
            pidx = max(0, min(len(raw)-1, d))  # crude: right opens P1
            self.key_editor = KeyBindEditor(pidx, self.grid_mode==GridMode.HEX,
                                            raw, self.font, self.small_font)

    def draw(self):
        if self.key_editor:
            self.key_editor.draw(self.screen)
            return
        w, h = self.screen.get_width(), self.screen.get_height()
        self.screen.fill(MENU_BG)
        is_hex = self.grid_mode == GridMode.HEX
        ai = self.num_snakes - self.num_players

        self.screen.blit(self.title_font.render("SNAKE ARENA", True, HIGHLIGHT),
                         self.title_font.render("SNAKE ARENA", True, HIGHLIGHT).get_rect(center=(w//2, 60)))
        self.screen.blit(self.small_font.render(
            "Smooth Edition  |  Spline snakes  |  Width growth  |  60 FPS", True, GRAY),
            self.small_font.render("x",True,GRAY).get_rect(center=(w//2, 98)))
        sub = self.small_font.render("Smooth Edition  |  Spline snakes  |  Width growth  |  60 FPS", True, GRAY)
        self.screen.blit(sub, sub.get_rect(center=(w//2, 98)))

        cy, gap = 140, 36
        items = [
            f"<  Human Players: {self.num_players}  >",
            f"<  Total Snakes: {self.num_snakes}  ({ai} AI)  >",
            f"<  Walls: {'Wrap' if self.wrap_walls else 'Solid'}  >",
            f"<  Grid: {'Hexagonal' if is_hex else 'Square'}  >",
            f"<  Display: {'Fullscreen' if self.fullscreen else 'Windowed'}  >",
            "[ Customize Keys ]",
            "[ START GAME ]",
        ]
        for i, label in enumerate(items):
            col = HIGHLIGHT if self.selected == i else WHITE
            if i == len(items)-1: cy += 10
            t = self.font.render(label, True, col)
            self.screen.blit(t, t.get_rect(center=(w//2, cy)))
            cy += gap

        # Controls
        cy = h - 170
        raw = self.hex_raw if is_hex else self.sq_raw
        hdr = self.small_font.render("— Current Key Bindings —", True, GRAY)
        self.screen.blit(hdr, hdr.get_rect(center=(w//2, cy-18)))
        for i, pmap in enumerate(raw):
            cidx = min(i, len(SNAKE_COLORS)-1)
            keys_str = "  ".join(f"{d}={v.replace('K_','')}" for d, v in pmap.items())
            tag = f"P{i+1}: {keys_str}"
            t = self.small_font.render(tag, True, SNAKE_COLORS[cidx][0])
            self.screen.blit(t, t.get_rect(center=(w//2, cy+4+i*18)))

        # Legend
        ly = cy + 4 + len(raw)*18 + 14
        lh = self.small_font.render("— Power-ups —", True, GRAY)
        self.screen.blit(lh, lh.get_rect(center=(w//2, ly)))
        legend = [("● Food", (255,50,50)), ("★ Golden", (255,215,0)),
                  ("⚡ Speed", (255,255,80)), ("❄ Slow", (100,100,255)),
                  ("🛡 Shield", (200,200,255)), ("⟳ Reverse", (255,100,255)),
                  ("⊕ Magnet", (255,160,60)), ("💣 Bomb", (255,80,30)),
                  ("👻 Ghost", (180,255,220))]
        cw = w // 3
        for i, (lb, co) in enumerate(legend):
            r, c = i//3, i%3
            t = self.small_font.render(lb, True, co)
            self.screen.blit(t, t.get_rect(center=(c*cw+cw//2, ly+16+r*16)))

        self.screen.blit(self.small_font.render("F11 fullscreen | ESC quit", True, DARK_GRAY),
                         self.small_font.render("x",True,GRAY).get_rect(center=(w//2, h-10)))
        ft = self.small_font.render("F11 fullscreen | ESC quit", True, DARK_GRAY)
        self.screen.blit(ft, ft.get_rect(center=(w//2, h-10)))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    pygame.init()
    desk = pygame.display.Info()
    desk_w, desk_h = desk.current_w, desk.current_h
    dw, dh = 900, 720

    screen = pygame.display.set_mode((dw, dh), pygame.RESIZABLE)
    pygame.display.set_caption("Snake Arena — Smooth Edition")
    clock = pygame.time.Clock()
    is_fs = False

    tf = pygame.font.SysFont("Arial", 44, bold=True)
    f = pygame.font.SysFont("Arial", 20, bold=True)
    sf = pygame.font.SysFont("Arial", 14)
    lf = pygame.font.SysFont("Arial", 11, bold=True)  # label font for snake names

    sq_raw, hex_raw = load_keybinds()
    menu = Menu(screen, f, sf, tf, sq_raw, hex_raw)
    game: Game | None = None
    state = "menu"
    tick_acc = 0.0

    def toggle_fs():
        """Safe: just resize RESIZABLE to desktop dims — no FULLSCREEN/NOFRAME flags."""
        nonlocal screen, is_fs
        if is_fs:
            screen = pygame.display.set_mode((dw, dh), pygame.RESIZABLE)
            is_fs = False
        else:
            screen = pygame.display.set_mode((desk_w, desk_h - 50), pygame.RESIZABLE)
            is_fs = True
        pygame.display.set_caption("Snake Arena — Smooth Edition")
        menu.screen, menu.fullscreen = screen, is_fs

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11: toggle_fs()
                elif event.key == pygame.K_ESCAPE:
                    if state == "playing":
                        state, game, tick_acc = "menu", None, 0.0
                        if is_fs: toggle_fs()
                    else: running = False
            if event.type == pygame.VIDEORESIZE and not is_fs:
                screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                menu.screen = screen
            if state == "menu":
                r = menu.handle_event(event)
                if r == "start":
                    if menu.fullscreen != is_fs: toggle_fs()
                    ww, wh = screen.get_width(), screen.get_height()
                    gm = menu.grid_mode
                    cols, rows = (HexGrid if gm==GridMode.HEX else SquareGrid).grid_from_window(ww, wh)
                    game = Game(menu.num_players, menu.num_snakes, menu.wrap_walls,
                                cols, rows, gm, sq_raw, hex_raw)
                    state, tick_acc = "playing", 0.0
            elif state == "playing" and game and game.game_over:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    state, game = "menu", None

        if state == "menu":
            menu.draw()
        elif state == "playing" and game:
            game.handle_input(pygame.key.get_pressed())
            tick_acc += dt
            while tick_acc >= TICK_INTERVAL:
                tick_acc -= TICK_INTERVAL; game.update()
            game.draw(screen, f, sf, lf, tick_acc / TICK_INTERVAL)

        pygame.display.flip()

    pygame.quit(); sys.exit()


if __name__ == "__main__":
    main()
