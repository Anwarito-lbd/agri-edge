# Flash Bookworm for agri-edge (Pi 5 + Camera Module 3)

**Use a spare microSD.** Keep the Vocular QNX card untouched.

## 1. Insert spare microSD into your PC (USB reader)

## 2. Open Raspberry Pi Imager

## 3. Choose device / OS / storage
- **Raspberry Pi Device:** Raspberry Pi 5
- **Operating System:** Raspberry Pi OS (64-bit) — Bookworm (not Lite if you want desktop; **Lite is fine** for headless agri-edge)
- **Storage:** your spare microSD (double-check size/label — do not pick the wrong disk)

## 4. Edit settings (gear / OS customisation) — required
Enable:
- **Set hostname:** `agri-edge` (or leave `raspberrypi`)
- **Enable SSH:** Use password authentication
- **Username:** `pi` (or your choice — tell the bot)
- **Password:** set one you’ll remember (tell the bot when Pi is online — or we’ll use SSH key later)
- **Configure wireless LAN:** your Wi‑Fi SSID + password, country **CA**
- **Locale:** America/Toronto (or your locale)

Save → **Yes** write → wait until Imager says done → **eject safely**.

## 5. On the Pi
1. Insert Bookworm SD
2. Seat Camera Module 3 ribbon (Pi 5 narrow connector)
3. Power on (27W PSU if you have it)
4. Wait ~60–90 seconds
5. Message the bot: **“Pi is on”**

Then the bot runs `discover_pi.ps1` → `bootstrap_pi.ps1` (copy repo, `pi_setup.sh`, camera + GoB smoke).
