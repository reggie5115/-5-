import pygame
import random
import sys
from enum import Enum

# 김지우

# Initialize Pygame
pygame.init()

# Constants
WINDOW_WIDTH = 400
WINDOW_HEIGHT = 600
GRID_SIZE = 4
BLOCK_SIZE = WINDOW_WIDTH // GRID_SIZE
FPS = 60

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (128, 128, 128)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
CYAN = (0, 255, 255)
MAGENTA = (255, 0, 255)

COLORS = [RED, GREEN, BLUE, YELLOW, CYAN, MAGENTA]


class Block:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.color = color
        self.rect = pygame.Rect(x * BLOCK_SIZE, y * BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE)

    def draw(self, surface):
        pygame.draw.rect(surface, self.color, self.rect)
        pygame.draw.rect(surface, WHITE, self.rect, 2)

    def contains_point(self, pos):
        return self.rect.collidepoint(pos)


class Grid:
    def __init__(self):
        self.blocks = [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.selected_blocks = set()

    def add_block(self, x, y, color):
        if 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE and self.blocks[y][x] is None:
            self.blocks[y][x] = Block(x, y, color)
            return True
        return False

    def get_block_at(self, x, y):
        if 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE:
            return self.blocks[y][x]
        return None

    def select_connected_blocks(self, x, y):
        """Select all connected blocks of the same color using BFS"""
        self.selected_blocks.clear()
        block = self.get_block_at(x, y)
        if block is None:
            return

        color = block.color
        queue = [(x, y)]
        visited = set()

        while queue:
            cx, cy = queue.pop(0)
            if (cx, cy) in visited:
                continue
            visited.add((cx, cy))

            current = self.get_block_at(cx, cy)
            if current and current.color == color:
                self.selected_blocks.add((cx, cy))
                # Check adjacent cells
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    nx, ny = cx + dx, cy + dy
                    if (nx, ny) not in visited and 0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE:
                        queue.append((nx, ny))

    def remove_selected_blocks(self):
        """Remove selected blocks and return points"""
        if len(self.selected_blocks) < 2:
            self.selected_blocks.clear()
            return 0

        points = len(self.selected_blocks) * 10
        for x, y in self.selected_blocks:
            self.blocks[y][x] = None
        self.selected_blocks.clear()

        # Apply gravity
        self.apply_gravity()
        return points

    def apply_gravity(self):
        """Make blocks fall down"""
        for x in range(GRID_SIZE):
            # Collect non-empty blocks in this column
            non_empty = []
            for y in range(GRID_SIZE):
                if self.blocks[y][x] is not None:
                    non_empty.append(self.blocks[y][x])

            # Clear column
            for y in range(GRID_SIZE):
                self.blocks[y][x] = None

            # Redistribute blocks from bottom
            for i, block in enumerate(non_empty):
                block.x = x
                block.y = GRID_SIZE - len(non_empty) + i
                self.blocks[block.y][x] = block

    def draw(self, surface):
        # Draw grid background
        pygame.draw.rect(surface, GRAY, (0, 0, WINDOW_WIDTH, WINDOW_HEIGHT), 2)

        # Draw grid lines
        for i in range(GRID_SIZE + 1):
            pygame.draw.line(surface, GRAY, (i * BLOCK_SIZE, 0), (i * BLOCK_SIZE, WINDOW_HEIGHT))
            pygame.draw.line(surface, GRAY, (0, i * BLOCK_SIZE), (WINDOW_WIDTH, i * BLOCK_SIZE))

        # Draw blocks
        for row in self.blocks:
            for block in row:
                if block:
                    block.draw(surface)

        # Highlight selected blocks
        for x, y in self.selected_blocks:
            rect = pygame.Rect(x * BLOCK_SIZE, y * BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE)
            pygame.draw.rect(surface, WHITE, rect, 4)

    def is_empty(self):
        """Check if grid is completely empty"""
        for row in self.blocks:
            for block in row:
                if block is not None:
                    return False
        return True


class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Block Blast")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        self.grid = Grid()
        self.score = 0
        self.game_over = False
        self.spawn_initial_blocks()

    def spawn_initial_blocks(self):
        """Spawn random blocks on the grid"""
        for _ in range(15):
            x = random.randint(0, GRID_SIZE - 1)
            y = random.randint(0, GRID_SIZE - 1)
            color = random.choice(COLORS)
            self.grid.add_block(x, y, color)

    def spawn_new_blocks(self):
        """Spawn a few new blocks"""
        for _ in range(3):
            x = random.randint(0, GRID_SIZE - 1)
            y = random.randint(0, GRID_SIZE - 1)
            if self.grid.get_block_at(x, y) is None:
                color = random.choice(COLORS)
                self.grid.add_block(x, y, color)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.MOUSEBUTTONDOWN:
                pos = pygame.mouse.get_pos()
                x = pos[0] // BLOCK_SIZE
                y = pos[1] // BLOCK_SIZE
                self.grid.select_connected_blocks(x, y)

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    points = self.grid.remove_selected_blocks()
                    self.score += points
                    if self.grid.is_empty():
                        self.game_over = True
                elif event.key == pygame.K_r:
                    self.__init__()

        return True

    def draw(self):
        self.screen.fill(BLACK)
        self.grid.draw(self.screen)

        # Draw score
        score_text = self.font.render(f"Score: {self.score}", True, WHITE)
        self.screen.blit(score_text, (10, 10))

        # Draw instructions
        small_font = pygame.font.Font(None, 24)
        instructions = [
            "Click to select connected blocks",
            "Space to remove | R to restart",
        ]
        for i, text in enumerate(instructions):
            instr_text = small_font.render(text, True, GRAY)
            self.screen.blit(instr_text, (10, WINDOW_HEIGHT - 60 + i * 25))

        # Draw game over message
        if self.game_over:
            game_over_text = self.font.render("Grid Cleared! Press R to restart", True, GREEN)
            text_rect = game_over_text.get_rect(center=(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2))
            self.screen.blit(game_over_text, text_rect)

        pygame.display.flip()

    def run(self):
        running = True
        while running:
            running = self.handle_events()
            self.draw()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    game = Game()
    game.run()
