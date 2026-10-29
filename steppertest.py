#!/usr/bin/env python3
# Sweep test: turn the Sangaboard's 4th (auxiliary) motor in small moves, read the pot
# (3-wire circuit, A0) after each move, then save a graph of voltage vs motor steps.
# Ctrl+C stops early and still saves the graph.
import time
import serial
import matplotlib

matplotlib.use("Agg")  # no screen over SSH, so draw straight to a PNG file
import matplotlib.pyplot as plt
from smbus2 import SMBus

PORT = "/dev/serial0"  # Pi's hardware serial port (GPIO14/15), where the Sangaboard listens
STEPS_PER_MOVE = 1  # motor steps between readings (smaller = finer graph, slower sweep)
TOTAL_STEPS = (
    10000  # how far to turn in total; must be more than one full turn of the pot
)
ADC_ADDR = 0x48


def read_volts(bus):
    # Same as test 2: one single-shot reading of A0 vs GND, +/-4.096 V range
    bus.write_i2c_block_data(ADC_ADDR, 0x01, [0xC3, 0x83])
    time.sleep(0.009)
    while not bus.read_i2c_block_data(ADC_ADDR, 0x01, 2)[0] & 0x80:
        time.sleep(0.001)
    hi, lo = bus.read_i2c_block_data(ADC_ADDR, 0x00, 2)
    raw = (hi << 8) | lo
    if raw >= 0x8000:
        raw -= 0x10000
    return raw * 4.096 / 32768


def send(board, command):
    # Send one command line to the Sangaboard and return its one-line reply
    board.write((command + "\n").encode())
    return board.readline().decode(errors="replace").strip()


board = serial.Serial(PORT, 115200, timeout=10)
time.sleep(0.5)
board.reset_input_buffer()
print("Sangaboard firmware:", send(board, "version"))
print(
    "blocking_moves true ->", send(board, "blocking_moves true")
)  # each move replies when finished
print("n_motors 4 ->", send(board, "n_motors 4"))  # turn on the 4th motor

bus = SMBus(1)
steps, volts = [], []
try:
    for pos in range(0, TOTAL_STEPS + 1, STEPS_PER_MOVE):
        v = read_volts(bus)
        steps.append(pos)
        volts.append(v)
        print(f"step {pos:6d}   A0 = {v:.4f} V")
        if pos < TOTAL_STEPS:
            reply = send(board, f"mr 0 0 0 {STEPS_PER_MOVE}")  # move only motor 4
            if reply != "done":
                print("   Sangaboard replied:", reply)
except KeyboardInterrupt:
    print("Stopped early.")
finally:
    send(board, "release")  # switch the motor coils off so it doesn't heat up
    board.close()
    bus.close()

# Find where the voltage jumps the most between two readings: that's the wrap-around point
plt.plot(steps, volts, ".-", markersize=3)
if len(volts) > 1:
    jumps = [abs(volts[i + 1] - volts[i]) for i in range(len(volts) - 1)]
    i = jumps.index(max(jumps))
    print(
        f"Biggest jump: {volts[i]:.3f} V at step {steps[i]}  ->  {volts[i + 1]:.3f} V at step {steps[i + 1]}"
    )
    plt.axvline(steps[i], color="red", linestyle="--", label=f"jump at step {steps[i]}")
    plt.legend()
plt.xlabel("Motor steps")
plt.ylabel("Pot voltage on A0 (V)")
plt.title("Pot voltage vs stepper position")
plt.grid(True)
plt.savefig("sweep.png", dpi=150)
print("Graph saved to sweep.png")
