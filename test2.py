#!/usr/bin/env python3
# Test 1: pot used as a variable resistor (end + wiper) with a fixed 10k from A0 to GND.
# Prints the pot reading ~10x per second. Hold the knob still to see the noise. Ctrl+C to stop.
import time, statistics
from collections import deque

try:
    from smbus2 import SMBus
except ImportError:
    from smbus import SMBus

ADDR = 0x48  # ADS1115 with ADDR left unconnected
VDD = 3.3  # Pi 3.3 V rail powering the pot and the ADS1115
R_FIXED = 10000.0  # fixed resistor from A0 to GND (ohms)
R_POT = (
    10000.0  # pot end-to-end resistance; measure yours (it's +/-20%) and put it here
)
ANGLE = 340.0  # RH24PC electrical travel in degrees


def read_a0(bus):
    # Config 0xC383: start conversion, AIN0 vs GND, +/-4.096 V range, single-shot, 128 SPS
    bus.write_i2c_block_data(ADDR, 0x01, [0xC3, 0x83])
    time.sleep(0.009)
    while not bus.read_i2c_block_data(ADDR, 0x01, 2)[0] & 0x80:
        time.sleep(0.001)
    hi, lo = bus.read_i2c_block_data(ADDR, 0x00, 2)
    raw = (hi << 8) | lo
    if raw >= 0x8000:
        raw -= 0x10000
    return raw * 4.096 / 32768


bus = SMBus(1)
history = deque(maxlen=50)
last_print = 0.0
try:
    while True:
        v = read_a0(bus)
        if v < 0.01:
            print(
                f"\rA0 = {v:.4f} V   wiper off the track or open circuit          ",
                end="",
                flush=True,
            )
            time.sleep(0.1)
            continue
        r_pot = R_FIXED * (VDD / v - 1)  # from V_A0 = VDD * R_FIXED / (R_FIXED + R_pot)
        angle = r_pot / R_POT * ANGLE
        history.append(angle)
        if time.monotonic() - last_print > 0.1:
            last_print = time.monotonic()
            noise = statistics.pstdev(history) if len(history) > 5 else 0.0
            print(
                f"\rA0 = {v:.4f} V   pot = {r_pot:6.0f} ohm   angle = {angle:7.2f} deg"
                f"   noise = {noise:.3f} deg rms   ",
                end="",
                flush=True,
            )
except KeyboardInterrupt:
    print()
finally:
    bus.close()
