#!/usr/bin/env python3
"""
Interactive PCA9685 servo calibration tool with separate HOME and ON positions.

Features:
- Sends all enabled channels to their saved HOME angle first
- Lets you select a servo and adjust it live with single key presses
- Switch between calibrating HOME vs ON for the selected servo
- Prints current angles in real time
- Saves/generated calibration tables for your project

Designed for the user's current setup:
- PCA9685 at 0x40
- PCA9685 at 0x41
- 16 channels on each board
- Adafruit ServoKit + CircuitPython stack
"""

import json
import os
import sys
import time
import select
import termios
import tty
from typing import Dict

import board
import busio
from adafruit_servokit import ServoKit


# =========================
# USER-TUNABLE SETTINGS
# =========================
DRIVER_ADDRESSES = {
    1: 0x40,
    2: 0x41,
    # 3: 0x42,
}

CHANNELS_PER_DRIVER = 16
DEFAULT_HOME = 85
DEFAULT_ON = 170
DEFAULT_ACTUATION_RANGE = 180
PULSE_MIN_US = 500
PULSE_MAX_US = 2500
SMALL_STEP = 1
LARGE_STEP = 5
TEST_DELTA = 20
MOVE_DELAY = 0.08
SAVE_JSON_PATH = "servo_home_on_calibration.json"
SAVE_PY_PATH = "servo_home_on_calibration_table.py"

DOT_POSITIONS = ["top left", "middle left", "bot left", "top right", "middle right", "bot right"]


def motor_position_name(motor_id: int) -> str:
    return DOT_POSITIONS[motor_id % 6]


def motor_driver_from_id(motor_id: int) -> int:
    return (motor_id // CHANNELS_PER_DRIVER) + 1


def channel_from_motor_id(motor_id: int) -> int:
    return motor_id % CHANNELS_PER_DRIVER


def clamp(angle: int, low: int = 0, high: int = 180) -> int:
    return max(low, min(high, int(angle)))


class RawKeyReader:
    def __enter__(self):
        self.fd = sys.stdin.fileno()
        self.old_settings = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        return self

    def __exit__(self, exc_type, exc, tb):
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)

    def read_key(self, timeout: float = None):
        rlist, _, _ = select.select([sys.stdin], [], [], timeout)
        if not rlist:
            return None
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            rlist, _, _ = select.select([sys.stdin], [], [], 0.01)
            if rlist:
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    rlist, _, _ = select.select([sys.stdin], [], [], 0.01)
                    if rlist:
                        ch3 = sys.stdin.read(1)
                        return "ESC[" + ch3
            return "ESC"
        return ch


