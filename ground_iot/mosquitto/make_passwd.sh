#!/usr/bin/env bash
# Create ground_iot/mosquitto/passwd with one user per role in the ACL.
# Prompts for each password; the file is gitignored and never committed.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
passwd_file="$here/passwd"
: > "$passwd_file"

for user in sensor agriedge nodered; do
  read -rsp "Password for MQTT user '$user': " pw
  echo
  docker run --rm -v "$here:/work" eclipse-mosquitto:2 \
    mosquitto_passwd -b /work/passwd "$user" "$pw"
done
chmod 600 "$passwd_file"
echo "Wrote $passwd_file"
