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

    # VERT_HOOK.bin -> 0x0891D740
    with open("bin/VERT_HOOK.bin", "rb") as f:
        patches.append((0x0891D740 - EBOOT_BASE, f.read()))

    # Hook 3: at 0x08886CA4 (replace 2 instructions with j + nop)
    # j 0x0891D740 = 0x0A2475D0
    patches.append((0x08886CA4 - EBOOT_BASE, b'\xD0\x75\x24\x0A\x00\x00\x00\x00'))

    with open(iso_path, 'r+b') as f:
        for file_offset, data in patches:
            iso_offset = eboot_offset + file_offset
            f.seek(iso_offset)
            f.write(data)
            print(f"  Patched {len(data):>5} bytes at EBOOT+0x{file_offset:06X} (ISO offset 0x{iso_offset:08X})")


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
    src_iso = os.path.expanduser("~/Downloads/Monster Hunter Portable 2nd G FUC gamma.iso")
    dst_iso = os.path.expanduser("~/Downloads/Monster Hunter Portable 2nd G FUC gamma patched.iso")

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

    print(f"Done!")


if __name__ == "__main__":
    main()
