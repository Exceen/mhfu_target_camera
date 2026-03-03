#!/usr/bin/env python3
"""Generate CWCheat codes for JP version (ULJM05500) only."""

import struct

CWCHEAT_BASE = 0x08800000

def bin_to_cwcheat(data, base_addr):
    """Convert binary data to CWCheat 32-bit write lines."""
    lines = []
    # Pad to 4-byte alignment
    if len(data) % 4 != 0:
        data += b'\x00' * (4 - len(data) % 4)
    for i in range(0, len(data), 4):
        word = struct.unpack('<I', data[i:i+4])[0]
        addr = base_addr + i
        offset = addr - CWCHEAT_BASE
        lines.append(f"_L 0x2{offset:07X} 0x{word:08X}")
    return lines

def divide_and_write(f, filepath, base_addr, name, amount, offset_0, offset_1):
    """Split a binary file into CWCheat sections."""
    ALIGNMENT = 0x20
    with open(filepath, 'rb') as bf:
        content = bf.read()

    total_size = len(content)
    part_size = (total_size // amount) & ~(ALIGNMENT - 1)

    for i in range(amount):
        start = i * part_size
        end = start + part_size if i < amount - 1 else total_size
        chunk = content[start:end]

        if i < amount - 1 and len(chunk) % ALIGNMENT != 0:
            pad = ALIGNMENT - (len(chunk) % ALIGNMENT)
            chunk += b'\x00' * pad

        section_addr = base_addr + start
        f.write(f"_C0 {name} [{i+offset_0}/{amount+offset_1}]\n")
        for line in bin_to_cwcheat(chunk, section_addr):
            f.write(line + "\n")

amount = 20
total = amount + 6  # +4 original sections + 2 vert hook sections

with open("ULJM-05500.TXT", "w") as f:
    # Section 1: Vertex data
    with open("bin/VERTEX.bin", "rb") as bf:
        data = bf.read()
    f.write(f"_C0 Target Cam [1/{total}]\n")
    for line in bin_to_cwcheat(data, 0x0891E2C0):
        f.write(line + "\n")

    # Section 2: Camera code
    with open("bin/TARGET_CAM_JP.bin", "rb") as bf:
        data = bf.read()
    f.write(f"_C0 Target Cam [2/{total}]\n")
    for line in bin_to_cwcheat(data, 0x0891C920):
        f.write(line + "\n")

    # Section 3: Hook 1
    f.write(f"_C0 Target Cam [3/{total}]\n")
    f.write("_L 0x200871F8 0x0A247248\n")

    # Section 4: Hook 2
    f.write(f"_C0 Target Cam [4/{total}]\n")
    f.write("_L 0x20069408 0x0A2472A8\n")

    # Sections 5-24: Target change code (split into chunks)
    divide_and_write(f, "bin/TARGET_CHANGE_JP.bin", 0x0891CAA0,
                     "Target Cam", amount, 5, 4)

    # Section 25: Vert hook code
    with open("bin/VERT_HOOK.bin", "rb") as bf:
        data = bf.read()
    f.write(f"_C0 Target Cam [{amount+5}/{total}]\n")
    for line in bin_to_cwcheat(data, 0x0891D700):
        f.write(line + "\n")

    # Section 26: Hook 3 (vert hook jump + nop)
    f.write(f"_C0 Target Cam [{amount+6}/{total}]\n")
    f.write("_L 0x20086CA4 0x0A2475C0\n")
    f.write("_L 0x20086CA8 0x00000000\n")

    # Crosshair sections
    divide_and_write(f, "bin/crosshair.bin", 0x0891DDBC,
                     "Crosshair", 8, 1, 0)

print("Generated ULJM-05500.TXT")
