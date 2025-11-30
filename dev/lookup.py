import time
import threading
from adafruit_servokit import ServoKit
import board
import busio

# Shared I2C bus
i2c = busio.I2C(board.SCL, board.SDA)

# Set channels to the number of servo channels on your kit.
# 8 for FeatherWing, 16 for Shield/HAT/Bonnet.
kit1 = ServoKit(channels=16, i2c=i2c, address=0x40)
kit2 = ServoKit(channels=16, i2c=i2c, address=0x41)

# Enable PCA9685 mapping depending on driver number calculated
driver_kits = {
    1: kit1,  # motors  0–15
    2: kit2,  # motors 16–31
    #3: kit3,  # motors 32–47
}

# Part 1: create a LUT for alphabet to binary translation
# logic is:
    # eg. A = top left on = 100000
    # (top left) (middle left) (bottom left) (top right) (middle right) (bottom right)
braille_lut = {
    "A": "100000", "B": "110000", "C": "100100", "D": "100110",
    "E": "100010", "F": "110100", "G": "110110", "H": "110010",
    "I": "010100", "J": "010110", "K": "101000", "L": "111000",
    "M": "101100", "N": "101110", "O": "101010", "P": "111100",
    "Q": "111110", "R": "111010", "S": "011100", "T": "011110",
    "U": "101001", "V": "111001", "W": "010111", "X": "101101",
    "Y": "101111", "Z": "101011"
}

dot_positions = ["top left", "middle left", "bot left", "top right", "middle right", "bot right"]

# Part 2: Write motor LUT referencing alphabet LUT
# logic is: 
    # code reads A then it refers to braille_lut to know how A looks in binary
    # Then from binary encode, will decode respective motors depending on position the letter needs to be

# Format: servo motor number: {"position": "position name respective to 6 dot_positions"}
servo_lut = {
    0: {"position": "top left"},    1: {"position": "middle left"}, 2: {"position": "bot left"},
    3: {"position": "top right"},   4: {"position": "middle right"}, 5: {"position": "bot right"},
    6: {"position": "top left"},    7: {"position": "middle left"}, 8: {"position": "bot left"},
    9: {"position": "top right"},  10: {"position": "middle right"}, 11: {"position": "bot right"},
    12: {"position": "top left"},   13: {"position": "middle left"}, 14: {"position": "bot left"},
    15: {"position": "top right"},  16: {"position": "middle right"}, 17: {"position": "bot right"},
    18: {"position": "top left"},   19: {"position": "middle left"}, 20: {"position": "bot left"},
    21: {"position": "top right"},  22: {"position": "middle right"}, 23: {"position": "bot right"},
    24: {"position": "top left"},   25: {"position": "middle left"}, 26: {"position": "bot left"},
    27: {"position": "top right"},  28: {"position": "middle right"}, 29: {"position": "bot right"},
    30: {"position": "top left"},   31: {"position": "middle left"}, 32: {"position": "bot left"},
    33: {"position": "top right"},  34: {"position": "middle right"}, 35: {"position": "bot right"},
    36: {"position": "top left"},   37: {"position": "middle left"}, 38: {"position": "bot left"},
    39: {"position": "top right"},  40: {"position": "middle right"}, 41: {"position": "bot right"},
    42: {"position": "top left"},   43: {"position": "middle left"}, 44: {"position": "bot left"},
    45: {"position": "top right"},  46: {"position": "middle right"}, 47: {"position": "bot right"},
}

#Return a list of motor_ids sorted ascending (physical order)
# Keeps LUT input clean
def build_motor_sequence(servo_lut):
    motor_ids = sorted(servo_lut.keys())
    return motor_ids

# Returns the servo motor driver each servo motor id belongs to
def motor_driver_from_id(motor_id, motors_per_driver=16):
    return (motor_id // motors_per_driver) + 1

def translate_letter_to_motors(letter, motor_sequence, cell_index):
    """
    letter -> list of activated motor dicts for the letter's cell.
    Each cell uses 6 consecutive motors from motor_sequence starting at cell_index*6.
    """

    # allows for case insensitivity A = a
    letter = letter.upper()
    # out of scope character detection
    if letter not in braille_lut:
        return []

    # translate letter to binary LUT
    pattern = braille_lut[letter]
    # define range of where letter starts and ends
    start_idx = cell_index * 6
    end_idx = (start_idx + 6) - 1

    # catch error for word out of motor scope
    if end_idx > len(motor_sequence):
        # not enough motors available
        raise IndexError(f"Not enough motors for letter #{cell_index+1} ('{letter}'). "
                         f"Need motors {start_idx+1}..{end_idx}, but only {len(motor_sequence)} exist.")

    cell_motors = motor_sequence[start_idx:end_idx]
    active = []
    for bit_i, bit in enumerate(pattern):
        if bit == "1":
            motor_id = cell_motors[bit_i]
            active.append({
                "motor": motor_id,
                "driver": motor_driver_from_id(motor_id),
                "position": dot_positions[bit_i]
            })
    return active

def translate_word(word, servo_lut):
    motor_sequence = build_motor_sequence(servo_lut)
    word = word.strip()
    results = []
    for i, ch in enumerate(word):
        try:
            active = translate_letter_to_motors(ch, motor_sequence, i)
        except IndexError as e:
            print("ERROR:", e)
            active = []
        results.append((ch.upper(), active))
    return results

def print_translation(results):
    for letter, motors in results:
        print(f"\nLetter '{letter}' -> activate:")
        if not motors:
            print("  (ERROR: no motors active or mapping missing)")
        else:
            for m in motors:
                print(f"  Driver {m['driver']} | Servo {m['motor']} | Position: {m['position']}")

# Top level multi-threading function created to run motors in parallel
def run_motor(results):

    # sub function for required motor motion (can be updated later to accurate requirement)
    def run_individual_motor(driver, motor_number, position):
        if motor_number is None or driver is None:
            return

        kit = driver_kits.get(driver)
        if kit is None:
            print(f"WARNING: No kit configured for driver {driver}, skipping motor {motor_number}")
            return
        # Compute the motor channel (0-15) based on top level motor_id (0-47)
        channel = motor_number % 16

        # Basic motion pattern (we can update when actually running)
        kit.continuous_servo[channel].throttle = 1
        time.sleep(1)
        kit.continuous_servo[channel].throttle = -1
        time.sleep(1)
        kit.continuous_servo[channel].throttle = 0
        time.sleep(1)

    threads = []

    # Iterate through each letter's motors in results
    for letter, motor_dicts in results:
        # Grab motor, driver, and position arguments
        for motor_dict in motor_dicts:
            motor_number = motor_dict.get('motor')      
            driver = motor_dict.get('driver')     
            position = motor_dict.get('position')  

            # Fallback: compute driver if missing
            if driver is None and motor_number is not None:
                driver = (motor_number // 16) + 1

            if motor_number is not None and driver is not None:
                thread = threading.Thread(
                    target=run_individual_motor,
                    args=(driver, motor_number, position),
                )
                threads.append(thread)
                thread.start()

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

def main():
    word = input("Enter a word to translate to Braille servo commands: ")
    res = translate_word(word, servo_lut)
    print_translation(res)
    run_motor(res)


if __name__ == "__main__":
    main()
