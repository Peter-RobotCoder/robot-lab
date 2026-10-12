"""How late does asyncio wake up on this machine? Run it on the class server (and on a laptop) before trusting a
60 Hz loop there:

    python3 engine/bench_timer.py            (over ssh: ssh robotlab python3 - < engine/bench_timer.py)

It runs two loops for five seconds each and prints how late each wake-up was. The games' loops use the deadline
pattern, so what matters is the second set of numbers: a typical lateness of a millisecond or two is fine; tens of
milliseconds means the machine is overloaded or its timer is coarse.
"""
import asyncio
import statistics
import time

STEP = 1 / 60


async def naive(seconds=5.0):
    """sleep(STEP) every time: the lateness of each sleep adds up, so the loop drifts."""
    t0 = time.perf_counter()
    ticks = 0
    while time.perf_counter() - t0 < seconds:
        await asyncio.sleep(STEP)
        ticks += 1
    wanted = seconds / STEP
    print(f"naive loop:    {ticks} ticks in {seconds:.0f} s (wanted {wanted:.0f}): "
          f"{(wanted - ticks) * STEP * 1000:.0f} ms behind by the end")


async def deadline(seconds=5.0):
    """The games' pattern: sleep until the next deadline, so lateness never accumulates."""
    t0 = next_t = time.perf_counter()
    late = []
    while time.perf_counter() - t0 < seconds:
        next_t += STEP
        await asyncio.sleep(max(0.0, next_t - time.perf_counter()))
        late.append((time.perf_counter() - next_t) * 1000)
    late.sort()
    print(f"deadline loop: {len(late)} ticks in {seconds:.0f} s; wake-up lateness median {statistics.median(late):.2f} ms, "
          f"90% {late[int(len(late) * 0.9)]:.2f} ms, worst {late[-1]:.2f} ms")


async def main():
    import os
    import platform
    import sys
    print(f"Python {sys.version.split()[0]} on {platform.platform()}")
    await naive()
    await deadline()
    if os.name == "nt":  # the games' servers ask Windows for a 1 ms clock (see fine_timer in the servers)
        import ctypes
        ctypes.windll.winmm.timeBeginPeriod(1)
        print("...and with Windows asked for a 1 ms clock:")
        await deadline()


if __name__ == "__main__":
    asyncio.run(main())
