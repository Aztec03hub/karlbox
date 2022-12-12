#!/bin/bash

echo "[X11] Disabling Energy Star Features" | systemd-cat -t kioskService -p info
xset -dpms
echo "[X11] Disabling Screen Saver" | systemd-cat -t kioskService -p info
xset s off
#echo "[X11] Adding localhost and localuser to xhost" | systemd-cat -t kioskService -p info
echo "[sudo] openbox-session" | systemd-cat -t kioskService -p info

openbox-session &
start-pulseaudio-x11

echo "Entering While Loop" | systemd-cat -t kioskService -p info

while true; do
 sleep 5
 rm -rf ~/.{config,cache}/chromium/
 chromium-browser '127.0.0.1:5000' --kiosk --password-store=basic --no-first-run --enable-logging=stderr --v=1 > ~/chromiumlog.txt 2>&1
done
