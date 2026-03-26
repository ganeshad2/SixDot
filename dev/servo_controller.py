import time
from adafruit_servokit import ServoKit
import board
import busio

# init test
"""import board
import busio
import adafruit_pca9685
i2c = busio.I2C(board.SCL, board.SDA)
pca = adafruit_pca9685.PCA9685(i2c)"""

# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT



# SWE Algorithm
# LUT for letters

# Datastructure - dict {'letter' : [dots that needs to be active]}

# Shared I2C bus
i2c = busio.I2C(board.SCL, board.SDA)

# Set channels to the number of servo channels on your kit.
# 8 for FeatherWing, 16 for Shield/HAT/Bonnet.
kit1 = ServoKit(channels=16, i2c=i2c, address=0x41)
s = kit1.servo[0]
# Try expanding the range (values are microseconds)
s.set_pulse_width_range(500, 2500)

#kit2 = ServoKit(channels=16, i2c=i2c, address=0x41)

'''
kit.servo[0].angle = 180
kit.continuous_servo[1].throttle = 1
time.sleep(1)
kit.continuous_servo[1].throttle = -1
time.sleep(1)
kit.servo[0].angle = 0
kit.continuous_servo[1].throttle = 0

kit.servo[15].angle = 180
kit.continuous_servo[1].throttle = 1
time.sleep(1)
kit.continuous_servo[1].throttle = -1
time.sleep(1)
kit.servo[15].angle = 0
kit.continuous_servo[1].throttle = 0
'''
while (1):
    s.angle = 0
    time.sleep(1)
    s.angle = 100
    time.sleep(1)
'''
kit2.continuous_servo[0].throttle = 1
time.sleep(1)
kit2.continuous_servo[0].throttle = -1
time.sleep(1)
kit2.continuous_servo[0].throttle = 0
'''
