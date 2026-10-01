import asyncio
from datetime import datetime, timezone, timedelta
import logging
import os
import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from keep_alive import Keep_alive

OPENWEATHER_API_KEY = os.environ.get('OPENWEATHER_API_KEY')
TELEGRAM_API = os.environ.get('TELEGRAM_API')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


def clean_text(text: str) -> str:
    """Clean markdown-sensitive characters to prevent parsing issues."""
    if not text:
        return ""
    return str(text).replace("*", "").replace("`", "'").replace("_", " ")


def get_weather_emoji(description: str, is_day: bool = True) -> str:
    """Return an appropriate emoji for the weather condition."""
    desc = description.lower()
    if "thunderstorm" in desc:
        return "⛈️"
    elif "drizzle" in desc:
        return "🌦️"
    elif "rain" in desc:
        return "🌧️"
    elif "snow" in desc or "sleet" in desc:
        return "❄️"
    elif "clear" in desc:
        return "☀️" if is_day else "🌙"
    elif "few clouds" in desc or "scattered clouds" in desc:
        return "⛅" if is_day else "☁️"
    elif "clouds" in desc:
        return "☁️"
    elif any(w in desc for w in ["mist", "smoke", "haze", "fog", "dust", "sand", "ash"]):
        return "🌫️"
    elif "tornado" in desc or "squall" in desc:
        return "🌪️"
    return "🌤️"


def get_wind_direction(deg: float) -> str:
    """Convert wind degrees to compass direction."""
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = round(deg / 22.5) % 16
    return directions[idx]


def format_full_weather_report(current_data: dict, forecast_data: dict = None) -> str:
    """Format a detailed full weather report for the location's present date."""
    raw_city = current_data.get("name", "Unknown")
    raw_country = current_data.get("sys", {}).get("country", "")
    city_name = clean_text(raw_city)
    country = clean_text(raw_country)
    location_title = f"{city_name}, {country}" if country else city_name

    tz_offset = current_data.get("timezone", 0)
    tz = timezone(timedelta(seconds=tz_offset))

    # Present local date and time of the location
    current_dt = current_data.get("dt", 0)
    local_now = datetime.fromtimestamp(current_dt, tz=tz)
    date_str = local_now.strftime("%A, %d %B %Y")
    time_str = local_now.strftime("%I:%M %p")

    # Current weather metrics
    main = current_data.get("main", {})
    temp = round(main.get("temp", 0), 1)
    feels_like = round(main.get("feels_like", 0), 1)
    humidity = main.get("humidity", 0)
    pressure = main.get("pressure", 0)

    weather_desc_raw = current_data["weather"][0]["description"] if current_data.get("weather") else "Clear"
    condition = clean_text(weather_desc_raw.capitalize())

    # Sunrise and Sunset times in local timezone
    sys_data = current_data.get("sys", {})
    sunrise_ts = sys_data.get("sunrise")
    sunset_ts = sys_data.get("sunset")
    is_day = True
    sunrise_str = "N/A"
    sunset_str = "N/A"

    if sunrise_ts and sunset_ts:
        is_day = sunrise_ts <= current_dt <= sunset_ts
        sunrise_str = datetime.fromtimestamp(sunrise_ts, tz=tz).strftime("%I:%M %p")
        sunset_str = datetime.fromtimestamp(sunset_ts, tz=tz).strftime("%I:%M %p")

    emoji = get_weather_emoji(weather_desc_raw, is_day)

    # Wind details
    wind = current_data.get("wind", {})
    wind_speed = wind.get("speed", 0)
    wind_deg = wind.get("deg")
    wind_dir = get_wind_direction(wind_deg) if wind_deg is not None else ""
    wind_str = f"{wind_speed} m/s ({wind_dir})" if wind_dir else f"{wind_speed} m/s"

    # Visibility & Cloud cover
    visibility = current_data.get("visibility")
    visibility_str = f"{round(visibility / 1000, 1)} km" if visibility is not None else "N/A"
    clouds = current_data.get("clouds", {}).get("all", 0)

    # Forecast timeline for the present date
    today_items = []
    upcoming_items = []
    if forecast_data and "list" in forecast_data:
        for item in forecast_data["list"]:
            item_dt = datetime.fromtimestamp(item.get("dt", 0), tz=tz)
            if item_dt.date() == local_now.date():
                today_items.append((item_dt, item))
            elif item_dt.date() > local_now.date() and len(upcoming_items) < 3:
                upcoming_items.append((item_dt, item))

    # Calculate daily High and Low temperatures for today
    all_today_mins = [main.get("temp_min", temp)]
    all_today_maxs = [main.get("temp_max", temp)]
    for _, item in today_items:
        all_today_mins.append(item.get("main", {}).get("temp_min", temp))
        all_today_maxs.append(item.get("main", {}).get("temp_max", temp))

    day_min = round(min(all_today_mins), 1)
    day_max = round(max(all_today_maxs), 1)

    lines = [
        f"🌍 *Weather Report for {location_title}*",
        f"📅 *Date:* {date_str}",
        f"⏰ *Local Time:* {time_str}\n",
        f"🌡️ *Temperature:* {temp}°C (Feels like {feels_like}°C)",
        f"📊 *Today's Range:* High {day_max}°C / Low {day_min}°C",
        f"{emoji} *Condition:* {condition}",
        f"💧 *Humidity:* {humidity}%",
        f"🌬️ *Pressure:* {pressure} hPa",
        f"💨 *Wind:* {wind_str}",
        f"👁️ *Visibility:* {visibility_str}",
        f"☁️ *Cloud Cover:* {clouds}%",
        f"🌅 *Sunrise:* {sunrise_str}  |  🌇 *Sunset:* {sunset_str}",
    ]

    # Forecast intervals section
    if today_items:
        lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        lines.append("⏳ *Today's Forecast Timeline:*")
        for item_dt, item in today_items:
            t_str = item_dt.strftime("%I:%M %p")
            i_temp = round(item.get("main", {}).get("temp", 0), 1)
            raw_i_desc = item["weather"][0]["description"] if item.get("weather") else ""
            i_desc = clean_text(raw_i_desc.capitalize())
            i_pod = item.get("sys", {}).get("pod", "d") == "d"
            i_emoji = get_weather_emoji(raw_i_desc, i_pod)
            i_pop = int(item.get("pop", 0) * 100)
            lines.append(f"• `{t_str}`: {i_temp}°C | {i_emoji} {i_desc} | 🌧️ {i_pop}%")
    elif upcoming_items:
        lines.append("\n━━━━━━━━━━━━━━━━━━━━")
        lines.append("⏳ *Upcoming Forecast (Overnight/Tomorrow):*")
        for item_dt, item in upcoming_items:
            t_str = item_dt.strftime("%a %I:%M %p")
            i_temp = round(item.get("main", {}).get("temp", 0), 1)
            raw_i_desc = item["weather"][0]["description"] if item.get("weather") else ""
            i_desc = clean_text(raw_i_desc.capitalize())
            i_pod = item.get("sys", {}).get("pod", "d") == "d"
            i_emoji = get_weather_emoji(raw_i_desc, i_pod)
            i_pop = int(item.get("pop", 0) * 100)
            lines.append(f"• `{t_str}`: {i_temp}°C | {i_emoji} {i_desc} | 🌧️ {i_pop}%")

    return "\n".join(lines)