class ServoCalibrator:
    def __init__(self):
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.kits: Dict[int, ServoKit] = {}
        self.enabled_motor_ids = []
        self.home_by_motor: Dict[int, int] = {}
        self.on_by_motor: Dict[int, int] = {}
        self.current_angle_by_motor: Dict[int, int] = {}
        self.saved_home_by_motor: Dict[int, int] = {}
        self.saved_on_by_motor: Dict[int, int] = {}
        self.selected_index = 0
        self.edit_mode = "home"  # "home" or "on"

        self._init_kits()
        self._init_servos()
        self._load_existing_calibration_if_present()

    def _init_kits(self):
        for driver, address in DRIVER_ADDRESSES.items():
            self.kits[driver] = ServoKit(channels=CHANNELS_PER_DRIVER, i2c=self.i2c, address=address)

    def _init_servos(self):
        max_motor_id = max(DRIVER_ADDRESSES.keys()) * CHANNELS_PER_DRIVER
        for motor_id in range(max_motor_id):
            driver = motor_driver_from_id(motor_id)
            if driver not in self.kits:
                continue
            channel = channel_from_motor_id(motor_id)
            servo = self.kits[driver].servo[channel]
            servo.actuation_range = DEFAULT_ACTUATION_RANGE
            servo.set_pulse_width_range(PULSE_MIN_US, PULSE_MAX_US)
            self.enabled_motor_ids.append(motor_id)
            self.home_by_motor[motor_id] = DEFAULT_HOME
            self.on_by_motor[motor_id] = DEFAULT_ON
            self.current_angle_by_motor[motor_id] = DEFAULT_HOME

    def _load_existing_calibration_if_present(self):
        if not os.path.exists(SAVE_JSON_PATH):
            return
        try:
            with open(SAVE_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)

            home_map = {int(key): clamp(val) for key, val in data.get("home_by_motor", {}).items()}
            on_map = {int(key): clamp(val) for key, val in data.get("on_by_motor", {}).items()}
            self.saved_home_by_motor = dict(home_map)
            self.saved_on_by_motor = dict(on_map)

            for motor_id, value in home_map.items():
                if motor_id in self.home_by_motor:
                    self.home_by_motor[motor_id] = value
                    self.current_angle_by_motor[motor_id] = value

            for motor_id, value in on_map.items():
                if motor_id in self.on_by_motor:
                    self.on_by_motor[motor_id] = value

            print(f"Loaded existing calibration from {SAVE_JSON_PATH}")
        except Exception as exc:
            print(f"WARNING: Could not load {SAVE_JSON_PATH}: {exc}")

    def servo_for_motor(self, motor_id: int):
        driver = motor_driver_from_id(motor_id)
        channel = channel_from_motor_id(motor_id)
        return self.kits[driver].servo[channel]

    def move_motor(self, motor_id: int, angle: int, delay: float = MOVE_DELAY):
        angle = clamp(angle)
        self.servo_for_motor(motor_id).angle = angle
        self.current_angle_by_motor[motor_id] = angle
        time.sleep(delay)

    def send_all_to_home(self):
        print("\nSending all enabled servos to their HOME angles...")
        for motor_id in self.enabled_motor_ids:
            self.move_motor(motor_id, self.home_by_motor[motor_id], delay=0.03)
        time.sleep(0.5)

    def send_all_to_on(self):
        print("\nSending all enabled servos to their ON angles...")
        for motor_id in self.enabled_motor_ids:
            self.move_motor(motor_id, self.on_by_motor[motor_id], delay=0.03)
        time.sleep(0.5)

    def selected_motor(self) -> int:
        return self.enabled_motor_ids[self.selected_index]

    def select_next(self):
        self.selected_index = (self.selected_index + 1) % len(self.enabled_motor_ids)

    def select_prev(self):
        self.selected_index = (self.selected_index - 1) % len(self.enabled_motor_ids)

    def active_target_angle(self, motor_id: int) -> int:
        return self.home_by_motor[motor_id] if self.edit_mode == "home" else self.on_by_motor[motor_id]

    def selected_status_line(self) -> str:
        motor_id = self.selected_motor()
        driver = motor_driver_from_id(motor_id)
        channel = channel_from_motor_id(motor_id)
        position = motor_position_name(motor_id)
        current = self.current_angle_by_motor[motor_id]
        home = self.home_by_motor[motor_id]
        on = self.on_by_motor[motor_id]
        active = self.active_target_angle(motor_id)
        return (
            f"Selected motor {motor_id} | driver {driver} | channel {channel} | "
            f"position '{position}' | mode={self.edit_mode.upper()} | "
            f"current={current}° | HOME={home}° | ON={on}° | active target={active}°"
        )

    def print_help(self):
        print("""
Controls:
  [ / ]   -> previous / next motor
  a / d   -> -1 / +1 degree
  j / l   -> -5 / +5 degrees
  Left/Right arrows also work for -1/+1 on many terminals

  m       -> toggle edit mode: HOME <-> ON
  h       -> move selected motor to saved HOME
  o       -> move selected motor to saved ON
  H       -> save current angle as HOME for selected motor
  O       -> save current angle as ON for selected motor

  t       -> test selected motor HOME -> ON -> HOME
  A       -> send ALL enabled servos to saved HOME
  Z       -> send ALL enabled servos to saved ON
  p       -> print calibration tables
  s       -> save calibration tables to files
  q       -> save + quit
""")

    def print_tables(self):
        print("\nHOME_BY_MOTOR = {")
        for motor_id in self.enabled_motor_ids:
            print(f"    {motor_id}: {self.home_by_motor[motor_id]},")
        print("}")

        print("\nON_BY_MOTOR = {")
        for motor_id in self.enabled_motor_ids:
            print(f"    {motor_id}: {self.on_by_motor[motor_id]},")
        print("}")

    def save_tables(self):
        merged_home = dict(self.saved_home_by_motor)
        merged_on = dict(self.saved_on_by_motor)
        for motor_id in self.enabled_motor_ids:
            merged_home[motor_id] = self.home_by_motor[motor_id]
            merged_on[motor_id] = self.on_by_motor[motor_id]

        self.saved_home_by_motor = dict(merged_home)
        self.saved_on_by_motor = dict(merged_on)

        json_payload = {
            "home_by_motor": {str(motor_id): merged_home[motor_id] for motor_id in sorted(merged_home)},
            "on_by_motor": {str(motor_id): merged_on[motor_id] for motor_id in sorted(merged_on)},
            "meta": {
                "default_actuation_range": DEFAULT_ACTUATION_RANGE,
                "pulse_width_range_us": [PULSE_MIN_US, PULSE_MAX_US],
                "driver_addresses": {str(driver): address for driver, address in sorted(DRIVER_ADDRESSES.items())},
            },
        }
        with open(SAVE_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(json_payload, f, indent=2)

        with open(SAVE_PY_PATH, "w", encoding="utf-8") as f:
            f.write("# Auto-generated by calibrate_servos_live_home_on.py\n")
            f.write(f"DEFAULT_ACTUATION_RANGE = {DEFAULT_ACTUATION_RANGE}\n")
            f.write(f"PULSE_WIDTH_RANGE_US = ({PULSE_MIN_US}, {PULSE_MAX_US})\n\n")

            f.write("HOME_BY_MOTOR = {\n")
            for motor_id in sorted(merged_home):
                position = motor_position_name(motor_id)
                f.write(f"    {motor_id}: {merged_home[motor_id]},  # {position}\n")
            f.write("}\n\n")

            f.write("ON_BY_MOTOR = {\n")
            for motor_id in sorted(merged_on):
                position = motor_position_name(motor_id)
                f.write(f"    {motor_id}: {merged_on[motor_id]},  # {position}\n")
            f.write("}\n")

        print(f"\nSaved calibration to {SAVE_JSON_PATH} and {SAVE_PY_PATH}")

    def adjust_selected(self, delta: int):
        motor_id = self.selected_motor()
        new_angle = clamp(self.current_angle_by_motor[motor_id] + delta)
        self.move_motor(motor_id, new_angle)
        print(self.selected_status_line())

    def move_selected_to_home(self):
        motor_id = self.selected_motor()
        self.move_motor(motor_id, self.home_by_motor[motor_id])
        print(self.selected_status_line())

    def move_selected_to_on(self):
        motor_id = self.selected_motor()
        self.move_motor(motor_id, self.on_by_motor[motor_id])
        print(self.selected_status_line())

    def save_selected_home(self):
        motor_id = self.selected_motor()
        self.home_by_motor[motor_id] = self.current_angle_by_motor[motor_id]
        print(f"Saved HOME for motor {motor_id}: {self.home_by_motor[motor_id]}°")
        print(self.selected_status_line())

    def save_selected_on(self):
        motor_id = self.selected_motor()
        self.on_by_motor[motor_id] = self.current_angle_by_motor[motor_id]
        print(f"Saved ON for motor {motor_id}: {self.on_by_motor[motor_id]}°")
        print(self.selected_status_line())

    def toggle_mode(self):
        self.edit_mode = "on" if self.edit_mode == "home" else "home"
        print(f"Switched edit mode to {self.edit_mode.upper()}")
        print(self.selected_status_line())

    def save_current_to_active_mode(self):
        if self.edit_mode == "home":
            self.save_selected_home()
        else:
            self.save_selected_on()

    def move_selected_to_active_target(self):
        if self.edit_mode == "home":
            self.move_selected_to_home()
        else:
            self.move_selected_to_on()

    def test_selected(self):
        motor_id = self.selected_motor()
        home = self.home_by_motor[motor_id]
        on = self.on_by_motor[motor_id]
        print(f"Testing motor {motor_id}: HOME {home}° -> ON {on}° -> HOME {home}°")
        self.move_motor(motor_id, home, 0.25)
        self.move_motor(motor_id, on, 0.45)
        self.move_motor(motor_id, home, 0.30)
        print(self.selected_status_line())

    def run(self):
        print("Interactive PCA9685 servo HOME/ON calibration")
        print(
            "Using pulse range "
            f"{PULSE_MIN_US}-{PULSE_MAX_US} us and actuation range {DEFAULT_ACTUATION_RANGE}°"
        )
        self.print_help()

        self.send_all_to_home()
        print(self.selected_status_line())
        print("\nAdjust with keys. Press q to save and quit.\n")

        with RawKeyReader() as reader:
            while True:
                key = reader.read_key(timeout=0.25)
                if key is None:
                    continue

                if key == '[':
                    self.select_prev()
                    print(self.selected_status_line())
                elif key == ']':
                    self.select_next()
                    print(self.selected_status_line())
                elif key in ('a', 'ESC[D'):
                    self.adjust_selected(-SMALL_STEP)
                elif key in ('d', 'ESC[C'):
                    self.adjust_selected(+SMALL_STEP)
                elif key == 'j':
                    self.adjust_selected(-LARGE_STEP)
                elif key == 'l':
                    self.adjust_selected(+LARGE_STEP)
                elif key == 'm':
                    self.toggle_mode()
                elif key == 'h':
                    self.move_selected_to_home()
                elif key == 'o':
                    self.move_selected_to_on()
                elif key == 'H':
                    self.save_selected_home()
                elif key == 'O':
                    self.save_selected_on()
                elif key == 'g':
                    self.move_selected_to_active_target()
                elif key == 'n':
                    self.save_current_to_active_mode()
                elif key == 't':
                    self.test_selected()
                elif key == 'A':
                    self.send_all_to_home()
                    print(self.selected_status_line())
                elif key == 'Z':
                    self.send_all_to_on()
                    print(self.selected_status_line())
                elif key == 'p':
                    self.print_tables()
                elif key == 's':
                    self.save_tables()
                elif key == 'q':
                    self.save_tables()
                    print("Exiting.")
                    break
                elif key == '?':
                    self.print_help()
                else:
                    pass


def main():
    try:
        app = ServoCalibrator()
        app.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as exc:
        print(f"\nERROR: {exc}")
        raise


if __name__ == "__main__":
    main()
