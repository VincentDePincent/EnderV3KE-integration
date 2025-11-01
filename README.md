# EnderV3KE-integration
A simple, fully local HA integration that uses the web-interface of your Ender V3KE to display print statistics in Home Assistant.

To run the bridge securely, create a `.env` file next to the script containing the required secrets (for example: `MQTT_USER=youruser`, `MQTT_PASS=averylongrandomstring`, and any broker overrides) and keep the values private; the program will refuse to start until these credentials are supplied.

After writing the file, restrict it to your account only (e.g. `chmod 600 .env`) and avoid committing it—this repository's `.gitignore` already excludes `.env`, so your secrets stay out of version control.
