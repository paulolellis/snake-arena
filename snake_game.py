"""
Multiplayer Snake Game with AI opponents and special items.
Supports 1-4 human players with AI filling remaining slots.
"""

import pygame
import random
import math
import sys
from enum import Enum, auto
from collections import deque

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CELL = 20
COLS, ROWS = 40, 30
WIDTH, HEIGHT = COLS * CELL, ROWS * CELL
PANEL_H = 60  # scoreboard panel at the top
WIN_W, WIN_H = WIDTH, HEIGHT + PANEL_H
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
    ((50, 200, 80), (30, 160, 60)),    # Green  – P1
    ((60, 130, 230), (40, 100, 190)),   # Blue   – P2
    ((230, 160, 40), (190, 120, 20)),   # Orange – P3
    ((200, 60, 200), (160, 30, 160)),   # Purple – P4
]

# Key mappings per player
PLAYER_KEYS = [
    {pygame.K_w: UP, pygame.K_s: DOWN, pygame.K_a: LEFT, pygame.K_d: RIGHT},
    {pygame.K_UP: UP, pygame.K_DOWN: DOWN, pygame.K_LEFT: LEFT, pygame.K_RIGHT: RIGHT},
    {pygame.K_i: UP, pygame.K_k: DOWN, pygame.K_j: LEFT, pygame.K_l: RIGHT},
    {pygame.K_KP8: UP, pygame.K_KP5: DOWN, pygame.K_KP4: LEFT, pygame.K_KP6: RIGHT},
]


