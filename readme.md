# 🌤️ Telegram Weather Bot
https://t.me/chitandas_bot

A lightweight, asynchronous Telegram bot that provides live weather updates for any city worldwide using the OpenWeatherMap API.

## ✨ Features
* 🌍 **Full Daily Weather Report:** Send `/weather <city>` or `/today <city>` to get a complete report for the present date:
  * Present local date & time adjusted to the city's timezone
  * Current temperature & feels-like temperature
  * Daily temperature range (High / Low)
  * Weather conditions with contextual emojis (day/night aware)
  * Humidity, atmospheric pressure, cloud cover, and visibility
  * Wind speed & compass direction (e.g. `4.1 m/s (NE)`)
  * Local sunrise & sunset times
  * 3-hour forecast timeline throughout today (with rain chance %)
* ⚡ **Command Support:** Supports `/start`, `/weather <city>`, and `/today <city>`.
* 🟢 **24/7 Free Uptime:** Includes an integrated Flask `keep_alive` server designed for cloud platforms like Render.
* 🔒 **Secure Configuration:** Uses environment variables for API tokens and credentials.

## 🛠️ Tech Stack
* **Language:** Python 3.10+
* **Framework:** `python-telegram-bot`
* **HTTP Client:** `httpx`
* **API:** OpenWeatherMap
* **Keep-Alive Server:** Flask
