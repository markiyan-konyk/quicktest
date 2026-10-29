#!/usr/bin/env python3
# Sweep test: turn the Sangaboard's 4th (auxiliary) motor, read the pot (3-wire circuit, A0)
# after every move, and record the exact step where the pot wraps around: the moment the
# voltage comes back at the low end and starts rising again. The number of steps between two
# of those moments is one full turn of the pot. Ctrl+C stops early and still saves everything.
import time
import serial
import matplotlib

matplotlib.use("Agg")  # no screen over SSH, so draw straight to a PNG file
import matplotlib.pyplot as plt
from smbus2 import SMBus

PORT = "/dev/serial0"  # Pi's hardware serial port (GPIO14/15), where the Sangaboard listens
TOTAL_STEPS = 100000  # how far to turn in total; a long test covers many pot turns
COARSE_STEPS = 20  # steps per move while far from the limit (fast)
FINE_STEPS = 1  # steps per move near the limit, so the wrap is found to the exact step
NEAR_TOP_V = 3.0  # above this the pot is close to its limit: switch to fine steps
START_V = 0.2  # after the limit, a reading below this may be the track starting again
CONFIRM = 5  # this many smooth readings in a row confirm the track really restarted
SMOOTH_V = 0.05  # biggest change between two fine readings that still counts as smooth
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
log = open("limits.txt", "a")  # every limit is saved here as soon as it's found
log.write(f"\n--- sweep started {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")

steps, volts, limits = [], [], []
pos = 0
near_limit = False  # True once we pass NEAR_TOP_V, until the restart has been found
candidate = None  # step of a low reading that might be the track starting again
smooth = 0  # smooth readings counted since that candidate

try:
    while True:
        v = read_volts(bus)
        steps.append(pos)
        volts.append(v)

        if not near_limit:
            near_limit = v > NEAR_TOP_V
        elif candidate is not None and abs(v - volts[-2]) < SMOOTH_V:
            smooth += 1
            if smooth >= CONFIRM:  # the track really restarted at `candidate`
                limits.append(candidate)
                msg = f"Limit #{len(limits)} at step {candidate}"
                if len(limits) > 1:
                    msg += (
                        f"   ({limits[-1] - limits[-2]} steps since the previous one)"
                    )
                print("\n" + msg)
                log.write(msg + "\n")
                log.flush()
                near_limit, candidate = False, None
        else:
            # not confirmed yet: a low reading starts a new candidate, anything else resets it
            candidate = pos if v < START_V else None
            smooth = 0

        print(
            f"\rstep {pos:7d}   A0 = {v:.4f} V   limits found: {len(limits)}   ",
            end="",
            flush=True,
        )

        if pos >= TOTAL_STEPS:
            break
        move = FINE_STEPS if near_limit else COARSE_STEPS
        reply = send(board, f"mr 0 0 0 {move}")  # move only motor 4
        if reply != "done":
            print("\n   Sangaboard replied:", reply)
        pos += move
except KeyboardInterrupt:
    print("\nStopped early.")
finally:
    send(board, "release")  # switch the motor coils off so it doesn't heat up
    board.close()
    bus.close()

# Summary: steps between consecutive limits = steps for one full turn of the pot
print()
gaps = [b - a for a, b in zip(limits, limits[1:])]
if gaps:
    summary = (
        f"Steps per pot turn: {gaps}\n"
        f"Average {sum(gaps) / len(gaps):.1f}, min {min(gaps)}, max {max(gaps)}"
    )
else:
    summary = (
        f"Limits found at steps {limits}; need at least two to measure a full turn."
    )
print(summary)
log.write(summary + "\n")
log.close()

plt.plot(steps, volts, ".-", markersize=2, linewidth=0.8)
for s in limits:
    plt.axvline(s, color="red", linestyle="--", linewidth=0.8)
plt.xlabel("Motor steps")
plt.ylabel("Pot voltage on A0 (V)")
plt.title("Pot voltage vs stepper position (red = limit)")
plt.grid(True)
plt.savefig("sweep.png", dpi=150)
print("Graph saved to sweep.png, limits saved to limits.txt")