async def fetch_weather(city: str) -> str:
    if not OPENWEATHER_API_KEY:
        return "⚠️ OpenWeather API key is not configured. Please set the OPENWEATHER_API_KEY environment variable.\n"

    params = {
        "q": city,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
    }
    current_url = "https://api.openweathermap.org/data/2.5/weather"
    forecast_url = "https://api.openweathermap.org/data/2.5/forecast"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            current_resp, forecast_resp = await asyncio.gather(
                client.get(current_url, params=params),
                client.get(forecast_url, params=params),
                return_exceptions=True
            )
    except Exception as e:
        logging.error(f"Network error while fetching weather: {e}")
        return "⚠️ Failed to connect to weather service. Please try again later.\n"

    if isinstance(current_resp, Exception) or current_resp.status_code != 200:
        if not isinstance(current_resp, Exception) and current_resp.status_code == 404:
            safe_city = clean_text(city)
            return f"❌ Could not find city: *{safe_city}*. Please check the spelling.\n"
        return "⚠️ Failed to fetch weather data. Please try again later.\n"

    current_data = current_resp.json()
    forecast_data = (
        forecast_resp.json()
        if (not isinstance(forecast_resp, Exception) and forecast_resp.status_code == 200)
        else None
    )

    return format_full_weather_report(current_data, forecast_data)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (
        "☀️ *Hey there! I'm your local Weather Assistant!* 🌧️\n\n"
        "Need the complete weather report and today's forecast for any city?\n\n"
        "Just drop `/weather <city>` in the chat below, and I'll fetch the full report for the present date—including temperature, highs & lows, humidity, wind, sunrise/sunset, and today's timeline!\n\n"
        "Example: `/weather Tokyo` ⬇️\n"
        "💡 *Tip: Check spelling if a city isn't recognized.*"
    )
    await update.message.reply_text(txt, parse_mode="Markdown")


async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Please provide a city name! Example: `/weather Tokyo`",
            parse_mode="Markdown"
        )
        return

    city = " ".join(context.args)
    report = await fetch_weather(city)
    await update.message.reply_text(report, parse_mode="Markdown")


if __name__ == '__main__':
    Keep_alive()

    application = ApplicationBuilder().token(TELEGRAM_API).build()

    start_handler = CommandHandler('start', start)
    weather_handler = CommandHandler('weather', weather)
    today_handler = CommandHandler('today', weather)

    application.add_handler(start_handler)
    application.add_handler(weather_handler)
    application.add_handler(today_handler)

    application.run_polling()
