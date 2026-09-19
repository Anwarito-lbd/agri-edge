# Pi bootstrap — Vocular hardware → agri-edge

**Hardware:** Raspberry Pi 5 + Camera Module 3 (same as Vocular)  
**Owner:** Anwar — software runs from the laptop once the Pi is on the network.

## Critical OS note
Vocular used **QNX**. agri-edge needs **64-bit Raspberry Pi OS Bookworm**.
Keep QNX on one SD card; use a **second microSD** for Bookworm so you can switch back.

## What you do (physical only)
1. Flash Bookworm 64-bit with Raspberry Pi Imager.
2. In Imager: enable SSH, set username/password, set Wi‑Fi (or use Ethernet).
3. Seat Camera Module 3 ribbon (Pi 5 narrow connector — blue tab orientation).
4. Power on. Wait ~60s for boot.
5. Tell agri-edge bot: **"Pi is on"** (and hostname if not `raspberrypi.local`).

## What the bot does after that
1. Find Pi on LAN (`raspberrypi.local` or IP).
2. Copy `agricultrul` (no vendor/weights bulk if possible).
3. Run `bash scripts/pi_setup.sh`.
4. Camera smoke test (`rpicam-hello`).
5. Channel-order check (red target).
6. Green-on-brown smoke capture.
7. Report results + next (reflectance panel / field walk).

## Do not buy again
Pi 5 + Camera Module 3 — you have them.

## Still useful
Active cooler, 27W PSU, spare SD, reflectance panel.
