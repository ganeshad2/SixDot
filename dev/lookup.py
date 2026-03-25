import json
import threading
import time
from pathlib import Path

try:
    from adafruit_servokit import ServoKit
    import board
    import busio
except Exception:
    ServoKit = None
    board = None
    busio = None


def initialize_driver_kits():
    if ServoKit is None or board is None or busio is None:
        return {}

    try:
        i2c = busio.I2C(board.SCL, board.SDA)
    except Exception as exc:
        print(f"Hardware not available. Skipping motor execution. ({exc})")
        return {}

    driver_kits = {}
    driver_addresses = {
        1: 0x40,
        2: 0x41,
    }

    for driver, address in driver_addresses.items():
        try:
            driver_kits[driver] = ServoKit(channels=16, i2c=i2c, address=address)
        except Exception as exc:
            print(f"Driver {driver} at 0x{address:02X} not available. Skipping it. ({exc})")

    if not driver_kits:
        print("No servo drivers are available. Skipping motor execution.")

    return driver_kits


driver_kits = None

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

HOME_ANGLE_BY_POSITION = {
    "top left": 100,
    "middle left": 0,
    "bot left": 100,
    "top right": 0,
    "middle right": 0,
    "bot right": 0,
}

ON_ANGLE_BY_POSITION = {
    "top left": 0,
    "middle left": 100,
    "bot left": 0,
    "top right": 100,
    "middle right": 100,
    "bot right": 100,
}

CALIBRATION_PATH = Path(__file__).with_name("servo_home_on_calibration.json")
HOME_BY_MOTOR = {}
ON_BY_MOTOR = {}


def load_home_on_calibration():
    if not CALIBRATION_PATH.exists():
        return {}, {}

    try:
        data = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
        home_by_motor = {int(k): int(v) for k, v in data.get("home_by_motor", {}).items()}
        on_by_motor = {int(k): int(v) for k, v in data.get("on_by_motor", {}).items()}
        return home_by_motor, on_by_motor
    except Exception as exc:
        print(f"Calibration load failed. Falling back to default angles. ({exc})")
        return {}, {}


HOME_BY_MOTOR, ON_BY_MOTOR = load_home_on_calibration()

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


def build_motor_sequence(servo_lut):
    motor_ids = sorted(servo_lut.keys())
    return motor_ids


def motor_driver_from_id(motor_id, motors_per_driver=16):
    return (motor_id // motors_per_driver) + 1


def translate_letter_to_motors(letter, motor_sequence, cell_index):
    """
    letter -> list of activated motor dicts for the letter's cell.
    Each cell uses 6 consecutive motors from motor_sequence starting at cell_index*6.
    """
    letter = letter.upper()
    if letter not in braille_lut:
        return []

    pattern = braille_lut[letter]
    start_idx = cell_index * 6
    end_idx = start_idx + 6

    if end_idx > len(motor_sequence):
        raise IndexError(
            f"Not enough motors for letter #{cell_index + 1} ('{letter}'). "
            f"Need motors {start_idx + 1}..{end_idx}, but only {len(motor_sequence)} exist."
        )

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


def run_motor(results):
    global driver_kits

    if driver_kits is None:
        driver_kits = initialize_driver_kits()

    if not driver_kits:
        return

    def run_individual_motor(driver, motor_number, position):
        if motor_number is None or driver is None:
            return

        kit = driver_kits.get(driver)
        if kit is None:
            print(f"WARNING: No kit configured for driver {driver}, skipping motor {motor_number}")
            return

        channel = motor_number % 16
        servo = kit.servo[channel]

        home_angle = HOME_BY_MOTOR.get(motor_number, HOME_ANGLE_BY_POSITION.get(position, 0))
        on_angle = ON_BY_MOTOR.get(motor_number, ON_ANGLE_BY_POSITION.get(position, 100))

        servo.angle = on_angle
        time.sleep(5)
        servo.angle = home_angle

    threads = []

    for _, motor_dicts in results:
        for motor_dict in motor_dicts:
            motor_number = motor_dict.get("motor")
            driver = motor_dict.get("driver")
            position = motor_dict.get("position")

            if driver is None and motor_number is not None:
                driver = (motor_number // 16) + 1

            if motor_number is not None and driver is not None:
                thread = threading.Thread(
                    target=run_individual_motor,
                    args=(driver, motor_number, position),
                )
                threads.append(thread)
                thread.start()

    for thread in threads:
        thread.join()


def main():
    word = input("Enter a word to translate to Braille servo commands: ")
    res = translate_word(word, servo_lut)
    print_translation(res)
    run_motor(res)


if __name__ == "__main__":
    main()
