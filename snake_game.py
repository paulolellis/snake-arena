"""
Multiplayer Snake Arena with AI opponents and special items.
Supports 1-4 human players, 1-10 total snakes, resizable/fullscreen grid.
Square or Hexagonal grid modes.
"""

import pygame
import random
import math
import sys
from enum import Enum, auto
from collections import deque

# ---------------------------------------------------------------------------
# Constants & defaults
# ---------------------------------------------------------------------------
CELL = 20
MIN_COLS, MIN_ROWS = 30, 20
PANEL_H = 70
FPS = 12

# Square directions
UP = (0, -1)
DOWN = (0, 1)
LEFT = (-1, 0)
RIGHT = (1, 0)
DIRS = [UP, DOWN, LEFT, RIGHT]

# Colors
BG = (15, 15, 25)
GRID_COL = (25, 25, 40)
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

# Square key mappings (4 keys per player)
PLAYER_KEYS = [
    {pygame.K_w: UP, pygame.K_s: DOWN, pygame.K_a: LEFT, pygame.K_d: RIGHT},
    {pygame.K_UP: UP, pygame.K_DOWN: DOWN, pygame.K_LEFT: LEFT, pygame.K_RIGHT: RIGHT},
    {pygame.K_i: UP, pygame.K_k: DOWN, pygame.K_j: LEFT, pygame.K_l: RIGHT},
    {pygame.K_KP8: UP, pygame.K_KP5: DOWN, pygame.K_KP4: LEFT, pygame.K_KP6: RIGHT},
]

# Hex key mappings (6 keys per player)
HEX_PLAYER_KEYS = [
    # P1: Q=NW, W=NE, A=W, D=E, Z=SW, X=SE
    {pygame.K_q: "NW", pygame.K_w: "NE", pygame.K_a: "W",
     pygame.K_d: "E", pygame.K_z: "SW", pygame.K_x: "SE"},
    # P2: U=NW, I=NE, J=W, L=E, N=SW, M=SE
    {pygame.K_u: "NW", pygame.K_i: "NE", pygame.K_j: "W",
     pygame.K_l: "E", pygame.K_n: "SW", pygame.K_m: "SE"},
    # P3: Numpad 7=NW, 9=NE, 4=W, 6=E, 1=SW, 3=SE
    {pygame.K_KP7: "NW", pygame.K_KP9: "NE", pygame.K_KP4: "W",
     pygame.K_KP6: "E", pygame.K_KP1: "SW", pygame.K_KP3: "SE"},
]

MAX_HUMANS = len(PLAYER_KEYS)  # 4
MAX_HUMANS_HEX = len(HEX_PLAYER_KEYS)  # 3
MAX_SNAKES = len(SNAKE_COLORS)  # 10

# Hex direction data (even-r offset, pointy-top)
HEX_DIR_NAMES = ["E", "W", "NE", "NW", "SE", "SW"]
HEX_OFFSETS = {
    0: {"E": (1, 0), "W": (-1, 0), "NE": (0, -1), "NW": (-1, -1),
        "SE": (0, 1), "SW": (-1, 1)},
    1: {"E": (1, 0), "W": (-1, 0), "NE": (1, -1), "NW": (0, -1),
        "SE": (1, 1), "SW": (0, 1)},
}
HEX_REVERSE = {"E": "W", "W": "E", "NE": "SW", "SW": "NE", "NW": "SE", "SE": "NW"}


# ---------------------------------------------------------------------------
# Grid Mode
# ---------------------------------------------------------------------------
class GridMode(Enum):
    SQUARE = auto()
    HEX = auto()


