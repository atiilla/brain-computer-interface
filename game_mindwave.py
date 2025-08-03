import pygame
import sys
import random
import time
from mindwave import parse_mindwave_packet, find_packet_start
import serial.tools.list_ports as serial_ports
from serial import Serial, SerialException

# Initialize pygame
pygame.init()

# Game constants
WIDTH, HEIGHT = 800, 600
PLAYER_SIZE = 40
PLATFORM_HEIGHT = 20
COIN_SIZE = 30
GRAVITY = 0.5
JUMP_STRENGTH = 12
FPS = 60

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
BROWN = (139, 69, 19)
SKYBLUE = (135, 206, 235)

# MindWave settings
SERIAL_PORT = "COM9"  # Change this to match your MindWave device
BAUD_RATE = 9600

class Player:
    def __init__(self):
        self.x = 100
        self.y = HEIGHT - 100
        self.width = PLAYER_SIZE
        self.height = PLAYER_SIZE
        self.speed_x = 0
        self.speed_y = 0
        self.on_ground = False
        self.jump_cooldown = 0
        self.color = RED
        
    def update(self, attention, meditation, platforms):
        # Attention affects horizontal movement (0-100)
        # Meditation affects jumping when high enough
        
        # Convert attention to horizontal speed (-5 to 5)
        self.speed_x = (attention - 50) / 10
        
        # Apply gravity
        self.speed_y += GRAVITY
        
        # Apply jump based on meditation and cooldown
        if meditation > 70 and self.on_ground and self.jump_cooldown <= 0:
            self.speed_y = -JUMP_STRENGTH
            self.on_ground = False
            self.jump_cooldown = 30  # Set cooldown to prevent multiple jumps
        
        if self.jump_cooldown > 0:
            self.jump_cooldown -= 1
        
        # Update position
        self.x += self.speed_x
        self.y += self.speed_y
        
        # Keep player within horizontal screen bounds
        self.x = max(0, min(self.x, WIDTH - self.width))
        
        # Check for platform collisions
        self.on_ground = False
        for platform in platforms:
            if (self.y + self.height >= platform.y and 
                self.y + self.height <= platform.y + 10 and
                self.x + self.width > platform.x and 
                self.x < platform.x + platform.width):
                self.on_ground = True
                self.y = platform.y - self.height
                self.speed_y = 0
        
        # Bottom screen boundary (death)
        if self.y > HEIGHT:
            return "game_over"
            
        # Change color based on state
        if self.on_ground:
            if meditation > 70:  # Ready to jump
                self.color = GREEN
            else:
                self.color = RED
        else:
            self.color = BLUE  # Jumping
        
        return "playing"
    
    def draw(self, screen):
        pygame.draw.rect(screen, self.color, (int(self.x), int(self.y), self.width, self.height))
        
        # Draw face
        eye_size = 5
        pygame.draw.circle(screen, WHITE, (int(self.x) + 10, int(self.y) + 10), eye_size)
        pygame.draw.circle(screen, WHITE, (int(self.x) + 30, int(self.y) + 10), eye_size)
        
        # Draw mouth based on state
        if self.on_ground:
            # Smile
            pygame.draw.arc(screen, WHITE, 
                          (int(self.x) + 10, int(self.y) + 20, 20, 10), 
                          3.14, 2*3.14, 2)
        else:
            # Open mouth
            pygame.draw.circle(screen, BLACK, (int(self.x) + 20, int(self.y) + 25), 5)

