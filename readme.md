# 🌤️ Telegram Weather Bot

A lightweight, asynchronous Telegram bot that provides live weather updates for any city worldwide using the OpenWeatherMap API.

## ✨ Features
* 🌍 **Instant Weather Lookup:** Send any city name to get live temperature, humidity, wind speed, and weather conditions.
* ⚡ **Command Support:** Supports `/start` and `/weather <city>` commands.
* 🟢 **24/7 Free Uptime:** Includes an integrated Flask `keep_alive` server designed for cloud platforms like Render.
* 🔒 **Secure Configuration:** Uses environment variables for API tokens and credentials.

## 🛠️ Tech Stack
* **Language:** Python 3.10+
* **Framework:** `python-telegram-bot`
* **HTTP Client:** `httpx`
* **API:** OpenWeatherMap
* **Keep-Alive Server:** Flask