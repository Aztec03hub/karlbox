# Karlbox Fresh Deployment

Date: 12/6/2022 Tuesday

## Flash the board

1. Connect the MicroUSB cable.
2. Connect the jumper to enter Force Recovery Mode.
3. Plug in internet Ethernet to *onboard* Ethernet Port.
4. Connect the mouse/keyboard, and ethernet breakout.
5. DO NOT CONNECT THE HDMI CABLE YET
6. Connect TTL to RS232 Converter to W8 (40 pin header):

|TX2 NX|Description|TTL-RS232|
|------|-----------|---------|
|[Pin 1]|+3V3|VCC|
|[Pin 6]|GND|GND|
|[Pin 8]|TX (UART1, dev/ttyTHS2)|TX|
|[Pin 10]|RX (UART1, dev/ttyTHS2)|RX|

7. Plug in the tx2 nx, then check on host if it's in Force Recovery Mode:
    * `watch lsusb`
    * Press `Ctrl-C`
8. Flash the board:
    * To SKIP building a fresh image, and use the premade system.img:
        ```
        sudo ./flash.sh -r jetson-xavier-nx-devkit-tx2-nx mmcblk0p1
        ```
    * To build a FRESH system image:
        ```
        sudo ./flash.sh jetson-xavier-nx-devkit-tx2-nx mmcblk0p1
        ```
9. Prepare board for Initial System Setup:
    * Remove power cable
    * Remove jumper
    * Connect HDMI Cable
    * Power up the system.

## IF DIRECT FLASHING -PREMADE- IMAGE, CHANGE HOSTNAME AND HOSTS FILES

1. Change the Hostname, replace old name with new name:
    ```
    sudo nano /etc/hostname
    ```

2. Change the Hosts file, replace old name with new name:
    ```
    sudo nano /etc/hosts
    ```

3. Reboot:
    `sudo reboot`

### YOU MAY STOP HERE, SYSTEM IS FULLY DEPLOYED