class Platform:
    def __init__(self, x, y, width):
        self.x = x
        self.y = y
        self.width = width
        self.height = PLATFORM_HEIGHT
        self.color = BROWN
        
    def draw(self, screen):
        pygame.draw.rect(screen, self.color, (self.x, self.y, self.width, self.height))
        
        # Draw brick pattern
        for i in range(0, self.width, 20):
            pygame.draw.line(screen, BLACK, (self.x + i, self.y), (self.x + i, self.y + self.height), 1)
        pygame.draw.line(screen, BLACK, (self.x, self.y + self.height // 2), 
                        (self.x + self.width, self.y + self.height // 2), 1)

class Coin:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.size = COIN_SIZE
        self.collected = False
        self.color = YELLOW
        
    def draw(self, screen):
        if not self.collected:
            pygame.draw.circle(screen, self.color, (int(self.x), int(self.y)), self.size // 2)
            # Draw dollar sign
            font = pygame.font.SysFont(None, 24)
            text = font.render("$", True, BLACK)
            screen.blit(text, (self.x - 5, self.y - 8))
    
    def check_collection(self, player):
        if not self.collected:
            # Check if player rectangle overlaps with coin circle
            player_rect = pygame.Rect(player.x, player.y, player.width, player.height)
            distance = ((player.x + player.width/2 - self.x)**2 + 
                        (player.y + player.height/2 - self.y)**2)**0.5
            
            if distance < player.width/2 + self.size/2:
                self.collected = True
                return True
        return False

def draw_metrics(screen, attention, meditation, signal_quality):
    font = pygame.font.SysFont(None, 36)
    
    # Draw attention meter (affects movement)
    pygame.draw.rect(screen, WHITE, (20, 20, 200, 30), 2)
    pygame.draw.rect(screen, RED, (22, 22, attention * 1.96, 26))
    attention_text = font.render(f"Movement: {attention}", True, WHITE)
    screen.blit(attention_text, (230, 20))
    
    # Draw meditation meter (affects jumping)
    pygame.draw.rect(screen, WHITE, (20, 60, 200, 30), 2)
    pygame.draw.rect(screen, BLUE, (22, 62, meditation * 1.96, 26))
    meditation_text = font.render(f"Jump Power: {meditation}", True, WHITE)
    screen.blit(meditation_text, (230, 60))
    
    # Signal quality indicator
    quality_text = "Signal: "
    if signal_quality < 50:
        quality_text += "Good"
        quality_color = GREEN
    elif signal_quality < 100:
        quality_text += "Fair"
        quality_color = YELLOW
    else:
        quality_text += "Poor"
        quality_color = RED
    
    quality_surface = font.render(quality_text, True, quality_color)
    screen.blit(quality_surface, (20, 100))

def display_instructions(screen):
    font = pygame.font.SysFont(None, 36)
    font_small = pygame.font.SysFont(None, 24)
    
    title = font.render("Mind Control Platform Game", True, WHITE)
    instr1 = font_small.render("Focus (attention) to move left/right", True, WHITE)
    instr2 = font_small.render("Meditate deeply (70+) to jump", True, WHITE)
    instr3 = font_small.render("Collect coins and reach the end of each level", True, WHITE)
    instr4 = font_small.render("Don't fall off the platforms!", True, WHITE)
    instr5 = font_small.render("Press SPACE to start", True, WHITE)
    
    screen.blit(title, (WIDTH//2 - title.get_width()//2, HEIGHT//3))
    screen.blit(instr1, (WIDTH//2 - instr1.get_width()//2, HEIGHT//3 + 50))
    screen.blit(instr2, (WIDTH//2 - instr2.get_width()//2, HEIGHT//3 + 80))
    screen.blit(instr3, (WIDTH//2 - instr3.get_width()//2, HEIGHT//3 + 110))
    screen.blit(instr4, (WIDTH//2 - instr4.get_width()//2, HEIGHT//3 + 140))
    screen.blit(instr5, (WIDTH//2 - instr5.get_width()//2, HEIGHT//3 + 190))

def display_game_over(screen, score, win=False):
    font = pygame.font.SysFont(None, 64)
    font_small = pygame.font.SysFont(None, 36)
    
    if win:
        title = font.render("Level Complete!", True, GREEN)
    else:
        title = font.render("Game Over", True, RED)
    
    score_text = font_small.render(f"Coins: {score}", True, WHITE)
    restart_text = font_small.render("Press SPACE to play again", True, WHITE)
    
    screen.blit(title, (WIDTH//2 - title.get_width()//2, HEIGHT//3))
    screen.blit(score_text, (WIDTH//2 - score_text.get_width()//2, HEIGHT//3 + 80))
    screen.blit(restart_text, (WIDTH//2 - restart_text.get_width()//2, HEIGHT//3 + 140))

def create_level(level_num):
    platforms = []
    coins = []
    
    if level_num == 1:
        # Starting platform
        platforms.append(Platform(0, HEIGHT - 50, 200))
        
        # Middle platforms
        platforms.append(Platform(250, HEIGHT - 120, 100))
        platforms.append(Platform(400, HEIGHT - 180, 100))
        platforms.append(Platform(550, HEIGHT - 120, 100))
        
        # End platform
        platforms.append(Platform(700, HEIGHT - 50, 100))
        
        # Add coins
        coins.append(Coin(300, HEIGHT - 150))
        coins.append(Coin(450, HEIGHT - 210))
        coins.append(Coin(600, HEIGHT - 150))
        coins.append(Coin(750, HEIGHT - 80))
        
    elif level_num == 2:
        # Starting platform
        platforms.append(Platform(0, HEIGHT - 50, 150))
        
        # Middle platforms (more challenging)
        platforms.append(Platform(200, HEIGHT - 120, 80))
        platforms.append(Platform(350, HEIGHT - 200, 80))
        platforms.append(Platform(500, HEIGHT - 280, 80))
        platforms.append(Platform(650, HEIGHT - 200, 80))
        
        # End platform
        platforms.append(Platform(700, HEIGHT - 100, 100))
        
        # Add coins
        coins.append(Coin(230, HEIGHT - 150))
        coins.append(Coin(390, HEIGHT - 230))
        coins.append(Coin(540, HEIGHT - 310))
        coins.append(Coin(750, HEIGHT - 130))
        
    elif level_num >= 3:
        # Starting platform
        platforms.append(Platform(0, HEIGHT - 50, 100))
        
        # Generate some random platforms for variety
        platform_y = HEIGHT - 100
        for i in range(8):
            platform_x = 150 + i * 80 + random.randint(-20, 20)
            platform_width = random.randint(60, 100)
            platform_y -= random.randint(0, 60)
            platform_y = max(HEIGHT - 350, min(platform_y, HEIGHT - 50))
            
            platforms.append(Platform(platform_x, platform_y, platform_width))
            
            # Add a coin above each platform
            coins.append(Coin(platform_x + platform_width//2, platform_y - 30))
    
    return platforms, coins

def simulate_mindwave_data():
    """Simulates MindWave data for testing without the actual device."""
    return {
        'signal_quality': random.randint(0, 200),
        'attention': random.randint(40, 60),  # More centered around neutral
        'meditation': random.randint(30, 70),  # Jump occasionally
        'delta': 0,
        'theta': 0,
        'low_alpha': 0,
        'high_alpha': 0,
        'blink_strength': 0,
        'raw': 0
    }

def main():
    # Setup pygame window
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("MindWave Platform Game")
    clock = pygame.time.Clock()
    
    # Game state
    game_state = "instructions"  # Can be "instructions", "playing", "game_over", "level_complete"
    score = 0
    level = 1
    
    # Game objects
    player = Player()
    platforms, coins = create_level(level)
    
    # Background elements
    background_color = SKYBLUE
    cloud_positions = [(random.randint(0, WIDTH), random.randint(50, 150)) for _ in range(5)]
    
    # MindWave data (default values)
    mindwave_data = {
        'signal_quality': 0,
        'attention': 50,
        'meditation': 50,
        'delta': 0,
        'theta': 0,
        'low_alpha': 0,
        'high_alpha': 0,
        'blink_strength': 0,
        'raw': 0
    }
    
    # Try to connect to MindWave device
    use_real_device = True
    try:
        ser = Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"Connected to MindWave device on {SERIAL_PORT}")
        buffer = bytearray()
    except SerialException as e:
        print(f"Error connecting to MindWave: {e}")
        print("Falling back to simulated data")
        use_real_device = False
    
    # Main game loop
    running = True
    while running:
        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    if game_state in ["instructions", "game_over", "level_complete"]:
                        game_state = "playing"
                        if game_state == "game_over":
                            level = 1  # Reset to level 1 after game over
                        player = Player()
                        platforms, coins = create_level(level)
                        score = 0
                        
                # Debug controls
                if event.key == pygame.K_UP:
                    mindwave_data['meditation'] = min(100, mindwave_data['meditation'] + 15)
                if event.key == pygame.K_DOWN:
                    mindwave_data['meditation'] = max(0, mindwave_data['meditation'] - 15)
                if event.key == pygame.K_RIGHT:
                    mindwave_data['attention'] = min(100, mindwave_data['attention'] + 15)
                if event.key == pygame.K_LEFT:
                    mindwave_data['attention'] = max(0, mindwave_data['attention'] - 15)
        
        # Get MindWave data
        if use_real_device:
            if find_packet_start(ser):
                buffer = bytearray([0xAA, 0xAA])
                
                if ser.in_waiting > 0:
                    length_byte = ser.read(1)[0]
                    buffer.append(length_byte)
                    
                    if length_byte > 0 and length_byte <= 0x20:
                        remaining = length_byte + 1
                        if ser.in_waiting >= remaining:
                            buffer.extend(ser.read(remaining))
                            
                            data = parse_mindwave_packet(bytes(buffer))
                            if data:
                                mindwave_data = data
        else:
            # Use simulated data
            if random.random() < 0.05:  # Only update occasionally to avoid rapid changes
                mindwave_data = simulate_mindwave_data()
        
        # Clear screen
        screen.fill(background_color)
        
        # Draw background elements
        for cloud_pos in cloud_positions:
            # Draw cloud
            pygame.draw.circle(screen, WHITE, (cloud_pos[0], cloud_pos[1]), 20)
            pygame.draw.circle(screen, WHITE, (cloud_pos[0] + 15, cloud_pos[1] - 10), 15)
            pygame.draw.circle(screen, WHITE, (cloud_pos[0] + 15, cloud_pos[1] + 10), 15)
            pygame.draw.circle(screen, WHITE, (cloud_pos[0] + 30, cloud_pos[1]), 20)
        
        # State-specific updates
        if game_state == "instructions":
            display_instructions(screen)
        
        elif game_state == "playing":
            # Update player based on MindWave data
            game_state = player.update(mindwave_data['attention'], mindwave_data['meditation'], platforms)
            
            # Check for coin collection
            coins_collected = 0
            for coin in coins:
                if coin.check_collection(player):
                    score += 1
            
            # Check if all coins collected (level complete)
            if all(coin.collected for coin in coins):
                game_state = "level_complete"
            
            # Draw game elements
            for platform in platforms:
                platform.draw(screen)
            
            for coin in coins:
                coin.draw(screen)
            
            player.draw(screen)
            
            # Draw game stats
            draw_metrics(screen, mindwave_data['attention'], mindwave_data['meditation'], mindwave_data['signal_quality'])
            
            # Score and level
            font = pygame.font.SysFont(None, 36)
            score_text = font.render(f"Coins: {score}", True, WHITE)
            level_text = font.render(f"Level: {level}", True, WHITE)
            screen.blit(score_text, (WIDTH - 150, 20))
            screen.blit(level_text, (WIDTH - 150, 60))
        
        elif game_state == "game_over":
            display_game_over(screen, score)
        
        elif game_state == "level_complete":
            display_game_over(screen, score, win=True)
            level += 1
            if level > 3:
                level = 1  # Loop back to level 1 after completing all levels
        
        # Update display
        pygame.display.flip()
        clock.tick(FPS)
    
    # Clean up
    if use_real_device and 'ser' in locals() and ser.is_open:
        ser.close()
    
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