# ---------------------------------------------------------------------------
# Specials
# ---------------------------------------------------------------------------
class SpecialType(Enum):
    FOOD = auto()
    SPEED_BOOST = auto()   # temporary speed increase
    SLOW_ZONE = auto()     # slow the snake that picks it up
    SHIELD = auto()        # survive one collision
    REVERSE = auto()       # reverse direction of the snake
    MAGNET = auto()        # food gravitates toward you for a while
    BOMB = auto()          # explodes — removes 5 segments from nearby snakes
    GHOST = auto()         # pass through other snakes for a few seconds
    GOLDEN_APPLE = auto()  # worth 5 points


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
        self.timer = 300  # ticks before it despawns (food never despawns)
        self.pulse = 0

    def draw(self, surf: pygame.Surface, font: pygame.font.Font):
        name, color, symbol, _ = SPECIAL_INFO[self.kind]
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
            # sparkle
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
            alpha_color = (180, 255, 220)
            pygame.draw.circle(surf, alpha_color, (x, y - 2), r)
            pygame.draw.rect(surf, alpha_color, (x - r, y - 2, r * 2, r))
            # wavy bottom
            for i in range(4):
                bx = x - r + i * (r * 2 // 4) + r // 4
                pygame.draw.circle(surf, BG, (bx, y + r - 2), r // 4)
        else:
            # Generic: colored circle with border
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
                 is_ai: bool, wrap_walls: bool):
        self.idx = idx
        self.is_ai = is_ai
        self.wrap_walls = wrap_walls
        self.body: deque[tuple[int, int]] = deque()
        self.direction = direction
        self.next_direction = direction
        self.alive = True
        self.score = 0
        self.color, self.color2 = SNAKE_COLORS[idx]
        self.speed_mod = 0       # ticks remaining for speed buff/debuff
        self.speed_mult = 1.0
        self.shield = False
        self.ghost_timer = 0
        self.magnet_timer = 0
        self.tick_accum = 0.0
        self.name = f"AI-{idx+1}" if is_ai else f"P{idx+1}"

        # Build initial body (length 4)
        for i in range(4):
            self.body.append((start_pos[0] - direction[0] * i,
                              start_pos[1] - direction[1] * i))

    # -- AI logic -----------------------------------------------------------
    def ai_choose_direction(self, specials: list, snakes: list):
        if not self.alive:
            return
        head = self.body[0]

        # Find nearest food-like item
        targets = [s for s in specials if s.kind in
                   (SpecialType.FOOD, SpecialType.GOLDEN_APPLE, SpecialType.SHIELD,
                    SpecialType.SPEED_BOOST, SpecialType.MAGNET, SpecialType.GHOST)]
        if not targets:
            targets = specials  # go for anything

        if not targets:
            return

        best = min(targets, key=lambda s: abs(s.pos[0] - head[0]) + abs(s.pos[1] - head[1]))

        # Determine desired direction
        dx = best.pos[0] - head[0]
        dy = best.pos[1] - head[1]

        # Possible directions (exclude reverse)
        reverse = (-self.direction[0], -self.direction[1])
        candidates = [d for d in DIRS if d != reverse]

        # Collect all occupied cells for danger check
        occupied = set()
        for s in snakes:
            if s.alive and s is not self:
                occupied.update(s.body)
        occupied.update(list(self.body)[1:])

        def is_safe(d):
            nx, ny = head[0] + d[0], head[1] + d[1]
            if self.wrap_walls:
                nx %= COLS
                ny %= ROWS
            else:
                if nx < 0 or nx >= COLS or ny < 0 or ny >= ROWS:
                    return False
            if (nx, ny) in occupied and self.ghost_timer <= 0:
                return False
            return True

        safe = [d for d in candidates if is_safe(d)]
        if not safe:
            return  # doomed

        # Prefer direction toward target
        def score_dir(d):
            nx, ny = head[0] + d[0], head[1] + d[1]
            if self.wrap_walls:
                nx %= COLS
                ny %= ROWS
            return abs(best.pos[0] - nx) + abs(best.pos[1] - ny)

        # Add slight randomness so AI isn't perfect
        if random.random() < 0.08:
            self.next_direction = random.choice(safe)
        else:
            self.next_direction = min(safe, key=score_dir)

    # -- Movement -----------------------------------------------------------
    def update_direction(self, new_dir):
        """Queue a new direction (prevent 180° reversal)."""
        reverse = (-self.direction[0], -self.direction[1])
        if new_dir != reverse:
            self.next_direction = new_dir

    def move(self) -> tuple[int, int] | None:
        """Move one step. Returns new head position or None if dead."""
        if not self.alive:
            return None

        self.direction = self.next_direction
        hx, hy = self.body[0]
        nx, ny = hx + self.direction[0], hy + self.direction[1]

        if self.wrap_walls:
            nx %= COLS
            ny %= ROWS
        else:
            if nx < 0 or nx >= COLS or ny < 0 or ny >= ROWS:
                if self.shield:
                    self.shield = False
                    # bounce back
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
            x = cx * CELL + PANEL_H  # wait, this isn't right
            rect = pygame.Rect(cx * CELL, cy * CELL + PANEL_H, CELL, CELL)
            col = self.color if i % 2 == 0 else self.color2

            if self.ghost_timer > 0:
                # semi-transparent look
                col = tuple(min(255, c + 60) for c in col)

            if self.shield and i == 0:
                pygame.draw.rect(surf, (220, 220, 255), rect.inflate(4, 4), 2, border_radius=4)

            pygame.draw.rect(surf, col, rect.inflate(-2, -2), border_radius=4)

            if i == 0:
                # Eyes
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
    def __init__(self, num_humans: int, wrap_walls: bool):
        self.num_humans = num_humans
        self.wrap_walls = wrap_walls
        self.snakes: list[Snake] = []
        self.specials: list[Special] = []
        self.particles: list[Particle] = []
        self.tick = 0
        self.game_over = False
        self.winner = None

        # Spawn 4 snakes total
        starts = [
            ((5, 5), RIGHT),
            ((COLS - 6, ROWS - 6), LEFT),
            ((COLS - 6, 5), DOWN),
            ((5, ROWS - 6), UP),
        ]
        for i in range(4):
            pos, d = starts[i]
            is_ai = i >= num_humans
            self.snakes.append(Snake(i, pos, d, is_ai, wrap_walls))

        # Initial food
        for _ in range(5):
            self._spawn_special(SpecialType.FOOD)

    def _free_cell(self) -> tuple[int, int]:
        occupied = set()
        for s in self.snakes:
            occupied.update(s.body)
        for sp in self.specials:
            occupied.add(sp.pos)
        for _ in range(500):
            pos = (random.randint(0, COLS - 1), random.randint(0, ROWS - 1))
            if pos not in occupied:
                return pos
        return (random.randint(0, COLS - 1), random.randint(0, ROWS - 1))

    def _spawn_special(self, kind: SpecialType | None = None):
        if kind is None:
            # Random special (weighted)
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
            for key, d in PLAYER_KEYS[i].items():
                if keys_pressed[key]:
                    snake.update_direction(d)

    def update(self):
        if self.game_over:
            return

        self.tick += 1

        # AI decisions
        for s in self.snakes:
            if s.is_ai and s.alive:
                s.ai_choose_direction(self.specials, self.snakes)

        # Move each snake (handle speed modifiers)
        for s in self.snakes:
            if not s.alive:
                continue
            # Decrement timers
            if s.speed_mod > 0:
                s.speed_mod -= 1
                if s.speed_mod == 0:
                    s.speed_mult = 1.0
            if s.ghost_timer > 0:
                s.ghost_timer -= 1
            if s.magnet_timer > 0:
                s.magnet_timer -= 1

            # Speed handling: fast snakes move every tick, slow snakes skip ticks
            s.tick_accum += s.speed_mult
            if s.tick_accum >= 1.0:
                s.tick_accum -= 1.0
                s.move()
            # If speed > 1, might move twice
            if s.tick_accum >= 1.0:
                s.tick_accum -= 1.0
                s.move()

        # Magnet effect: pull nearby food toward magnet holders
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
                            new_pos = (sp.pos[0] + mx, sp.pos[1] + my)
                            sp.pos = new_pos

        # Check special pickups
        for s in self.snakes:
            if not s.alive:
                continue
            head = s.body[0]
            for sp in self.specials[:]:
                if sp.pos == head:
                    self._apply_special(s, sp)
                    self.specials.remove(sp)

        # Check collisions
        for s in self.snakes:
            if not s.alive:
                continue
            head = s.body[0]

            # Self-collision (skip head)
            if head in list(s.body)[1:]:
                if s.ghost_timer <= 0:
                    if s.shield:
                        s.shield = False
                        s.shrink(3)
                    else:
                        s.alive = False
                        self._emit_particles(head, s.color, 20)
                        continue

            # Collision with others
            for other in self.snakes:
                if other is s or not other.alive:
                    continue
                if head in other.body:
                    if s.ghost_timer > 0:
                        continue
                    if s.shield:
                        s.shield = False
                        # Punish the other snake
                        other.shrink(3)
                    else:
                        s.alive = False
                        self._emit_particles(head, s.color, 20)
                        break

        # Spawn specials periodically
        if self.tick % 40 == 0:
            self._spawn_special()

        # Maintain minimum food count
        food_count = sum(1 for sp in self.specials if sp.kind == SpecialType.FOOD)
        if food_count < 3:
            self._spawn_special(SpecialType.FOOD)

        # Despawn old specials (except food)
        for sp in self.specials[:]:
            if sp.kind != SpecialType.FOOD:
                sp.timer -= 1
                if sp.timer <= 0:
                    self.specials.remove(sp)

        # Update particles
        for p in self.particles[:]:
            p.update()
            if p.life <= 0:
                self.particles.remove(p)

        # Check game over
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
            # Damage nearby snakes
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
        surf.fill(BG)

        # Draw grid
        for x in range(0, WIDTH, CELL):
            pygame.draw.line(surf, GRID_COL, (x, PANEL_H), (x, WIN_H))
        for y in range(PANEL_H, WIN_H, CELL):
            pygame.draw.line(surf, GRID_COL, (0, y), (WIDTH, y))

        # Wall indicator
        if not self.wrap_walls:
            pygame.draw.rect(surf, (180, 40, 40), (0, PANEL_H, WIDTH, HEIGHT), 3)
        else:
            # Dashed border effect for wrap
            for x in range(0, WIDTH, 20):
                pygame.draw.line(surf, (40, 120, 180), (x, PANEL_H), (x + 10, PANEL_H), 2)
                pygame.draw.line(surf, (40, 120, 180), (x, WIN_H - 1), (x + 10, WIN_H - 1), 2)
            for y in range(PANEL_H, WIN_H, 20):
                pygame.draw.line(surf, (40, 120, 180), (0, y), (0, y + 10), 2)
                pygame.draw.line(surf, (40, 120, 180), (WIDTH - 1, y), (WIDTH - 1, y + 10), 2)

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
        pygame.draw.rect(surf, (20, 20, 35), (0, 0, WIDTH, PANEL_H))
        pygame.draw.line(surf, (60, 60, 80), (0, PANEL_H - 1), (WIDTH, PANEL_H - 1))

        panel_w = WIDTH // 4
        for i, s in enumerate(self.snakes):
            x_off = i * panel_w + 10
            # Name
            label = f"{s.name}"
            if s.is_ai:
                label += " [AI]"
            col = s.color if s.alive else DARK_GRAY
            txt = small_font.render(label, True, col)
            surf.blit(txt, (x_off, 6))
            # Score
            score_txt = font.render(str(s.score), True, col)
            surf.blit(score_txt, (x_off, 24))
            # Status icons
            icon_x = x_off + 50
            if s.shield:
                pygame.draw.circle(surf, (180, 180, 255), (icon_x, 34), 6, 2)
                icon_x += 16
            if s.ghost_timer > 0:
                pygame.draw.circle(surf, (180, 255, 220), (icon_x, 34), 6)
                icon_x += 16
            if s.magnet_timer > 0:
                pygame.draw.circle(surf, (255, 160, 60), (icon_x, 34), 6)
                icon_x += 16
            if s.speed_mod > 0:
                c = YELLOW if s.speed_mult > 1 else (100, 100, 255)
                pygame.draw.circle(surf, c, (icon_x, 34), 6)
            if not s.alive:
                dead_txt = small_font.render("DEAD", True, RED)
                surf.blit(dead_txt, (x_off + panel_w - 55, 24))

        # Game over overlay
        if self.game_over:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))
            surf.blit(overlay, (0, PANEL_H))

            if self.winner:
                msg = f"{self.winner.name} WINS!"
                col = self.winner.color
            else:
                msg = "DRAW!"
                col = WHITE
            txt = font.render(msg, True, col)
            surf.blit(txt, txt.get_rect(center=(WIDTH // 2, WIN_H // 2 - 20)))
            restart = small_font.render("Press SPACE to return to menu", True, GRAY)
            surf.blit(restart, restart.get_rect(center=(WIDTH // 2, WIN_H // 2 + 20)))


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
        self.wrap_walls = True
        self.selected = 0  # 0=players, 1=walls, 2=start
        self.options = 3

    def handle_event(self, event) -> str | None:
        """Returns 'start' if game should begin, else None."""
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected - 1) % self.options
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected = (self.selected + 1) % self.options
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                if self.selected == 0:
                    self.num_players = max(1, self.num_players - 1)
                elif self.selected == 1:
                    self.wrap_walls = not self.wrap_walls
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                if self.selected == 0:
                    self.num_players = min(4, self.num_players + 1)
                elif self.selected == 1:
                    self.wrap_walls = not self.wrap_walls
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.selected == 2:
                    return "start"
                elif self.selected == 1:
                    self.wrap_walls = not self.wrap_walls
        return None

    def draw(self):
        self.screen.fill(MENU_BG)

        # Title
        title = self.title_font.render("SNAKE ARENA", True, HIGHLIGHT)
        self.screen.blit(title, title.get_rect(center=(WIN_W // 2, 80)))

        subtitle = self.small_font.render("Up to 4 players  •  AI opponents  •  Power-ups", True, GRAY)
        self.screen.blit(subtitle, subtitle.get_rect(center=(WIN_W // 2, 120)))

        cy = 190
        gap = 60

        # Players
        col = HIGHLIGHT if self.selected == 0 else WHITE
        txt = self.font.render(f"◀  Players: {self.num_players}  ({4 - self.num_players} AI)  ▶", True, col)
        self.screen.blit(txt, txt.get_rect(center=(WIN_W // 2, cy)))

        # Walls
        cy += gap
        col = HIGHLIGHT if self.selected == 1 else WHITE
        mode = "Wrap (traverse)" if self.wrap_walls else "Solid (collide)"
        txt = self.font.render(f"◀  Walls: {mode}  ▶", True, col)
        self.screen.blit(txt, txt.get_rect(center=(WIN_W // 2, cy)))

        # Start
        cy += gap + 20
        col = HIGHLIGHT if self.selected == 2 else WHITE
        txt = self.font.render("[ START GAME ]", True, col)
        self.screen.blit(txt, txt.get_rect(center=(WIN_W // 2, cy)))

        # Controls help
        cy = WIN_H - 160
        controls = [
            ("P1: W/A/S/D", SNAKE_COLORS[0][0]),
            ("P2: Arrow Keys", SNAKE_COLORS[1][0]),
            ("P3: I/J/K/L", SNAKE_COLORS[2][0]),
            ("P4: Numpad 8/4/5/6", SNAKE_COLORS[3][0]),
        ]
        header = self.small_font.render("— Controls —", True, GRAY)
        self.screen.blit(header, header.get_rect(center=(WIN_W // 2, cy - 20)))
        for i, (text, color) in enumerate(controls):
            txt = self.small_font.render(text, True, color)
            self.screen.blit(txt, txt.get_rect(center=(WIN_W // 2, cy + 10 + i * 24)))

        # Specials legend
        legend_y = cy + 115
        legend_header = self.small_font.render("— Power-ups —", True, GRAY)
        self.screen.blit(legend_header, legend_header.get_rect(center=(WIN_W // 2, legend_y)))
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
        col_w = WIN_W // cols_count
        for i, (label, color) in enumerate(items):
            r = i // cols_count
            c = i % cols_count
            x = c * col_w + col_w // 2
            y = legend_y + 22 + r * 22
            t = self.small_font.render(label, True, color)
            self.screen.blit(t, t.get_rect(center=(x, y)))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption("Snake Arena")
    clock = pygame.time.Clock()

    title_font = pygame.font.SysFont("Arial", 48, bold=True)
    font = pygame.font.SysFont("Arial", 24, bold=True)
    small_font = pygame.font.SysFont("Arial", 16)

    menu = Menu(screen, font, small_font, title_font)
    game: Game | None = None
    state = "menu"  # "menu" | "playing"

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if state == "playing":
                    state = "menu"
                    game = None
                else:
                    running = False

            if state == "menu":
                result = menu.handle_event(event)
                if result == "start":
                    game = Game(menu.num_players, menu.wrap_walls)
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