# ---------------------------------------------------------------------------
# SquareGrid
# ---------------------------------------------------------------------------
class SquareGrid:
    mode = GridMode.SQUARE

    def __init__(self, cols, rows):
        self.cols = cols
        self.rows = rows

    def directions(self):
        return list(DIRS)

    def offset(self, pos, direction):
        return (pos[0] + direction[0], pos[1] + direction[1])

    def reverse_dir(self, d):
        return (-d[0], -d[1])

    def is_reverse(self, d1, d2):
        return d1 == self.reverse_dir(d2)

    def wrap(self, pos):
        return (pos[0] % self.cols, pos[1] % self.rows)

    def in_bounds(self, pos):
        return 0 <= pos[0] < self.cols and 0 <= pos[1] < self.rows

    def distance(self, a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def cell_to_pixel(self, pos):
        return (pos[0] * CELL + CELL // 2, pos[1] * CELL + CELL // 2 + PANEL_H)

    def cell_size(self):
        return CELL

    def draw_grid(self, surf):
        gw, gh = self.grid_pixel_size()
        for x in range(0, gw + 1, CELL):
            pygame.draw.line(surf, GRID_COL, (x, PANEL_H), (x, PANEL_H + gh))
        for y in range(PANEL_H, PANEL_H + gh + 1, CELL):
            pygame.draw.line(surf, GRID_COL, (0, y), (gw, y))

    def draw_cell(self, surf, pos, color, shrink=2):
        rect = pygame.Rect(pos[0] * CELL, pos[1] * CELL + PANEL_H, CELL, CELL)
        pygame.draw.rect(surf, color, rect.inflate(-shrink, -shrink), border_radius=4)

    def draw_cell_outline(self, surf, pos, color, width=2):
        rect = pygame.Rect(pos[0] * CELL, pos[1] * CELL + PANEL_H, CELL, CELL)
        pygame.draw.rect(surf, color, rect.inflate(4, 4), width, border_radius=4)

    def grid_pixel_size(self):
        return (self.cols * CELL, self.rows * CELL)

    def infer_direction(self, from_pos, to_pos):
        d = (to_pos[0] - from_pos[0], to_pos[1] - from_pos[1])
        if d in DIRS:
            return d
        # Wrapped — check all directions
        for direction in DIRS:
            if self.wrap(self.offset(from_pos, direction)) == to_pos:
                return direction
        return RIGHT

    def pick_start_direction(self, sx, sy, cx, cy):
        dx = 1 if cx > sx else -1 if cx < sx else 0
        dy = 1 if cy > sy else -1 if cy < sy else 0
        if abs(cx - sx) >= abs(cy - sy):
            d = (dx, 0)
        else:
            d = (0, dy)
        return d if d != (0, 0) else RIGHT

    def direction_to_pixel_offset(self, d):
        return (d[0], d[1])

    @staticmethod
    def grid_from_window(win_w, win_h):
        cols = max(MIN_COLS, win_w // CELL)
        rows = max(MIN_ROWS, (win_h - PANEL_H) // CELL)
        return cols, rows


# ---------------------------------------------------------------------------
# HexGrid (even-r offset, pointy-top)
# ---------------------------------------------------------------------------
class HexGrid:
    mode = GridMode.HEX

    def __init__(self, cols, rows):
        self.cols = cols
        self.rows = rows
        self.hex_size = CELL * 0.58
        self.hex_w = math.sqrt(3) * self.hex_size
        self.hex_h = 2 * self.hex_size

    def directions(self):
        return list(HEX_DIR_NAMES)

    def offset(self, pos, direction):
        parity = pos[1] & 1
        dc, dr = HEX_OFFSETS[parity][direction]
        return (pos[0] + dc, pos[1] + dr)

    def reverse_dir(self, d):
        return HEX_REVERSE[d]

    def is_reverse(self, d1, d2):
        return d1 == HEX_REVERSE.get(d2)

    def wrap(self, pos):
        return (pos[0] % self.cols, pos[1] % self.rows)

    def in_bounds(self, pos):
        return 0 <= pos[0] < self.cols and 0 <= pos[1] < self.rows

    def _to_cube(self, col, row):
        q = col - (row + (row & 1)) // 2
        r = row
        s = -q - r
        return (q, r, s)

    def distance(self, a, b):
        aq, ar, as_ = self._to_cube(a[0], a[1])
        bq, br, bs = self._to_cube(b[0], b[1])
        return max(abs(aq - bq), abs(ar - br), abs(as_ - bs))

    def cell_to_pixel(self, pos):
        col, row = pos
        px = col * self.hex_w + (row & 1) * self.hex_w * 0.5 + self.hex_w * 0.5
        py = row * self.hex_h * 0.75 + self.hex_size + PANEL_H
        return (px, py)

    def cell_size(self):
        return self.hex_size * 2

    def _hex_vertices(self, cx, cy, size):
        verts = []
        for i in range(6):
            angle = math.radians(60 * i - 30)  # pointy-top
            verts.append((cx + size * math.cos(angle), cy + size * math.sin(angle)))
        return verts

    def draw_grid(self, surf):
        for row in range(self.rows):
            for col in range(self.cols):
                cx, cy = self.cell_to_pixel((col, row))
                verts = self._hex_vertices(cx, cy, self.hex_size)
                pygame.draw.polygon(surf, GRID_COL, verts, 1)

    def draw_cell(self, surf, pos, color, shrink=2):
        cx, cy = self.cell_to_pixel(pos)
        s = self.hex_size - shrink * 0.5
        verts = self._hex_vertices(cx, cy, s)
        pygame.draw.polygon(surf, color, verts)

    def draw_cell_outline(self, surf, pos, color, width=2):
        cx, cy = self.cell_to_pixel(pos)
        verts = self._hex_vertices(cx, cy, self.hex_size + 2)
        pygame.draw.polygon(surf, color, verts, width)

    def grid_pixel_size(self):
        gw = int(self.cols * self.hex_w + self.hex_w * 0.5 + 2)
        gh = int(self.rows * self.hex_h * 0.75 + self.hex_size + 2)
        return (gw, gh)

    def infer_direction(self, from_pos, to_pos):
        for d in HEX_DIR_NAMES:
            if self.offset(from_pos, d) == to_pos:
                return d
        # Wrap-aware
        for d in HEX_DIR_NAMES:
            if self.wrap(self.offset(from_pos, d)) == to_pos:
                return d
        return "E"

    def pick_start_direction(self, sx, sy, cx, cy):
        best_dir = "E"
        best_dist = float('inf')
        for d in HEX_DIR_NAMES:
            nx, ny = self.offset((sx, sy), d)
            dist = abs(nx - cx) + abs(ny - cy)
            if dist < best_dist:
                best_dist = dist
                best_dir = d
        return best_dir

    def direction_to_pixel_offset(self, d):
        """Approximate pixel direction for drawing eyes."""
        mapping = {
            "E": (1, 0), "W": (-1, 0),
            "NE": (1, -1), "NW": (-1, -1),
            "SE": (1, 1), "SW": (-1, 1),
        }
        return mapping.get(d, (1, 0))

    @staticmethod
    def grid_from_window(win_w, win_h):
        hex_size = CELL * 0.58
        hex_w = math.sqrt(3) * hex_size
        hex_h = 2 * hex_size
        cols = max(MIN_COLS, int(win_w / hex_w) - 1)
        rows = max(MIN_ROWS, int((win_h - PANEL_H) / (hex_h * 0.75)) - 1)
        return cols, rows


# ---------------------------------------------------------------------------
# Specials
# ---------------------------------------------------------------------------
class SpecialType(Enum):
    FOOD = auto()
    SPEED_BOOST = auto()
    SLOW_ZONE = auto()
    SHIELD = auto()
    REVERSE = auto()
    MAGNET = auto()
    BOMB = auto()
    GHOST = auto()
    GOLDEN_APPLE = auto()


SPECIAL_INFO = {
    SpecialType.FOOD:         ("Food",         (255, 50, 50),   "●", None),
    SpecialType.SPEED_BOOST:  ("Speed Boost",  (255, 255, 80),  "⚡", 80),
    SpecialType.SLOW_ZONE:    ("Slow",         (100, 100, 255), "❄", 80),
    SpecialType.SHIELD:       ("Shield",       (200, 200, 255), "🛡", None),
    SpecialType.REVERSE:      ("Reverse",      (255, 100, 255), "⟳", None),
    SpecialType.MAGNET:       ("Magnet",       (255, 160, 60),  "⊕", 100),
    SpecialType.BOMB:         ("Bomb",         (255, 80, 30),   "💣", None),
    SpecialType.GHOST:        ("Ghost",        (180, 255, 220), "👻", 80),
    SpecialType.GOLDEN_APPLE: ("Golden Apple", (255, 215, 0),   "★", None),
}


class Special:
    def __init__(self, kind: SpecialType, pos: tuple[int, int]):
        self.kind = kind
        self.pos = pos
        self.timer = 300
        self.pulse = 0

    def draw(self, surf: pygame.Surface, font: pygame.font.Font, grid):
        _, color, symbol, _ = SPECIAL_INFO[self.kind]
        self.pulse = (self.pulse + 0.12) % (2 * math.pi)
        scale = 1.0 + 0.15 * math.sin(self.pulse)
        px, py = grid.cell_to_pixel(self.pos)
        x, y = int(px), int(py)
        sz = grid.cell_size() * 0.5

        if self.kind == SpecialType.FOOD:
            r = int(sz * 0.7 * scale)
            pygame.draw.circle(surf, color, (x, y), r)
            pygame.draw.circle(surf, (255, 120, 120), (x, y), r, 1)
        elif self.kind == SpecialType.BOMB:
            r = int(sz * 0.8 * scale)
            pygame.draw.circle(surf, (60, 60, 60), (x, y), r)
            pygame.draw.circle(surf, color, (x, y), r, 2)
            pygame.draw.line(surf, YELLOW, (x, y - r), (x + 3, y - r - 5), 2)
        elif self.kind == SpecialType.GOLDEN_APPLE:
            r = int(sz * 0.76 * scale)
            pygame.draw.circle(surf, color, (x, y), r)
            pygame.draw.circle(surf, (200, 170, 0), (x, y), r, 1)
            for angle in range(0, 360, 60):
                sx = x + int((r + 3) * math.cos(math.radians(angle + self.pulse * 30)))
                sy = y + int((r + 3) * math.sin(math.radians(angle + self.pulse * 30)))
                pygame.draw.circle(surf, WHITE, (sx, sy), 1)
        elif self.kind == SpecialType.SHIELD:
            r = int(sz * 0.8 * scale)
            pygame.draw.circle(surf, color, (x, y), r, 2)
            pygame.draw.circle(surf, (150, 150, 255), (x, y), r - 3)
        elif self.kind == SpecialType.GHOST:
            r = int(sz * 0.76 * scale)
            c = (180, 255, 220)
            pygame.draw.circle(surf, c, (x, y - 2), r)
            pygame.draw.rect(surf, c, (x - r, y - 2, r * 2, r))
            for i in range(4):
                bx = x - r + i * (r * 2 // 4) + r // 4
                pygame.draw.circle(surf, BG, (bx, y + r - 2), max(1, r // 4))
        else:
            r = int(sz * 0.76 * scale)
            pygame.draw.circle(surf, color, (x, y), r)
            pygame.draw.circle(surf, WHITE, (x, y), r, 1)
            txt = font.render(symbol, True, WHITE)
            surf.blit(txt, txt.get_rect(center=(x, y)))


# ---------------------------------------------------------------------------
# Particle effects
# ---------------------------------------------------------------------------
class Particle:
    def __init__(self, x, y, color):
        self.x, self.y = float(x), float(y)
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(1, 4)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = random.randint(10, 25)
        self.color = color
        self.r = random.randint(2, 4)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.life -= 1
        self.r = max(1, self.r - 0.1)

    def draw(self, surf):
        if self.life > 0:
            alpha = max(0, min(255, self.life * 12))
            c = tuple(min(255, int(ch * alpha / 255)) for ch in self.color)
            pygame.draw.circle(surf, c, (int(self.x), int(self.y)), int(self.r))


# ---------------------------------------------------------------------------
# Snake
# ---------------------------------------------------------------------------
class Snake:
    def __init__(self, idx: int, start_pos: tuple[int, int], direction,
                 is_ai: bool, wrap_walls: bool, grid):
        self.idx = idx
        self.is_ai = is_ai
        self.wrap_walls = wrap_walls
        self.grid = grid
        self.body: deque[tuple[int, int]] = deque()
        self.direction = direction
        self.next_direction = direction
        self.alive = True
        self.score = 0
        self.color, self.color2 = SNAKE_COLORS[idx]
        self.speed_mod = 0
        self.speed_mult = 1.0
        self.shield = False
        self.ghost_timer = 0
        self.magnet_timer = 0
        self.tick_accum = 0.0
        self.name = f"AI-{idx + 1}" if is_ai else f"P{idx + 1}"

        # Build initial body (length 4)
        pos = start_pos
        rev = grid.reverse_dir(direction)
        for i in range(4):
            self.body.append(pos)
            if i < 3:
                pos = grid.offset(pos, rev)

    def ai_choose_direction(self, specials: list, snakes: list):
        if not self.alive:
            return
        head = self.body[0]
        g = self.grid

        targets = [s for s in specials if s.kind in
                   (SpecialType.FOOD, SpecialType.GOLDEN_APPLE, SpecialType.SHIELD,
                    SpecialType.SPEED_BOOST, SpecialType.MAGNET, SpecialType.GHOST)]
        if not targets:
            targets = specials
        if not targets:
            return

        best = min(targets, key=lambda s: g.distance(head, s.pos))

        reverse = g.reverse_dir(self.direction)
        candidates = [d for d in g.directions() if d != reverse]

        occupied = set()
        for s in snakes:
            if s.alive and s is not self:
                occupied.update(s.body)
        occupied.update(list(self.body)[1:])

        def is_safe(d):
            new_pos = g.offset(head, d)
            if self.wrap_walls:
                new_pos = g.wrap(new_pos)
            else:
                if not g.in_bounds(new_pos):
                    return False
            if new_pos in occupied and self.ghost_timer <= 0:
                return False
            return True

        safe = [d for d in candidates if is_safe(d)]
        if not safe:
            return

        def score_dir(d):
            new_pos = g.offset(head, d)
            if self.wrap_walls:
                new_pos = g.wrap(new_pos)
            return g.distance(new_pos, best.pos)

        if random.random() < 0.08:
            self.next_direction = random.choice(safe)
        else:
            self.next_direction = min(safe, key=score_dir)

    def update_direction(self, new_dir):
        if not self.grid.is_reverse(new_dir, self.direction):
            self.next_direction = new_dir

    def move(self) -> tuple[int, int] | None:
        if not self.alive:
            return None

        self.direction = self.next_direction
        new_pos = self.grid.offset(self.body[0], self.direction)

        if self.wrap_walls:
            new_pos = self.grid.wrap(new_pos)
        else:
            if not self.grid.in_bounds(new_pos):
                if self.shield:
                    self.shield = False
                    self.direction = self.grid.reverse_dir(self.direction)
                    self.next_direction = self.direction
                    return self.body[0]
                self.alive = False
                return None

        self.body.appendleft(new_pos)
        self.body.pop()
        return new_pos

    def grow(self, amount=1):
        for _ in range(amount):
            self.body.append(self.body[-1])

    def shrink(self, amount=5):
        for _ in range(min(amount, len(self.body) - 2)):
            if len(self.body) > 2:
                self.body.pop()

    def reverse(self):
        self.body.reverse()
        if len(self.body) >= 2:
            self.direction = self.grid.infer_direction(self.body[1], self.body[0])
            self.next_direction = self.direction

    def draw(self, surf: pygame.Surface):
        if not self.alive:
            return
        g = self.grid
        for i, pos in enumerate(self.body):
            col = self.color if i % 2 == 0 else self.color2

            if self.ghost_timer > 0:
                col = tuple(min(255, c + 60) for c in col)

            if self.shield and i == 0:
                g.draw_cell_outline(surf, pos, (220, 220, 255), 2)

            g.draw_cell(surf, pos, col)

            if i == 0:
                # Eyes
                cx, cy = g.cell_to_pixel(pos)
                cx, cy = int(cx), int(cy)
                dx, dy = g.direction_to_pixel_offset(self.direction)
                ex1 = cx - 3
                ex2 = cx + 3
                ey = cy - 2
                pygame.draw.circle(surf, WHITE, (ex1, ey), 3)
                pygame.draw.circle(surf, WHITE, (ex2, ey), 3)
                pygame.draw.circle(surf, (20, 20, 20), (ex1 + dx, ey + dy), 1)
                pygame.draw.circle(surf, (20, 20, 20), (ex2 + dx, ey + dy), 1)


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------
class Game:
    def __init__(self, num_humans: int, num_snakes: int, wrap_walls: bool,
                 cols: int, rows: int, grid_mode: GridMode):
        self.num_humans = num_humans
        self.num_snakes = num_snakes
        self.wrap_walls = wrap_walls
        if grid_mode == GridMode.HEX:
            self.grid = HexGrid(cols, rows)
        else:
            self.grid = SquareGrid(cols, rows)
        self.snakes: list[Snake] = []
        self.specials: list[Special] = []
        self.particles: list[Particle] = []
        self.tick = 0
        self.game_over = False
        self.winner = None

        starts = self._generate_starts(num_snakes)
        for i in range(num_snakes):
            pos, d = starts[i]
            is_ai = i >= num_humans
            self.snakes.append(Snake(i, pos, d, is_ai, wrap_walls, self.grid))

        for _ in range(3 + num_snakes):
            self._spawn_special(SpecialType.FOOD)

    def _generate_starts(self, count):
        g = self.grid
        margin = 6
        cx, cy = g.cols // 2, g.rows // 2
        starts = []
        for i in range(count):
            angle = 2 * math.pi * i / count
            sx = int(cx + (cx - margin) * math.cos(angle))
            sy = int(cy + (cy - margin) * math.sin(angle))
            sx = max(margin, min(g.cols - margin, sx))
            sy = max(margin, min(g.rows - margin, sy))
            d = g.pick_start_direction(sx, sy, cx, cy)
            starts.append(((sx, sy), d))
        return starts

    def _free_cell(self):
        g = self.grid
        occupied = set()
        for s in self.snakes:
            occupied.update(s.body)
        for sp in self.specials:
            occupied.add(sp.pos)
        for _ in range(500):
            pos = (random.randint(0, g.cols - 1), random.randint(0, g.rows - 1))
            if pos not in occupied:
                return pos
        return (random.randint(0, g.cols - 1), random.randint(0, g.rows - 1))

    def _spawn_special(self, kind=None):
        if kind is None:
            roll = random.random()
            if roll < 0.35:
                kind = SpecialType.FOOD
            elif roll < 0.48:
                kind = SpecialType.SPEED_BOOST
            elif roll < 0.58:
                kind = SpecialType.SLOW_ZONE
            elif roll < 0.67:
                kind = SpecialType.SHIELD
            elif roll < 0.75:
                kind = SpecialType.REVERSE
            elif roll < 0.82:
                kind = SpecialType.MAGNET
            elif roll < 0.89:
                kind = SpecialType.BOMB
            elif roll < 0.95:
                kind = SpecialType.GHOST
            else:
                kind = SpecialType.GOLDEN_APPLE
        self.specials.append(Special(kind, self._free_cell()))

    def _emit_particles(self, pos, color, count=8):
        px, py = self.grid.cell_to_pixel(pos)
        for _ in range(count):
            self.particles.append(Particle(px, py, color))

    def handle_input(self, keys_pressed):
        is_hex = self.grid.mode == GridMode.HEX
        key_maps = HEX_PLAYER_KEYS if is_hex else PLAYER_KEYS
        max_h = MAX_HUMANS_HEX if is_hex else MAX_HUMANS
        for i, snake in enumerate(self.snakes):
            if snake.is_ai or not snake.alive:
                continue
            if i >= max_h:
                continue
            for key, d in key_maps[i].items():
                if keys_pressed[key]:
                    snake.update_direction(d)

    def update(self):
        if self.game_over:
            return

        self.tick += 1
        g = self.grid

        for s in self.snakes:
            if s.is_ai and s.alive:
                s.ai_choose_direction(self.specials, self.snakes)

        for s in self.snakes:
            if not s.alive:
                continue
            if s.speed_mod > 0:
                s.speed_mod -= 1
                if s.speed_mod == 0:
                    s.speed_mult = 1.0
            if s.ghost_timer > 0:
                s.ghost_timer -= 1
            if s.magnet_timer > 0:
                s.magnet_timer -= 1

            s.tick_accum += s.speed_mult
            if s.tick_accum >= 1.0:
                s.tick_accum -= 1.0
                s.move()
            if s.tick_accum >= 1.0:
                s.tick_accum -= 1.0
                s.move()

        # Magnet effect
        for s in self.snakes:
            if s.alive and s.magnet_timer > 0:
                head = s.body[0]
                for sp in self.specials:
                    if sp.kind in (SpecialType.FOOD, SpecialType.GOLDEN_APPLE):
                        dist = g.distance(head, sp.pos)
                        if 1 < dist < 8:
                            # Move food one step closer via best neighbor
                            best_nb = sp.pos
                            best_d = dist
                            for d in g.directions():
                                nb = g.offset(sp.pos, d)
                                if g.in_bounds(nb):
                                    nd = g.distance(head, nb)
                                    if nd < best_d:
                                        best_d = nd
                                        best_nb = nb
                            sp.pos = best_nb

        # Pickups
        for s in self.snakes:
            if not s.alive:
                continue
            head = s.body[0]
            for sp in self.specials[:]:
                if sp.pos == head:
                    self._apply_special(s, sp)
                    self.specials.remove(sp)

        # Collisions
        for s in self.snakes:
            if not s.alive:
                continue
            head = s.body[0]

            if head in list(s.body)[1:]:
                if s.ghost_timer <= 0:
                    if s.shield:
                        s.shield = False
                        s.shrink(3)
                    else:
                        s.alive = False
                        self._emit_particles(head, s.color, 20)
                        continue

            for other in self.snakes:
                if other is s or not other.alive:
                    continue
                if head in other.body:
                    if s.ghost_timer > 0:
                        continue
                    if s.shield:
                        s.shield = False
                        other.shrink(3)
                    else:
                        s.alive = False
                        self._emit_particles(head, s.color, 20)
                        break

        spawn_interval = max(15, 40 - self.num_snakes * 2)
        if self.tick % spawn_interval == 0:
            self._spawn_special()

        food_count = sum(1 for sp in self.specials if sp.kind == SpecialType.FOOD)
        min_food = 2 + self.num_snakes
        if food_count < min_food:
            self._spawn_special(SpecialType.FOOD)

        for sp in self.specials[:]:
            if sp.kind != SpecialType.FOOD:
                sp.timer -= 1
                if sp.timer <= 0:
                    self.specials.remove(sp)

        for p in self.particles[:]:
            p.update()
            if p.life <= 0:
                self.particles.remove(p)

        alive = [s for s in self.snakes if s.alive]
        if len(alive) <= 1:
            self.game_over = True
            if alive:
                self.winner = alive[0]

    def _apply_special(self, snake, sp):
        _, color, _, duration = SPECIAL_INFO[sp.kind]
        self._emit_particles(sp.pos, color, 12)

        if sp.kind == SpecialType.FOOD:
            snake.grow(1)
            snake.score += 1
        elif sp.kind == SpecialType.GOLDEN_APPLE:
            snake.grow(3)
            snake.score += 5
        elif sp.kind == SpecialType.SPEED_BOOST:
            snake.speed_mod = duration
            snake.speed_mult = 1.8
        elif sp.kind == SpecialType.SLOW_ZONE:
            snake.speed_mod = duration
            snake.speed_mult = 0.5
        elif sp.kind == SpecialType.SHIELD:
            snake.shield = True
        elif sp.kind == SpecialType.REVERSE:
            snake.reverse()
        elif sp.kind == SpecialType.MAGNET:
            snake.magnet_timer = duration
        elif sp.kind == SpecialType.BOMB:
            bx, by = sp.pos
            self._emit_particles(sp.pos, (255, 100, 30), 30)
            for other in self.snakes:
                if not other.alive:
                    continue
                for seg in list(other.body):
                    if self.grid.distance(seg, (bx, by)) < 5:
                        if other is not snake:
                            other.shrink(5)
                            other.score = max(0, other.score - 2)
                        break
            snake.score += 2
        elif sp.kind == SpecialType.GHOST:
            snake.ghost_timer = duration

    def draw(self, surf, font, small_font):
        g = self.grid
        win_w = surf.get_width()
        grid_w, grid_h = g.grid_pixel_size()

        surf.fill(BG)

        # Draw grid
        g.draw_grid(surf)

        # Wall indicator
        if not self.wrap_walls:
            pygame.draw.rect(surf, (180, 40, 40), (0, PANEL_H, grid_w, grid_h), 3)
        else:
            for x in range(0, grid_w, 20):
                pygame.draw.line(surf, (40, 120, 180), (x, PANEL_H), (x + 10, PANEL_H), 2)
                pygame.draw.line(surf, (40, 120, 180), (x, PANEL_H + grid_h - 1), (x + 10, PANEL_H + grid_h - 1), 2)
            for y in range(PANEL_H, PANEL_H + grid_h, 20):
                pygame.draw.line(surf, (40, 120, 180), (0, y), (0, y + 10), 2)
                pygame.draw.line(surf, (40, 120, 180), (grid_w - 1, y), (grid_w - 1, y + 10), 2)

        # Specials
        for sp in self.specials:
            sp.draw(surf, small_font, g)

        # Snakes
        for s in self.snakes:
            s.draw(surf)

        # Particles
        for p in self.particles:
            p.draw(surf)

        # Scoreboard panel
        pygame.draw.rect(surf, (20, 20, 35), (0, 0, win_w, PANEL_H))
        pygame.draw.line(surf, (60, 60, 80), (0, PANEL_H - 1), (win_w, PANEL_H - 1))

        n = len(self.snakes)
        if n <= 5:
            panel_w = win_w // max(n, 1)
            for i, s in enumerate(self.snakes):
                self._draw_snake_panel(surf, s, i * panel_w + 8, 4, panel_w, font, small_font)
        else:
            top_n = (n + 1) // 2
            bot_n = n - top_n
            pw_top = win_w // top_n
            pw_bot = win_w // max(bot_n, 1)
            for i in range(top_n):
                self._draw_snake_panel(surf, self.snakes[i], i * pw_top + 8, 2, pw_top, font, small_font)
            for i in range(bot_n):
                self._draw_snake_panel(surf, self.snakes[top_n + i], i * pw_bot + 8, 36, pw_bot, font, small_font)

        # Game over overlay
        if self.game_over:
            overlay = pygame.Surface((grid_w, grid_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))
            surf.blit(overlay, (0, PANEL_H))

            if self.winner:
                msg = f"{self.winner.name} WINS!"
                col = self.winner.color
            else:
                msg = "DRAW!"
                col = WHITE
            txt = font.render(msg, True, col)
            surf.blit(txt, txt.get_rect(center=(grid_w // 2, PANEL_H + grid_h // 2 - 20)))
            restart = small_font.render("Press SPACE to return to menu  |  ESC to quit", True, GRAY)
            surf.blit(restart, restart.get_rect(center=(grid_w // 2, PANEL_H + grid_h // 2 + 20)))

    def _draw_snake_panel(self, surf, s, x, y, w, font, small_font):
        label = s.name
        if s.is_ai:
            label += " [AI]"
        col = s.color if s.alive else DARK_GRAY
        pygame.draw.rect(surf, col, (x, y + 2, 10, 10), border_radius=2)
        txt = small_font.render(label, True, col)
        surf.blit(txt, (x + 14, y))
        score_txt = font.render(str(s.score), True, col)
        surf.blit(score_txt, (x + 14, y + 14))
        icon_x = x + 55
        icon_y = y + 20
        if s.shield:
            pygame.draw.circle(surf, (180, 180, 255), (icon_x, icon_y), 5, 2)
            icon_x += 14
        if s.ghost_timer > 0:
            pygame.draw.circle(surf, (180, 255, 220), (icon_x, icon_y), 5)
            icon_x += 14
        if s.magnet_timer > 0:
            pygame.draw.circle(surf, (255, 160, 60), (icon_x, icon_y), 5)
            icon_x += 14
        if s.speed_mod > 0:
            c = YELLOW if s.speed_mult > 1 else (100, 100, 255)
            pygame.draw.circle(surf, c, (icon_x, icon_y), 5)
        if not s.alive:
            dead_txt = small_font.render("DEAD", True, RED)
            surf.blit(dead_txt, (x + w - 50, y + 14))


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
class Menu:
    def __init__(self, screen, font, small_font, title_font):
        self.screen = screen
        self.font = font
        self.small_font = small_font
        self.title_font = title_font
        self.num_players = 1
        self.num_snakes = 4
        self.wrap_walls = True
        self.grid_mode = GridMode.SQUARE
        self.fullscreen = False
        # 0=players, 1=snakes, 2=walls, 3=grid, 4=fullscreen, 5=start
        self.selected = 0
        self.options = 6

    def _max_humans(self):
        return MAX_HUMANS_HEX if self.grid_mode == GridMode.HEX else MAX_HUMANS

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected - 1) % self.options
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected = (self.selected + 1) % self.options
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                if self.selected == 0:
                    self.num_players = max(1, self.num_players - 1)
                elif self.selected == 1:
                    self.num_snakes = max(1, self.num_snakes - 1)
                    self.num_players = min(self.num_players, self.num_snakes)
                elif self.selected == 2:
                    self.wrap_walls = not self.wrap_walls
                elif self.selected == 3:
                    self.grid_mode = GridMode.SQUARE if self.grid_mode == GridMode.HEX else GridMode.HEX
                    self.num_players = min(self.num_players, self._max_humans())
                elif self.selected == 4:
                    self.fullscreen = not self.fullscreen
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                if self.selected == 0:
                    self.num_players = min(self._max_humans(),
                                           min(self.num_snakes, self.num_players + 1))
                elif self.selected == 1:
                    self.num_snakes = min(MAX_SNAKES, self.num_snakes + 1)
                elif self.selected == 2:
                    self.wrap_walls = not self.wrap_walls
                elif self.selected == 3:
                    self.grid_mode = GridMode.SQUARE if self.grid_mode == GridMode.HEX else GridMode.HEX
                    self.num_players = min(self.num_players, self._max_humans())
                elif self.selected == 4:
                    self.fullscreen = not self.fullscreen
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.selected == self.options - 1:
                    return "start"
                elif self.selected == 2:
                    self.wrap_walls = not self.wrap_walls
                elif self.selected == 3:
                    self.grid_mode = GridMode.SQUARE if self.grid_mode == GridMode.HEX else GridMode.HEX
                    self.num_players = min(self.num_players, self._max_humans())
                elif self.selected == 4:
                    self.fullscreen = not self.fullscreen
        return None

    def draw(self):
        w = self.screen.get_width()
        h = self.screen.get_height()
        self.screen.fill(MENU_BG)

        title = self.title_font.render("SNAKE ARENA", True, HIGHLIGHT)
        self.screen.blit(title, title.get_rect(center=(w // 2, 70)))

        subtitle = self.small_font.render(
            "Up to 4 human players  |  Up to 10 snakes  |  Square or Hex grid", True, GRAY)
        self.screen.blit(subtitle, subtitle.get_rect(center=(w // 2, 110)))

        cy = 155
        gap = 42
        is_hex = self.grid_mode == GridMode.HEX

        # Players
        col = HIGHLIGHT if self.selected == 0 else WHITE
        ai_count = self.num_snakes - self.num_players
        txt = self.font.render(f"<  Human Players: {self.num_players}  >", True, col)
        self.screen.blit(txt, txt.get_rect(center=(w // 2, cy)))

        # Total snakes
        cy += gap
        col = HIGHLIGHT if self.selected == 1 else WHITE
        txt = self.font.render(f"<  Total Snakes: {self.num_snakes}  ({ai_count} AI)  >", True, col)
        self.screen.blit(txt, txt.get_rect(center=(w // 2, cy)))

        # Walls
        cy += gap
        col = HIGHLIGHT if self.selected == 2 else WHITE
        mode = "Wrap (traverse)" if self.wrap_walls else "Solid (collide)"
        txt = self.font.render(f"<  Walls: {mode}  >", True, col)
        self.screen.blit(txt, txt.get_rect(center=(w // 2, cy)))

        # Grid mode
        cy += gap
        col = HIGHLIGHT if self.selected == 3 else WHITE
        gm = "Hexagonal" if is_hex else "Square"
        txt = self.font.render(f"<  Grid: {gm}  >", True, col)
        self.screen.blit(txt, txt.get_rect(center=(w // 2, cy)))

        # Fullscreen
        cy += gap
        col = HIGHLIGHT if self.selected == 4 else WHITE
        fs_label = "Fullscreen (max grid)" if self.fullscreen else "Windowed (800x660)"
        txt = self.font.render(f"<  Display: {fs_label}  >", True, col)
        self.screen.blit(txt, txt.get_rect(center=(w // 2, cy)))

        # Start
        cy += gap + 16
        col = HIGHLIGHT if self.selected == self.options - 1 else WHITE
        txt = self.font.render("[ START GAME ]", True, col)
        self.screen.blit(txt, txt.get_rect(center=(w // 2, cy)))

        # Controls help
        cy = h - 175
        if is_hex:
            controls = [
                ("P1: Q/W (NW/NE)  A/D (W/E)  Z/X (SW/SE)", SNAKE_COLORS[0][0]),
                ("P2: U/I (NW/NE)  J/L (W/E)  N/M (SW/SE)", SNAKE_COLORS[1][0]),
                ("P3: Numpad 7/9  4/6  1/3", SNAKE_COLORS[2][0]),
            ]
        else:
            controls = [
                ("P1: W/A/S/D", SNAKE_COLORS[0][0]),
                ("P2: Arrow Keys", SNAKE_COLORS[1][0]),
                ("P3: I/J/K/L", SNAKE_COLORS[2][0]),
                ("P4: Numpad 8/4/5/6", SNAKE_COLORS[3][0]),
            ]
        header = self.small_font.render("— Controls —", True, GRAY)
        self.screen.blit(header, header.get_rect(center=(w // 2, cy - 20)))
        for i, (text, color) in enumerate(controls):
            txt = self.small_font.render(text, True, color)
            self.screen.blit(txt, txt.get_rect(center=(w // 2, cy + 8 + i * 20)))

        # Specials legend
        legend_y = cy + 8 + len(controls) * 20 + 15
        legend_header = self.small_font.render("— Power-ups —", True, GRAY)
        self.screen.blit(legend_header, legend_header.get_rect(center=(w // 2, legend_y)))
        items = [
            ("● Food (+1)", (255, 50, 50)),
            ("★ Golden (+5)", (255, 215, 0)),
            ("⚡ Speed", (255, 255, 80)),
            ("❄ Slow", (100, 100, 255)),
            ("🛡 Shield", (200, 200, 255)),
            ("⟳ Reverse", (255, 100, 255)),
            ("⊕ Magnet", (255, 160, 60)),
            ("💣 Bomb", (255, 80, 30)),
            ("👻 Ghost", (180, 255, 220)),
        ]
        cols_count = 3
        col_w = w // cols_count
        for i, (label, color) in enumerate(items):
            r = i // cols_count
            c = i % cols_count
            x = c * col_w + col_w // 2
            y = legend_y + 18 + r * 18
            t = self.small_font.render(label, True, color)
            self.screen.blit(t, t.get_rect(center=(x, y)))

        foot = self.small_font.render("F11 to toggle fullscreen  |  ESC to quit", True, DARK_GRAY)
        self.screen.blit(foot, foot.get_rect(center=(w // 2, h - 12)))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    pygame.init()
    desk_info = pygame.display.Info()
    desk_w, desk_h = desk_info.current_w, desk_info.current_h
    default_w, default_h = 800, 660

    screen = pygame.display.set_mode((default_w, default_h), pygame.RESIZABLE)
    pygame.display.set_caption("Snake Arena")
    clock = pygame.time.Clock()
    is_fullscreen = False

    title_font = pygame.font.SysFont("Arial", 48, bold=True)
    font = pygame.font.SysFont("Arial", 22, bold=True)
    small_font = pygame.font.SysFont("Arial", 15)

    menu = Menu(screen, font, small_font, title_font)
    game: Game | None = None
    state = "menu"

    def toggle_fullscreen():
        nonlocal screen, is_fullscreen
        if is_fullscreen:
            screen = pygame.display.set_mode((default_w, default_h), pygame.RESIZABLE)
            is_fullscreen = False
        else:
            screen = pygame.display.set_mode((desk_w, desk_h), pygame.NOFRAME)
            is_fullscreen = True
        pygame.display.set_caption("Snake Arena")
        menu.screen = screen
        menu.fullscreen = is_fullscreen

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    toggle_fullscreen()
                elif event.key == pygame.K_ESCAPE:
                    if state == "playing":
                        state = "menu"
                        game = None
                        if is_fullscreen:
                            toggle_fullscreen()
                    else:
                        running = False

            if event.type == pygame.VIDEORESIZE and not is_fullscreen:
                screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                menu.screen = screen

            if state == "menu":
                result = menu.handle_event(event)
                if result == "start":
                    if menu.fullscreen != is_fullscreen:
                        toggle_fullscreen()
                    win_w = screen.get_width()
                    win_h = screen.get_height()
                    if menu.grid_mode == GridMode.HEX:
                        cols, rows = HexGrid.grid_from_window(win_w, win_h)
                    else:
                        cols, rows = SquareGrid.grid_from_window(win_w, win_h)
                    game = Game(menu.num_players, menu.num_snakes,
                                menu.wrap_walls, cols, rows, menu.grid_mode)
                    state = "playing"

            elif state == "playing" and game and game.game_over:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    state = "menu"
                    game = None

        if state == "menu":
            menu.draw()
        elif state == "playing" and game:
            keys = pygame.key.get_pressed()
            game.handle_input(keys)
            game.update()
            game.draw(screen, font, small_font)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
