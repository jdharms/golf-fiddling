"""Tests for the music engine export path (golf/core/audio.py)."""

import struct

import pytest

from golf.core import audio

ROM_PATH = "nes_open_us.nes"


@pytest.fixture(scope="module")
def rom():
    try:
        with open(ROM_PATH, "rb") as f:
            return f.read()
    except FileNotFoundError:
        pytest.skip(f"{ROM_PATH} not present")


# --------------------------------------------------------------------- NSF

def test_nsf_header(rom):
    nsf = audio.build_nsf(rom)
    assert nsf[:5] == b"NESM\x1a"
    assert nsf[5] == 1                       # version
    assert nsf[6] == audio.TRACK_COUNT == 23
    assert nsf[7] == 1                       # starting song
    load, init, play = struct.unpack_from("<HHH", nsf, 8)
    assert load == 0x8000
    assert init == 0xD000
    assert play == init + len(audio._NSF_STUB) - 3
    assert list(nsf[112:120]) == [0, 1, 2, 3, 4, 5, 5, 5]
    assert nsf[122] == 0 and nsf[123] == 0   # NTSC, no expansion audio
    assert len(nsf) == 0x80 + 6 * 0x1000


def test_nsf_maps_engine_and_samples(rom):
    """$8000 must land on AudioEngineMain and $C000 on the DPCM page."""
    nsf = audio.build_nsf(rom)
    body = nsf[0x80:]
    raw = rom[16:]
    assert body[0:0x4000] == raw[audio.BANK14_OFF:audio.BANK15_OFF]
    assert body[0x4000:0x5000] == raw[audio.BANK15_OFF:audio.BANK15_OFF + 0x1000]


def test_nsf_stub_runs_under_emulation(rom):
    """INIT must select the track and PLAY must drive the engine."""
    from py65.devices.mpu6502 import MPU

    nsf = audio.build_nsf(rom)
    init, play = struct.unpack_from("<HH", nsf, 10)
    body = nsf[0x80:]
    pages = [body[i * 0x1000:(i + 1) * 0x1000] for i in range(len(body) // 0x1000)]
    prg = bytearray(b"".join(pages[b] for b in nsf[112:120]))

    bus = audio._Bus(prg)
    mpu = MPU(memory=bus)
    mpu.sp = 0xFD
    # INIT must not clear the stack page or it could not return to the player.
    for i in range(0x0100, 0x0180):
        bus.ram[i] = 0xA5
    mpu.a, mpu.x = 0, 0                     # song 1 (0-based), NTSC
    audio._call(mpu, init)                  # raises if it never returns
    assert bus.ram[audio.MUSIC_REQUEST] == 1
    assert bus.ram[audio.SFX_ACTIVE] == 1
    assert all(bus.ram[i] == 0xA5 for i in range(0x0100, 0x0180))
    assert bus.ram[0x0200:0x0800] == bytes(0x600)   # everything else cleared

    for f in range(120):
        bus.frame = f
        audio._call(mpu, play)
    assert len(bus.writes) > 300
    assert {a for _, a, _ in bus.writes} >= {0x4000, 0x4004, 0x400A, 0x4015}


# ---------------------------------------------------------------- engine run

@pytest.mark.parametrize("track", [1, 4, 0x0A, 0x17])
def test_engine_runs_every_track(rom, track):
    writes = audio.run_engine(rom, track, 60)
    assert writes, f"track ${track:02X} produced no APU writes"
    assert all(0x4000 <= a <= 0x4017 for _, a, _ in writes)


def test_dmc_flag_gates_percussion(rom):
    with_dmc = audio.run_engine(rom, 1, 180, dmc=True)
    without = audio.run_engine(rom, 1, 180, dmc=False)
    dmc_regs = range(0x4010, 0x4014)
    assert any(a in dmc_regs for _, a, _ in with_dmc)
    assert not any(a in dmc_regs for _, a, _ in without)


# --------------------------------------------------------------- drum kit NSF

def test_drum_nsf_header(rom):
    nsf = audio.build_drum_nsf(rom)
    assert nsf[:5] == b"NESM\x1a"
    assert nsf[6] == audio.DMC_SAMPLE_COUNT == 10
    load, init, play = struct.unpack_from("<HHH", nsf, 8)
    assert (load, init, play) == (0x8000, audio._DRUM_INIT_ADDR, audio._DRUM_PLAY_ADDR)
    assert len(nsf) == 0x80 + 6 * 0x1000


@pytest.mark.parametrize("sid", range(1, 11))
def test_drum_nsf_plays_the_right_sample(rom, sid):
    """Each song must hand DmcUpdate the address, length and rate for its slot."""
    from py65.devices.mpu6502 import MPU

    nsf = audio.build_drum_nsf(rom)
    init, play = struct.unpack_from("<HH", nsf, 10)
    body = nsf[0x80:]
    pages = [body[i * 0x1000:(i + 1) * 0x1000] for i in range(len(body) // 0x1000)]
    prg = bytearray(b"".join(pages[b] for b in nsf[112:120]))

    bus = audio._Bus(prg)
    mpu = MPU(memory=bus)
    mpu.sp = 0xFD
    mpu.a, mpu.x = sid - 1, 0
    audio._call(mpu, init)
    for f in range(300):
        bus.frame = f
        audio._call(mpu, play)

    info = audio.dmc_sample_info(rom, sid)
    addr = [(f, v) for f, a, v in bus.writes if a == 0x4012]
    length = [v for _, a, v in bus.writes if a == 0x4013]
    rate = [v for _, a, v in bus.writes if a == 0x4010]
    assert addr and length and rate
    assert addr[0][1] == (info["address"] - 0xC000) // 64
    assert length[0] == (info["length"] - 1) // 16
    assert rate[0] & 0x0F == info["rate_index"]
    # repeats on a steady 48-frame cycle so it can be auditioned
    hits = [f for f, _ in addr]
    assert all(b - a == 48 for a, b in zip(hits, hits[1:]))


def test_drum_nsf_reproduces_the_cutoff(rom):
    """The engine must disable the DMC channel again once its frame counter expires."""
    from py65.devices.mpu6502 import MPU

    nsf = audio.build_drum_nsf(rom)
    init, play = struct.unpack_from("<HH", nsf, 10)
    body = nsf[0x80:]
    pages = [body[i * 0x1000:(i + 1) * 0x1000] for i in range(len(body) // 0x1000)]
    prg = bytearray(b"".join(pages[b] for b in nsf[112:120]))

    bus = audio._Bus(prg)
    mpu = MPU(memory=bus)
    mpu.sp = 0xFD
    mpu.a, mpu.x = 0, 0          # song 1 -> sample 1, runs 8 frames
    audio._call(mpu, init)
    for f in range(60):
        bus.frame = f
        audio._call(mpu, play)

    enable = [(f, v) for f, a, v in bus.writes if a == 0x4015]
    on = [f for f, v in enable if v & 0x10]
    off_after = [f for f, v in enable if not v & 0x10 and f > on[0]]
    frames = audio.dmc_sample_info(rom, 1)["frames"]
    assert on, "DMC channel was never enabled"
    assert off_after and off_after[0] - on[0] <= frames + 1
