"""
Multiplayer Snake Arena with AI opponents and special items.
Supports 1-4 human players, 1-10 total snakes, resizable/fullscreen grid.
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
PANEL_H = 70  # scoreboard panel at the top
FPS = 12

# Directions
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
    ((50, 200, 80), (30, 160, 60)),      # Green
    ((60, 130, 230), (40, 100, 190)),     # Blue
    ((230, 160, 40), (190, 120, 20)),     # Orange
    ((200, 60, 200), (160, 30, 160)),     # Purple
    ((220, 60, 60), (180, 40, 40)),       # Red
    ((60, 210, 210), (30, 170, 170)),     # Cyan
    ((210, 210, 60), (170, 170, 30)),     # Yellow
    ((255, 130, 170), (210, 90, 130)),    # Pink
    ((140, 100, 60), (100, 70, 40)),      # Brown
    ((180, 180, 180), (130, 130, 130)),   # Silver
]

# Key mappings per human player (max 4 human-controllable)
PLAYER_KEYS = [
    {pygame.K_w: UP, pygame.K_s: DOWN, pygame.K_a: LEFT, pygame.K_d: RIGHT},
    {pygame.K_UP: UP, pygame.K_DOWN: DOWN, pygame.K_LEFT: LEFT, pygame.K_RIGHT: RIGHT},
    {pygame.K_i: UP, pygame.K_k: DOWN, pygame.K_j: LEFT, pygame.K_l: RIGHT},
    {pygame.K_KP8: UP, pygame.K_KP5: DOWN, pygame.K_KP4: LEFT, pygame.K_KP6: RIGHT},
]

MAX_HUMANS = len(PLAYER_KEYS)  # 4
MAX_SNAKES = len(SNAKE_COLORS)  # 10


# ---------------------------------------------------------------------------
# Grid helper – computes cols/rows from current window size
# ---------------------------------------------------------------------------
def grid_from_window(win_w: int, win_h: int) -> tuple[int, int]:
    """Return (cols, rows) for the playable area."""
    cols = max(MIN_COLS, win_w // CELL)
    rows = max(MIN_ROWS, (win_h - PANEL_H) // CELL)
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

    def draw(self, surf: pygame.Surface, font: pygame.font.Font):
        _, color, symbol, _ = SPECIAL_INFO[self.kind]
        self.pulse = (self.pulse + 0.12) % (2 * math.pi)
        scale = 1.0 + 0.15 * math.sin(self.pulse)
        x = self.pos[0] * CELL + CELL // 2
        y = self.pos[1] * CELL + CELL // 2 + PANEL_H

        if self.kind == SpecialType.FOOD:
            r = int(CELL * 0.35 * scale)
            pygame.draw.circle(surf, color, (x, y), r)
            pygame.draw.circle(surf, (255, 120, 120), (x, y), r, 1)
        elif self.kind == SpecialType.BOMB:
            r = int(CELL * 0.4 * scale)
            pygame.draw.circle(surf, (60, 60, 60), (x, y), r)
            pygame.draw.circle(surf, color, (x, y), r, 2)
            pygame.draw.line(surf, YELLOW, (x, y - r), (x + 3, y - r - 5), 2)
        elif self.kind == SpecialType.GOLDEN_APPLE:
            r = int(CELL * 0.38 * scale)
            pygame.draw.circle(surf, color, (x, y), r)
            pygame.draw.circle(surf, (200, 170, 0), (x, y), r, 1)
            for angle in range(0, 360, 60):
                sx = x + int((r + 3) * math.cos(math.radians(angle + self.pulse * 30)))
                sy = y + int((r + 3) * math.sin(math.radians(angle + self.pulse * 30)))
                pygame.draw.circle(surf, WHITE, (sx, sy), 1)
        elif self.kind == SpecialType.SHIELD:
            r = int(CELL * 0.4 * scale)
            pygame.draw.circle(surf, color, (x, y), r, 2)
            pygame.draw.circle(surf, (150, 150, 255), (x, y), r - 3)
        elif self.kind == SpecialType.GHOST:
            r = int(CELL * 0.38 * scale)
            c = (180, 255, 220)
            pygame.draw.circle(surf, c, (x, y - 2), r)
            pygame.draw.rect(surf, c, (x - r, y - 2, r * 2, r))
            for i in range(4):
                bx = x - r + i * (r * 2 // 4) + r // 4
                pygame.draw.circle(surf, BG, (bx, y + r - 2), r // 4)
        else:
            r = int(CELL * 0.38 * scale)
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
    def __init__(self, idx: int, start_pos: tuple[int, int], direction: tuple[int, int],
                 is_ai: bool, wrap_walls: bool, cols: int, rows: int):
        self.idx = idx
        self.is_ai = is_ai
        self.wrap_walls = wrap_walls
        self.cols = cols
        self.rows = rows
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

        for i in range(4):
            self.body.append((start_pos[0] - direction[0] * i,
                              start_pos[1] - direction[1] * i))

    def ai_choose_direction(self, specials: list, snakes: list):
        if not self.alive:
            return
        head = self.body[0]

        targets = [s for s in specials if s.kind in
                   (SpecialType.FOOD, SpecialType.GOLDEN_APPLE, SpecialType.SHIELD,
                    SpecialType.SPEED_BOOST, SpecialType.MAGNET, SpecialType.GHOST)]
        if not targets:
            targets = specials
        if not targets:
            return

        best = min(targets, key=lambda s: abs(s.pos[0] - head[0]) + abs(s.pos[1] - head[1]))

        reverse = (-self.direction[0], -self.direction[1])
        candidates = [d for d in DIRS if d != reverse]

        occupied = set()
        for s in snakes:
            if s.alive and s is not self:
                occupied.update(s.body)
        occupied.update(list(self.body)[1:])

        def is_safe(d):
            nx, ny = head[0] + d[0], head[1] + d[1]
            if self.wrap_walls:
                nx %= self.cols
                ny %= self.rows
            else:
                if nx < 0 or nx >= self.cols or ny < 0 or ny >= self.rows:
                    return False
            if (nx, ny) in occupied and self.ghost_timer <= 0:
                return False
            return True

        safe = [d for d in candidates if is_safe(d)]
        if not safe:
            return

        def score_dir(d):
            nx, ny = head[0] + d[0], head[1] + d[1]
            if self.wrap_walls:
                nx %= self.cols
                ny %= self.rows
            return abs(best.pos[0] - nx) + abs(best.pos[1] - ny)

        if random.random() < 0.08:
            self.next_direction = random.choice(safe)
        else:
            self.next_direction = min(safe, key=score_dir)

    def update_direction(self, new_dir):
        reverse = (-self.direction[0], -self.direction[1])
        if new_dir != reverse:
            self.next_direction = new_dir

    def move(self) -> tuple[int, int] | None:
        if not self.alive:
            return None

        self.direction = self.next_direction
        hx, hy = self.body[0]
        nx, ny = hx + self.direction[0], hy + self.direction[1]

        if self.wrap_walls:
            nx %= self.cols
            ny %= self.rows
        else:
            if nx < 0 or nx >= self.cols or ny < 0 or ny >= self.rows:
                if self.shield:
                    self.shield = False
                    self.direction = (-self.direction[0], -self.direction[1])
                    self.next_direction = self.direction
                    return self.body[0]
                self.alive = False
                return None

        self.body.appendleft((nx, ny))
        self.body.pop()
        return (nx, ny)

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
            hx, hy = self.body[0]
            nx, ny = self.body[1]
            self.direction = (hx - nx, hy - ny)
            self.next_direction = self.direction

    def draw(self, surf: pygame.Surface):
        if not self.alive:
            return
        for i, (cx, cy) in enumerate(self.body):
            rect = pygame.Rect(cx * CELL, cy * CELL + PANEL_H, CELL, CELL)
            col = self.color if i % 2 == 0 else self.color2

            if self.ghost_timer > 0:
                col = tuple(min(255, c + 60) for c in col)

            if self.shield and i == 0:
                pygame.draw.rect(surf, (220, 220, 255), rect.inflate(4, 4), 2, border_radius=4)

            pygame.draw.rect(surf, col, rect.inflate(-2, -2), border_radius=4)

            if i == 0:
                ex1 = rect.centerx - 3
                ex2 = rect.centerx + 3
                ey = rect.centery - 2
                pygame.draw.circle(surf, WHITE, (ex1, ey), 3)
                pygame.draw.circle(surf, WHITE, (ex2, ey), 3)
                pygame.draw.circle(surf, (20, 20, 20),
                                   (ex1 + self.direction[0], ey + self.direction[1]), 1)
                pygame.draw.circle(surf, (20, 20, 20),
                                   (ex2 + self.direction[0], ey + self.direction[1]), 1)


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------
class Game:
    def __init__(self, num_humans: int, num_snakes: int, wrap_walls: bool,
                 cols: int, rows: int):
        self.num_humans = num_humans
        self.num_snakes = num_snakes
        self.wrap_walls = wrap_walls
        self.cols = cols
        self.rows = rows
        self.snakes: list[Snake] = []
        self.specials: list[Special] = []
        self.particles: list[Particle] = []
        self.tick = 0
        self.game_over = False
        self.winner = None

        # Generate spawn positions distributed around the map edges
        starts = self._generate_starts(num_snakes)
        for i in range(num_snakes):
            pos, d = starts[i]
            is_ai = i >= num_humans
            self.snakes.append(Snake(i, pos, d, is_ai, wrap_walls, cols, rows))

        # Initial food scales with snake count
        for _ in range(3 + num_snakes):
            self._spawn_special(SpecialType.FOOD)

    def _generate_starts(self, count: int) -> list[tuple[tuple[int, int], tuple[int, int]]]:
        """Generate evenly-spaced starting positions around the perimeter."""
        margin = 6
        cx, cy = self.cols // 2, self.rows // 2
        # Place snakes in a circle around the center
        starts = []
        for i in range(count):
            angle = 2 * math.pi * i / count
            sx = int(cx + (cx - margin) * math.cos(angle))
            sy = int(cy + (cy - margin) * math.sin(angle))
            sx = max(margin, min(self.cols - margin, sx))
            sy = max(margin, min(self.rows - margin, sy))
            # Direction: point toward center
            dx = 1 if cx > sx else -1 if cx < sx else 0
            dy = 1 if cy > sy else -1 if cy < sy else 0
            # Pick primary axis
            if abs(cx - sx) >= abs(cy - sy):
                d = (dx, 0)
            else:
                d = (0, dy)
            if d == (0, 0):
                d = RIGHT
            starts.append(((sx, sy), d))
        return starts

    def _free_cell(self) -> tuple[int, int]:
        occupied = set()
        for s in self.snakes:
            occupied.update(s.body)
        for sp in self.specials:
            occupied.add(sp.pos)
        for _ in range(500):
            pos = (random.randint(0, self.cols - 1), random.randint(0, self.rows - 1))
            if pos not in occupied:
                return pos
        return (random.randint(0, self.cols - 1), random.randint(0, self.rows - 1))

    def _spawn_special(self, kind: SpecialType | None = None):
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
        x = pos[0] * CELL + CELL // 2
        y = pos[1] * CELL + CELL // 2 + PANEL_H
        for _ in range(count):
            self.particles.append(Particle(x, y, color))

    def handle_input(self, keys_pressed):
        for i, snake in enumerate(self.snakes):
            if snake.is_ai or not snake.alive:
                continue
            if i >= MAX_HUMANS:
                continue
            for key, d in PLAYER_KEYS[i].items():
                if keys_pressed[key]:
                    snake.update_direction(d)

    def update(self):
        if self.game_over:
            return

        self.tick += 1

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
                        dx = head[0] - sp.pos[0]
                        dy = head[1] - sp.pos[1]
                        dist = abs(dx) + abs(dy)
                        if 1 < dist < 8:
                            mx = (1 if dx > 0 else -1 if dx < 0 else 0)
                            my = (1 if dy > 0 else -1 if dy < 0 else 0)
                            sp.pos = (sp.pos[0] + mx, sp.pos[1] + my)

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

        # Spawn specials (scale rate with snake count)
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

    def _apply_special(self, snake: Snake, sp: Special):
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
                    if abs(seg[0] - bx) + abs(seg[1] - by) < 5:
                        if other is not snake:
                            other.shrink(5)
                            other.score = max(0, other.score - 2)
                        break
            snake.score += 2
        elif sp.kind == SpecialType.GHOST:
            snake.ghost_timer = duration

    def draw(self, surf: pygame.Surface, font: pygame.font.Font, small_font: pygame.font.Font):
        win_w = surf.get_width()
        win_h = surf.get_height()
        grid_w = self.cols * CELL
        grid_h = self.rows * CELL

        surf.fill(BG)

        # Draw grid
        for x in range(0, grid_w + 1, CELL):
            pygame.draw.line(surf, GRID_COL, (x, PANEL_H), (x, PANEL_H + grid_h))
        for y in range(PANEL_H, PANEL_H + grid_h + 1, CELL):
            pygame.draw.line(surf, GRID_COL, (0, y), (grid_w, y))

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
            sp.draw(surf, small_font)

        # Snakes
        for s in self.snakes:
            s.draw(surf)

        # Particles
        for p in self.particles:
            p.draw(surf)

        # Scoreboard panel
        pygame.draw.rect(surf, (20, 20, 35), (0, 0, win_w, PANEL_H))
        pygame.draw.line(surf, (60, 60, 80), (0, PANEL_H - 1), (win_w, PANEL_H - 1))

        # Adaptive layout: 2 rows if > 5 snakes
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
        # Color swatch
        pygame.draw.rect(surf, col, (x, y + 2, 10, 10), border_radius=2)
        txt = small_font.render(label, True, col)
        surf.blit(txt, (x + 14, y))
        # Score
        score_txt = font.render(str(s.score), True, col)
        surf.blit(score_txt, (x + 14, y + 14))
        # Status icons
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
        self.fullscreen = False
        self.selected = 0  # 0=players, 1=snakes, 2=walls, 3=fullscreen, 4=start
        self.options = 5

    def handle_event(self, event) -> str | None:
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
                    # Ensure humans <= snakes
                    self.num_players = min(self.num_players, self.num_snakes)
                elif self.selected == 2:
                    self.wrap_walls = not self.wrap_walls
                elif self.selected == 3:
                    self.fullscreen = not self.fullscreen
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                if self.selected == 0:
                    self.num_players = min(MAX_HUMANS, min(self.num_snakes, self.num_players + 1))
                elif self.selected == 1:
                    self.num_snakes = min(MAX_SNAKES, self.num_snakes + 1)
                elif self.selected == 2:
                    self.wrap_walls = not self.wrap_walls
                elif self.selected == 3:
                    self.fullscreen = not self.fullscreen
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.selected == self.options - 1:
                    return "start"
                elif self.selected == 2:
                    self.wrap_walls = not self.wrap_walls
                elif self.selected == 3:
                    self.fullscreen = not self.fullscreen
        return None

    def draw(self):
        w = self.screen.get_width()
        h = self.screen.get_height()
        self.screen.fill(MENU_BG)

        # Title
        title = self.title_font.render("SNAKE ARENA", True, HIGHLIGHT)
        self.screen.blit(title, title.get_rect(center=(w // 2, 80)))

        subtitle = self.small_font.render(
            "Up to 4 human players  |  Up to 10 snakes  |  AI opponents  |  Power-ups", True, GRAY)
        self.screen.blit(subtitle, subtitle.get_rect(center=(w // 2, 120)))

        cy = 175
        gap = 50

        # Players
        col = HIGHLIGHT if self.selected == 0 else WHITE
        ai_count = self.num_snakes - self.num_players
        txt = self.font.render(
            f"<  Human Players: {self.num_players}  >", True, col)
        self.screen.blit(txt, txt.get_rect(center=(w // 2, cy)))

        # Total snakes
        cy += gap
        col = HIGHLIGHT if self.selected == 1 else WHITE
        txt = self.font.render(
            f"<  Total Snakes: {self.num_snakes}  ({ai_count} AI)  >", True, col)
        self.screen.blit(txt, txt.get_rect(center=(w // 2, cy)))

        # Walls
        cy += gap
        col = HIGHLIGHT if self.selected == 2 else WHITE
        mode = "Wrap (traverse)" if self.wrap_walls else "Solid (collide)"
        txt = self.font.render(f"<  Walls: {mode}  >", True, col)
        self.screen.blit(txt, txt.get_rect(center=(w // 2, cy)))

        # Fullscreen
        cy += gap
        col = HIGHLIGHT if self.selected == 3 else WHITE
        fs_label = "Fullscreen (max grid)" if self.fullscreen else "Windowed (800x660)"
        txt = self.font.render(f"<  Display: {fs_label}  >", True, col)
        self.screen.blit(txt, txt.get_rect(center=(w // 2, cy)))

        # Start
        cy += gap + 20
        col = HIGHLIGHT if self.selected == self.options - 1 else WHITE
        txt = self.font.render("[ START GAME ]", True, col)
        self.screen.blit(txt, txt.get_rect(center=(w // 2, cy)))

        # Controls help
        cy = h - 170
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
            self.screen.blit(txt, txt.get_rect(center=(w // 2, cy + 10 + i * 22)))

        # Specials legend
        legend_y = cy + 105
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
            y = legend_y + 20 + r * 20
            t = self.small_font.render(label, True, color)
            self.screen.blit(t, t.get_rect(center=(x, y)))

        # Footer
        foot = self.small_font.render("F11 to toggle fullscreen  |  ESC to quit", True, DARK_GRAY)
        self.screen.blit(foot, foot.get_rect(center=(w // 2, h - 15)))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    pygame.init()
    info = pygame.display.Info()
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
            screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            is_fullscreen = True
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
                        # Restore window mode if needed
                    else:
                        running = False

            if event.type == pygame.VIDEORESIZE and not is_fullscreen:
                screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                menu.screen = screen

            if state == "menu":
                result = menu.handle_event(event)
                if result == "start":
                    # Apply fullscreen preference from menu
                    if menu.fullscreen != is_fullscreen:
                        toggle_fullscreen()
                    win_w = screen.get_width()
                    win_h = screen.get_height()
                    cols, rows = grid_from_window(win_w, win_h)
                    game = Game(menu.num_players, menu.num_snakes,
                                menu.wrap_walls, cols, rows)
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
