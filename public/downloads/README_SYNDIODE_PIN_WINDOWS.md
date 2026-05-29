# Syndiode Swarm Signal for Windows

Download:

https://www.syndiode.com/downloads/syndiode-pin-light-control.exe

This is the Windows companion app for the SyndiodePin light firmware. It uses
the Swarm Oracle style: one pin ID field, one large **Signal** field, and one
answer field where the light oracle speaks.

It sends the selected pattern to a Syndiode ESP32 pin through Firebase Realtime
Database.

The app stores its settings under `%APPDATA%\SyndiodePin\settings.json`.

## Firebase client key

The Windows source and EXE do not embed a Google/Firebase API key. Configure the
key locally with one of these options:

- set the `SYNDIODE_FIREBASE_API_KEY` environment variable
- put the key in `%APPDATA%\SyndiodePin\firebase_api_key.txt`
- add `firebase_api_key` to `%APPDATA%\SyndiodePin\settings.json`

Do not commit Firebase client keys to this repository. Rotate/restrict any key
that was ever exposed in Git history.

## Controls

- Pin ID: stores the ESP32 pin device id locally.
- Signal: generates and sends one local light pattern.
- Oracle answer: shows the phrase and color swatches for the generated pattern.

## Build locally

Run this from the `public/downloads` folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_syndiode_pin_light_control_exe.ps1
```

The build uses a temporary virtual environment in `%TEMP%` so the global Python
installation stays unchanged.
