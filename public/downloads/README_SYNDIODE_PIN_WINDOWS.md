# Syndiode Swarm Signal for Windows

Download:

https://www.syndiode.com/downloads/syndiode-pin-light-control.exe

This is the Windows companion app for the SyndiodePin light firmware. It uses
the Swarm Oracle style: one large **Swarm Signal** button, a Firebase readback
test, and the same local light pattern logic as the Android app.

It sends the selected pattern to:

- a Syndiode ESP32 pin through Firebase Realtime Database
- a local WLED-compatible node through `http://<host>/json/state`

The app stores its settings under `%APPDATA%\SyndiodePin\settings.json`.

## Controls

- Save pin: stores the ESP32 pin device id and checks/creates its Firebase node.
- Swarm Signal: generates and sends one local light pattern.
- Firebase test: reads back the current pin state from Firebase.
- Soft, Active, Bright: manual signal intensity variants.
- Advanced WLED: optional local WLED host/IP support.
- Reset WiFi: sends `devices/<pin_id>/status/reset_wifi = true`.

## Build locally

Run this from the `public/downloads` folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_syndiode_pin_light_control_exe.ps1
```

The build uses a temporary virtual environment in `%TEMP%` so the global Python
installation stays unchanged.
