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
    1: {"position": "top left"},    2: {"position": "middle left"}, 3: {"position": "bot left"},
    4: {"position": "top right"},   5: {"position": "middle right"},6: {"position": "bot right"},
    7: {"position": "top left"},    8: {"position": "middle left"}, 9: {"position": "bot left"},
    10: {"position": "top right"}, 11: {"position": "middle right"},12: {"position": "bot right"},
    13: {"position": "top left"},   14: {"position": "middle left"},15: {"position": "bot left"},
    16: {"position": "top right"}, 17: {"position": "middle right"},18: {"position": "bot right"},
    19: {"position": "top left"},   20: {"position": "middle left"},21: {"position": "bot left"},
    22: {"position": "top right"}, 23: {"position": "middle right"},24: {"position": "bot right"},
    25: {"position": "top left"},   26: {"position": "middle left"},27: {"position": "bot left"},
    28: {"position": "top right"}, 29: {"position": "middle right"},30: {"position": "bot right"},
    31: {"position": "top left"},   32: {"position": "middle left"},33: {"position": "bot left"},
    34: {"position": "top right"}, 35: {"position": "middle right"},36: {"position": "bot right"},
    37: {"position": "top left"},   38: {"position": "middle left"},39: {"position": "bot left"},
    40: {"position": "top right"}, 41: {"position": "middle right"},42: {"position": "bot right"},
    43: {"position": "top left"},   44: {"position": "middle left"},45: {"position": "bot left"},
    46: {"position": "top right"}, 47: {"position": "middle right"},48: {"position": "bot right"},
}

#Return a list of motor_ids sorted ascending (physical order)
# Keeps LUT input clean
def build_motor_sequence(servo_lut):
    motor_ids = sorted(servo_lut.keys())
    return motor_ids

# Returns the servo motor driver each servo motor id belongs to
# e.g. motor_id = 17 
    # (17-1)//16 + 1 = 16//16 + 1 = 1 + 1 = 2 -> Driver 2
def motor_driver_from_id(motor_id, motors_per_driver=16):
    return ((motor_id - 1) // motors_per_driver) + 1

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
    end_idx = start_idx + 6

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

def main():
    word = input("Enter a word to translate to Braille servo commands: ")
    res = translate_word(word, servo_lut)
    print_translation(res)

if __name__ == "__main__":
    main()