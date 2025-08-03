import pygame
import serial
import time
import threading
import serial.tools.list_ports as serial_ports
from serial import Serial, SerialException
from collections import deque
import binascii

# Constants
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 700
FPS = 30

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (100, 100, 100)
BLUE = (0, 0, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
YELLOW = (255, 255, 0)
PURPLE = (128, 0, 128)
CYAN = (0, 255, 255)
ORANGE = (255, 165, 0)

class MindWaveProcessor:
    def __init__(self, port='COM9', baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.running = False
        self.data_callback = None
        self.blink_timestamps = []
        self.last_blink_type = None
        self.last_data = None
        self.brain_data_buffer = {
            'delta': deque(maxlen=100),
            'theta': deque(maxlen=100),
            'low_alpha': deque(maxlen=100),
            'high_alpha': deque(maxlen=100),
            'raw': deque(maxlen=100),
            'attention': deque(maxlen=100),
            'meditation': deque(maxlen=100),
        }

    def connect(self):
        try:
            self.serial_conn = Serial(self.port, self.baudrate, timeout=1)
            self.running = True
            print(f"Connected to MindWave on {self.port}.")
            threading.Thread(target=self.read_data, daemon=True).start()
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    def find_packet_start(self):
        """Search for the packet start sequence (0xAA, 0xAA)"""
        first_aa = False
        
        while self.running:
            if self.serial_conn.in_waiting > 0:
                byte = self.serial_conn.read(1)[0]
                if byte == 0xAA and not first_aa:
                    first_aa = True
                elif byte == 0xAA and first_aa:
                    # Found start sequence
                    return True
                else:
                    first_aa = False
            else:
                time.sleep(0.1)  # Wait for more data
                return False
        
        return False

    def read_data(self):
        buffer = bytearray()
        
        while self.running:
            try:
                # Look for packet start sequence
                if self.find_packet_start():
                    # Found packet start (0xAA, 0xAA)
                    buffer = bytearray([0xAA, 0xAA])
                    
                    # Read length byte
                    if self.serial_conn.in_waiting > 0:
                        length_byte = self.serial_conn.read(1)[0]
                        buffer.append(length_byte)
                        
                        # Read the rest of the packet based on length
                        if length_byte > 0 and length_byte <= 0x20:  # Reasonable length check
                            remaining = length_byte + 1  # +1 for checksum
                            if self.serial_conn.in_waiting >= remaining:
                                buffer.extend(self.serial_conn.read(remaining))
                                
                                # Process complete packet
                                data = self.parse_mindwave_packet(bytes(buffer))
                                if data:
                                    self.last_data = data
                                    
                                    # Process blink if detected
                                    if data['blink_strength'] > 0:
                                        self.process_blink(data['blink_strength'], data['raw'])
                                    
                                    # Update data buffers
                                    for key in self.brain_data_buffer:
                                        if key in data:
                                            self.brain_data_buffer[key].append(data[key])
                                    
                                    # Call the callback if it exists
                                    if self.data_callback:
                                        self.data_callback(data, self.last_blink_type)
                
                # If not enough data, wait a bit
                if self.serial_conn.in_waiting < 3:
                    time.sleep(0.05)
                
            except Exception as e:
                print(f"Read error: {e}")

    def process_blink(self, strength, raw_value):
        """Process blink and determine if it's left, right, or both eyes"""
        current_time = time.time()
        blink_window_seconds = 0.75 # Shorter window for double blink detection
        
        # Clean old timestamps
        self.blink_timestamps = [t for t in self.blink_timestamps if current_time - t < blink_window_seconds]
        
        # Add current timestamp
        self.blink_timestamps.append(current_time)
        
        # Log the raw value received for this blink event
        print(f"Blink event: Strength={strength}, Raw={raw_value}, Timestamps_in_window={len(self.blink_timestamps)}")

        # Determine blink type
        # Check for rapid double blink first (>= 2 blinks within the window)
        if len(self.blink_timestamps) >= 2:
            self.last_blink_type = "Both Eyes Blink"
            print(f"--> Classified as: Both Eyes Blink (rapid succession)")
            # Clear timestamps after detecting two blinks close together
            self.blink_timestamps.clear()
        else:
            # Single blink detected recently - classify based on raw value
            # Heuristic: Negative raw value might indicate left, positive might indicate right
            if raw_value < 0: 
                self.last_blink_type = "Left Eye Blink"
                print(f"--> Classified as: Left Eye Blink (raw < 0)")
            else: # Includes raw_value >= 0
                self.last_blink_type = "Right Eye Blink"
                print(f"--> Classified as: Right Eye Blink (raw >= 0)")
            # Don't clear timestamp yet, wait to see if a second blink follows quickly

        # Note: Callback is called later in read_data with the determined self.last_blink_type

    def parse_mindwave_packet(self, packet):
        """Parse a MindWave packet and extract data"""
        if len(packet) < 32:
            return None  # Ignore short packets

        if packet[0] == 0xAA and packet[1] == 0xAA:  # Start bytes
            payload_length = packet[2]  # Length of data
            
            if payload_length == 0x20:  # Expected length
                checksum = packet[-1]
                payload = packet[3:-1]  # Extract payload

                # Compute checksum
                computed_checksum = (~sum(payload) & 0xFF)

                if computed_checksum == checksum:  # Verify checksum
                    # Extract more detailed data
                    signal_quality = payload[1]
                    
                    # Extract EEG power bands if available
                    delta = int.from_bytes(payload[4:6], byteorder='big') if len(payload) > 5 else 0
                    theta = int.from_bytes(payload[6:8], byteorder='big') if len(payload) > 7 else 0
                    low_alpha = int.from_bytes(payload[8:10], byteorder='big') if len(payload) > 9 else 0
                    high_alpha = int.from_bytes(payload[10:12], byteorder='big') if len(payload) > 11 else 0
                    high_beta = int.from_bytes(payload[12:14], byteorder='big') if len(payload) > 13 else 0
                    low_beta = int.from_bytes(payload[14:16], byteorder='big') if len(payload) > 15 else 0
                    gamma1 = int.from_bytes(payload[16:18], byteorder='big') if len(payload) > 17 else 0
                    gamma2 = int.from_bytes(payload[18:20], byteorder='big') if len(payload) > 19 else 0
                    
                    attention = payload[29] if len(payload) > 29 else 0
                    meditation = payload[31] if len(payload) > 31 else 0
                    
                    # Extract blink data (usually encoded at a specific position)
                    blink_strength = 0
                    
                    # Scan through payload for blink data
                    for i in range(len(payload) - 2):
                        if payload[i] == 0x16:  # Assuming 0x16 is the blink marker
                            blink_strength = payload[i + 1]
                            break
                    
                    # Get raw value for blink side detection
                    raw = 0
                    for i in range(len(payload) - 2):
                        if payload[i] == 0x80:  # Raw value marker
                            raw = int.from_bytes(payload[i+1:i+3], byteorder='big', signed=True)
                            if raw > 32768:  # Convert to signed 16-bit
                                raw -= 65536
                            break
                    
                    return {
                        'signal_quality': signal_quality,
                        'attention': attention,
                        'meditation': meditation,
                        'delta': delta,
                        'theta': theta,
                        'low_alpha': low_alpha,
                        'high_alpha': high_alpha,
                        'low_beta': low_beta,
                        'high_beta': high_beta,
                        'gamma1': gamma1,
                        'gamma2': gamma2,
                        'blink_strength': blink_strength,
                        'raw': raw
                    }

        return None

    def disconnect(self):
        self.running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        print("Disconnected from MindWave.")

class MindWaveUI:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("MindWave Brain Visualization")
        self.clock = pygame.time.Clock()
        
        # Fonts
        self.font_large = pygame.font.SysFont('Arial', 36, bold=True)
        self.font_medium = pygame.font.SysFont('Arial', 24)
        self.font_small = pygame.font.SysFont('Arial', 18)
        
        # MindWave processor
        self.processor = MindWaveProcessor()
        self.processor.data_callback = self.update_data
        
        # State variables
        self.running = True
        self.connected = False
        self.last_blink_type = None
        self.last_blink_time = 0
        self.current_data = None
        
        # For visualization of brain wave data
        self.graph_data = {
            'delta': deque(maxlen=100),
            'theta': deque(maxlen=100),
            'low_alpha': deque(maxlen=100),
            'high_alpha': deque(maxlen=100),
            'attention': deque(maxlen=100),
            'meditation': deque(maxlen=100),
        }
        
        # Wave colors
        self.wave_colors = {
            'delta': BLUE,
            'theta': GREEN,
            'low_alpha': YELLOW,
            'high_alpha': RED,
            'attention': PURPLE,
            'meditation': CYAN,
        }
        
        # Eye blink animation
        self.left_eye_open = True
        self.right_eye_open = True
        self.blink_duration = 0.3  # seconds
        self.attention_level = 0
        self.meditation_level = 0
        
        # Try to connect automatically
        self.connect()

    def connect(self):
        """Connect to MindWave device"""
        self.connected = self.processor.connect()
        return self.connected

    def update_data(self, data, blink_type):
        """Callback function to handle new data from MindWave"""
        self.current_data = data
        
        # Update brain wave data for visualization
        for key in self.graph_data:
            if key in data:
                self.graph_data[key].append(data[key])
        
        # Update attention and meditation levels
        self.attention_level = data.get('attention', 0)
        self.meditation_level = data.get('meditation', 0)
        
        # Handle blink detection
        if blink_type:
            self.last_blink_type = blink_type
            self.last_blink_time = time.time()
            
            # Trigger eye blink animation
            if "Left" in blink_type:
                self.left_eye_open = False
            elif "Right" in blink_type:
                self.right_eye_open = False
            elif "Both" in blink_type:
                self.left_eye_open = False
                self.right_eye_open = False

    def draw_face(self):
        """Draw face with blinking eyes"""
        # Face position and size
        face_x = WINDOW_WIDTH // 2
        face_y = 200
        face_radius = 100
        
        # Draw face circle
        pygame.draw.circle(self.screen, WHITE, (face_x, face_y), face_radius, 3)
        
        # Eye positions
        eye_radius = 15
        left_eye_x = face_x - 40
        right_eye_x = face_x + 40
        eyes_y = face_y - 30
        
        # Check if eyes should be reset to open
        current_time = time.time()
        if not self.left_eye_open and current_time - self.last_blink_time > self.blink_duration:
            self.left_eye_open = True
        if not self.right_eye_open and current_time - self.last_blink_time > self.blink_duration:
            self.right_eye_open = True
        
        # Draw eyes based on blink state
        pygame.draw.circle(self.screen, WHITE if self.left_eye_open else BLACK, (left_eye_x, eyes_y), eye_radius)
        pygame.draw.circle(self.screen, WHITE if self.right_eye_open else BLACK, (right_eye_x, eyes_y), eye_radius)
        
        # Draw mouth (smile or neutral based on attention level)
        mouth_y = face_y + 40
        if self.attention_level > 50:
            # Happy mouth for high attention
            pygame.draw.arc(self.screen, WHITE, 
                         (face_x - 30, mouth_y - 10, 60, 30), 
                         0, 3.14, 2)
        else:
            # Neutral mouth for low attention
            pygame.draw.line(self.screen, WHITE, 
                         (face_x - 20, mouth_y), 
                         (face_x + 20, mouth_y), 2)
        
        # Draw labels
        left_label = self.font_small.render("Left Eye", True, WHITE)
        right_label = self.font_small.render("Right Eye", True, WHITE)
        self.screen.blit(left_label, (left_eye_x - left_label.get_width() // 2, eyes_y - 35))
        self.screen.blit(right_label, (right_eye_x - right_label.get_width() // 2, eyes_y - 35))
        
        # Draw last blink indicator if applicable
        if self.last_blink_type and current_time - self.last_blink_time < 2.0:
            blink_text = self.font_medium.render(f"Last Blink: {self.last_blink_type}", True, YELLOW)
            self.screen.blit(blink_text, (WINDOW_WIDTH // 2 - blink_text.get_width() // 2, face_y + 80))

    def draw_brain_wave_graphs(self):
        """Draw graphs for brain wave data"""
        if not self.current_data:
            return
            
        # Graph area
        graph_x = 50
        graph_y = 350
        graph_width = WINDOW_WIDTH - 100
        graph_height = 200
        
        # Draw graph background
        pygame.draw.rect(self.screen, GRAY, (graph_x, graph_y, graph_width, graph_height), 1)
        
        # Draw title
        title = self.font_medium.render("Brain Wave Patterns", True, ORANGE)
        self.screen.blit(title, (WINDOW_WIDTH // 2 - title.get_width() // 2, graph_y - 40))
        
        # Draw graphs for each brain wave
        for i, (wave_type, values) in enumerate(self.graph_data.items()):
            if values:
                # Draw wave name and current value
                name_text = self.font_small.render(f"{wave_type}: {values[-1] if values else 0}", True, self.wave_colors[wave_type])
                self.screen.blit(name_text, (graph_x, graph_y + graph_height + 10 + i * 20))
                
                # Draw wave graph
                if len(values) > 1:
                    points = []
                    max_val = max(max(values), 1)  # Avoid division by zero
                    
                    for j, val in enumerate(values):
                        x = graph_x + (j * graph_width) // len(values)
                        y = graph_y + graph_height - (val * graph_height) // max_val
                        points.append((x, y))
                    
                    if len(points) > 1:
                        pygame.draw.lines(self.screen, self.wave_colors[wave_type], False, points, 2)

    def draw_metrics(self):
        """Draw brain metrics"""
        if not self.current_data:
            # Use default values if no data
            signal_quality = 30
            attention = self.attention_level
            meditation = self.meditation_level
        else:
            signal_quality = self.current_data.get('signal_quality', 30)
            attention = self.current_data.get('attention', 0)
            meditation = self.current_data.get('meditation', 0)
        
        # Draw metrics at the top of the screen
        metrics_x = 20
        metrics_y = 20
        
        title = self.font_large.render("Brain Metrics", True, WHITE)
        self.screen.blit(title, (WINDOW_WIDTH // 2 - title.get_width() // 2, metrics_y))
        
        # Signal quality
        quality_color = GREEN if signal_quality < 50 else (YELLOW if signal_quality < 100 else RED)
        quality_text = self.font_medium.render(f"Signal Quality: {signal_quality}", True, quality_color)
        self.screen.blit(quality_text, (metrics_x, metrics_y + 40))
        
        # Attention and meditation
        attention_text = self.font_medium.render(f"Attention: {attention}", True, PURPLE)
        meditation_text = self.font_medium.render(f"Meditation: {meditation}", True, CYAN)
        
        self.screen.blit(attention_text, (metrics_x, metrics_y + 70))
        self.screen.blit(meditation_text, (metrics_x + 200, metrics_y + 70))

    def run(self):
        """Main loop"""
        while self.running:
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q:
                        self.running = False
                    elif event.key == pygame.K_c:
                        self.connect()
            
            # Clear screen
            self.screen.fill(BLACK)
            
            if not self.connected:
                # Show connection instructions
                text = self.font_large.render("Not connected to MindWave", True, RED)
                self.screen.blit(text, (WINDOW_WIDTH // 2 - text.get_width() // 2, WINDOW_HEIGHT // 2 - 30))
                
                text2 = self.font_medium.render("Press 'C' to connect or 'Q' to quit", True, WHITE)
                self.screen.blit(text2, (WINDOW_WIDTH // 2 - text2.get_width() // 2, WINDOW_HEIGHT // 2 + 30))
            else:
                # Draw interface components
                self.draw_face()
                self.draw_metrics()
                self.draw_brain_wave_graphs()
                
                # Draw controls
                controls = self.font_small.render("Press 'Q' to quit", True, WHITE)
                self.screen.blit(controls, (WINDOW_WIDTH - controls.get_width() - 20, WINDOW_HEIGHT - 30))
            
            # Update display
            pygame.display.flip()
            self.clock.tick(FPS)
        
        # Clean up
        self.processor.disconnect()
        pygame.quit()

if __name__ == "__main__":
    # List available serial ports
    ports = list(serial_ports.comports())
    print("Available serial ports:")
    for i, port in enumerate(ports):
        print(f"{i+1}. {port.device} - {port.description}")
    
    # Create and run the UI
    ui = MindWaveUI()
    ui.run() 