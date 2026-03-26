#!/usr/bin/env python3
"""Patch EBOOT.BIN inside a PSP ISO with target camera binaries."""

import struct
import shutil
import sys
import os

SECTOR_SIZE = 2048
EBOOT_BASE = 0x8801A4C
BASE_RAM = 0x8800000


def find_file_in_iso(iso_path, target_path_parts):
    """Parse ISO 9660 to find a file's byte offset and size."""
    with open(iso_path, 'rb') as f:
        # Read Primary Volume Descriptor at sector 16
        f.seek(16 * SECTOR_SIZE)
        pvd = f.read(SECTOR_SIZE)
        assert pvd[0:1] == b'\x01' and pvd[1:6] == b'CD001', "Not a valid ISO 9660"

        # Root directory record starts at byte 156 of PVD
        root_record = pvd[156:156+34]
        dir_lba = struct.unpack_from('<I', root_record, 2)[0]
        dir_size = struct.unpack_from('<I', root_record, 10)[0]

        for part in target_path_parts:
            f.seek(dir_lba * SECTOR_SIZE)
            dir_data = f.read(dir_size)
            found = False
            pos = 0
            while pos < len(dir_data):
                rec_len = dir_data[pos]
                if rec_len == 0:
                    # Skip to next sector boundary
                    pos = (pos // SECTOR_SIZE + 1) * SECTOR_SIZE
                    continue
                name_len = dir_data[pos + 32]
                name = dir_data[pos + 33:pos + 33 + name_len].decode('ascii', errors='replace')
                # ISO 9660 appends ";1" version, strip it
                name = name.split(';')[0]
                lba = struct.unpack_from('<I', dir_data, pos + 2)[0]
                size = struct.unpack_from('<I', dir_data, pos + 10)[0]
                flags = dir_data[pos + 25]

                if name.upper() == part.upper():
                    dir_lba = lba
                    dir_size = size
                    found = True
                    break
                pos += rec_len

            if not found:
                raise FileNotFoundError(f"'{part}' not found in ISO directory")

    return dir_lba * SECTOR_SIZE, dir_size


def patch_iso(iso_path, eboot_offset):
    """Apply target camera patches to EBOOT.BIN inside the ISO."""
    patches = []

    # TARGET_CAM_JP.bin -> 0x0891C920
    with open("bin/TARGET_CAM_JP.bin", "rb") as f:
        patches.append((0x0891C920 - EBOOT_BASE, f.read()))

    # TARGET_CHANGE_JP.bin -> 0x0891CAA0
    with open("bin/TARGET_CHANGE_JP.bin", "rb") as f:
        patches.append((0x0891CAA0 - EBOOT_BASE, f.read()))

    # VERTEX.bin -> 0x0891E2C0
    with open("bin/VERTEX.bin", "rb") as f:
        patches.append((0x0891E2C0 - EBOOT_BASE, f.read()))

    # crosshair.bin -> 0x0891DDBC
    with open("bin/crosshair.bin", "rb") as f:
        patches.append((0x0891DDBC - EBOOT_BASE, f.read()))

    # Hook 1: at 0x000871F8 + BASE_RAM
    patches.append((0x000871F8 + BASE_RAM - EBOOT_BASE, b'\x48\x72\x24\x0A'))

    # Hook 2: at 0x00069408 + BASE_RAM
    patches.append((0x00069408 + BASE_RAM - EBOOT_BASE, b'\xA8\x72\x24\x0A'))

    # VERT_HOOK.bin -> 0x0891D7C0
    with open("bin/VERT_HOOK.bin", "rb") as f:
        patches.append((0x0891D7C0 - EBOOT_BASE, f.read()))

    # Hook 3: at 0x08886CA4 (replace 2 instructions with j + nop)
    # j 0x0891D7C0 = 0x0A2475F0
    patches.append((0x08886CA4 - EBOOT_BASE, b'\xF0\x75\x24\x0A\x00\x00\x00\x00'))

    # Icon X position default value (halfword = 8)
    patches.append((0x0891C8EC - EBOOT_BASE, struct.pack('<H', 8)))

    with open(iso_path, 'r+b') as f:
        for file_offset, data in patches:
            iso_offset = eboot_offset + file_offset
            f.seek(iso_offset)
            f.write(data)
            print(f"  Patched {len(data):>5} bytes at EBOOT+0x{file_offset:06X} (ISO offset 0x{iso_offset:08X})")


def generate_cheats():
    """Generate cheats.txt from exported label addresses."""
    with open("bin/cheats_addrs.bin", "rb") as f:
        data = f.read()

    addrs = struct.unpack(f'<{len(data)//4}I', data)
    (vtx1_hi, y1, vtx4_hi, y2, crosshair_draw,
     cx0, cx1, cx2, cx3, cx4, cx5,
     cy0, cy1, cy2, cy3, cy4, cy5,
     icon_x_pos) = addrs

    CW = 0x08800000

    def cw32(addr, val):
        return f"_L 0x2{addr - CW:07X} 0x{val:08X}"

    def cw16(addr, val):
        return f"_L 0x1{addr - CW:07X} 0x{val:08X}"

    # Icon size cheats patch the lui/ori halves of li instructions
    # Small: x=9..27(18px), y=246..264(18px)
    # Medium: x=9..33(24px), y=240..264(24px)
    # Large: x=8..44(36px), y=228..264(36px) — code default

    cross_addrs = [cx0, cx1, cx2, cx3, cx4, cx5,
                   cy0, cy1, cy2, cy3, cy4, cy5]

    # Crosshair offset patterns: [x0..x5, y0..y5]
    cross_50  = [-8, 8, 8, -8, 8, -8, -8, 8, -8, -8, 8, 8]
    cross_75  = [-12, 12, 12, -12, 12, -12, -12, 12, -12, -12, 12, 12]
    cross_100 = [-16, 16, 16, -16, 16, -16, -16, 16, -16, -16, 16, 16]

    def addi_instr(offset):
        # addi t0, t0, offset -> 0x21080000 | (offset & 0xFFFF)
        return 0x21080000 | (offset & 0xFFFF)

    lines = []
    lines.append("_C0 == Target Cam Adjustments ====")
    lines.append("_L 0x00000000 0x00000000")

    lines.append("_C0  Small Icon (18x18)")
    lines.append(cw32(vtx1_hi, 0x3C080009))
    lines.append(cw32(y1, 0x340800F6))
    lines.append(cw32(vtx4_hi, 0x3C08001B))
    lines.append(cw32(y2, 0x34080108))

    lines.append("_C0  Medium Icon (24x24)")
    lines.append(cw32(vtx1_hi, 0x3C080009))
    lines.append(cw32(y1, 0x340800F0))
    lines.append(cw32(vtx4_hi, 0x3C080021))
    lines.append(cw32(y2, 0x34080108))

    lines.append("_C0  Large Icon (36x36)")
    lines.append(cw32(vtx1_hi, 0x3C080009))
    lines.append(cw32(y1, 0x340800E4))
    lines.append(cw32(vtx4_hi, 0x3C08002D))
    lines.append(cw32(y2, 0x34080108))

    lines.append(f"_C0  Icon X position (default 8)")
    lines.append(cw16(icon_x_pos, 0x00000008))

    lines.append("_C0  Hide Crosshair")
    lines.append(cw32(crosshair_draw, 0x00000000))

    lines.append("_C0  Show Crosshair")
    # jal sceGeListEnQueue would need the original instruction
    # Read it from the binary instead of hardcoding
    offset_in_bin = crosshair_draw - 0x0891CAA0
    with open("bin/TARGET_CHANGE_JP.bin", "rb") as f:
        f.seek(offset_in_bin)
        original_instr = struct.unpack('<I', f.read(4))[0]
    lines.append(cw32(crosshair_draw, original_instr))

    for name, offsets in [("50%", cross_50), ("75%", cross_75), ("100%", cross_100)]:
        lines.append(f"_C0  Crosshair Size {name}")
        for addr, off in zip(cross_addrs, offsets):
            lines.append(cw32(addr, addi_instr(off)))

    cheats_file = os.path.join(os.path.dirname(__file__) or '.', "cheats.txt")
    with open(cheats_file, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print(f"  Written to {cheats_file}")


def patch_title(iso_path, new_title, max_len=128):
    """Patch the game title in PARAM.SFO inside the ISO."""
    sfo_offset, sfo_size = find_file_in_iso(iso_path, ["PSP_GAME", "PARAM.SFO"])
    title_bytes = new_title.encode('utf-8') + b'\x00'
    if len(title_bytes) > max_len:
        raise ValueError(f"Title too long: {len(title_bytes)} > {max_len}")
    # Pad with zeros to fill the full field
    title_bytes = title_bytes.ljust(max_len, b'\x00')
    # TITLE data is at offset 0x158 within PARAM.SFO
    title_iso_offset = sfo_offset + 0x158
    with open(iso_path, 'r+b') as f:
        f.seek(title_iso_offset)
        f.write(title_bytes)
    print(f"  Set title to: {new_title}")


def main():
    src_iso = os.path.expanduser("~/Documents/PPSSPP/ISOs/Monster Hunter Portable 2nd G FUC zeta.iso")
    dst_iso = os.path.expanduser("~/Downloads/FUComplete zeta patched.iso")

    print(f"Copying ISO...")
    shutil.copy2(src_iso, dst_iso)
    print(f"  -> {dst_iso}")

    print(f"Finding EBOOT.BIN in ISO...")
    eboot_offset, eboot_size = find_file_in_iso(dst_iso, ["PSP_GAME", "SYSDIR", "EBOOT.BIN"])
    print(f"  Found at offset 0x{eboot_offset:08X}, size {eboot_size} bytes")

    print(f"Applying patches...")
    patch_iso(dst_iso, eboot_offset)

    print(f"Patching title...")
    title = "MONSTER HUNTER FREEDOM UNITE COMPLETE v1.4.0"
    version_file = os.path.join(os.path.dirname(__file__) or '.', "version.txt")
    if os.path.exists(version_file):
        version = open(version_file).read().strip()
        if version:
            title += f" ({version})"
    patch_title(dst_iso, title)

    print(f"Generating cheats...")
    generate_cheats()

    print(f"Done!")


if __name__ == "__main__":
    main()
