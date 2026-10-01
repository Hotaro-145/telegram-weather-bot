import asyncio
from collections import defaultdict
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


def get_event_category(main_weather: str, desc: str, weather_id: int):
    """Categorize weather events into standard types with emoji and priority."""
    main_lower = main_weather.lower()
    desc_lower = desc.lower()

    if 200 <= weather_id < 300 or "thunderstorm" in main_lower or "thunderstorm" in desc_lower:
        return ("Thunderstorm", "⛈️", 1, "a thunderstorm")
    if 600 <= weather_id < 700 or "snow" in main_lower or "sleet" in desc_lower or "snow" in desc_lower:
        return ("Snow", "❄️", 2, "snow")
    if 500 <= weather_id < 600 or "rain" in main_lower or "rain" in desc_lower:
        return ("Rain", "🌧️", 3, "rain")
    if 300 <= weather_id < 400 or "drizzle" in main_lower or "drizzle" in desc_lower:
        return ("Drizzle", "🌦️", 4, "drizzle")
    if 700 <= weather_id < 800 or any(w in desc_lower for w in ["fog", "mist", "haze", "smoke", "dust", "sand", "ash"]):
        name = "Fog/Mist" if ("fog" in desc_lower or "mist" in desc_lower) else "Haze/Low Visibility"
        phrasing = "fog/mist" if ("fog" in desc_lower or "mist" in desc_lower) else "reduced visibility"
        return (name, "🌫️", 5, phrasing)
    return None


def extract_today_events(current_data: dict, today_items: list, upcoming_items: list, tz: timezone, local_now: datetime):
    """
    Extract significant weather events (Rain, Snow, Thunderstorm, Fog, High Winds, etc.)
    with their occurrence times and details for today.
    Returns: (summary_inline_str, detailed_bullet_lines)
    """
    events_by_type = defaultdict(list)

    # 1. Check current weather
    cur_weather = current_data.get("weather", [{}])[0]
    cur_id = cur_weather.get("id", 800)
    cur_main = cur_weather.get("main", "")
    cur_desc = cur_weather.get("description", "")
    cur_cat = get_event_category(cur_main, cur_desc, cur_id)
    if cur_cat:
        events_by_type[cur_cat].append(("now", clean_text(cur_desc.capitalize()), None))

    # 2. Check today's forecast intervals (or upcoming if late at night)
    items_to_check = today_items if today_items else upcoming_items
    for item_dt, item in items_to_check:
        t_str = item_dt.strftime("%I:%M %p")
        if not today_items and item_dt.date() > local_now.date():
            t_str = item_dt.strftime("%a %I:%M %p")

        item_w = item.get("weather", [{}])[0]
        w_id = item_w.get("id", 800)
        w_main = item_w.get("main", "")
        w_desc = item_w.get("description", "")
        cat = get_event_category(w_main, w_desc, w_id)
        pop = int(item.get("pop", 0) * 100) if item.get("pop") is not None else None

        if cat:
            events_by_type[cat].append((t_str, clean_text(w_desc.capitalize()), pop))

        # Check for high winds (>= 10.8 m/s = strong breeze/gale)
        wind_speed = item.get("wind", {}).get("speed", 0)
        wind_gust = item.get("wind", {}).get("gust", 0)
        if wind_speed >= 10.8 or wind_gust >= 15.0:
            speed_info = f"{wind_speed} m/s"
            if wind_gust >= 15.0:
                speed_info += f", gusts {wind_gust} m/s"
            wind_cat = ("High Wind", "💨", 6, "strong winds")
            events_by_type[wind_cat].append((t_str, f"Gusts up to {speed_info}", None))

    if not events_by_type:
        general_desc = cur_desc.capitalize() if cur_desc else "Clear sky"
        summary_str = f"Today there is no rain or adverse weather expected (mostly {clean_text(general_desc)})"
        detailed_lines = [f"• ✨ *No rain or adverse weather expected today* (mostly {clean_text(general_desc)})."]
        return summary_str, detailed_lines

    sorted_cats = sorted(events_by_type.keys(), key=lambda c: c[2])
    detailed_lines = []
    short_summaries = []

    for cat in sorted_cats:
        cat_name, emoji, _, phrasing = cat
        occurrences = events_by_type[cat]

        times = []
        descs_set = set()
        max_pop = 0

        for t_str, d_str, pop in occurrences:
            if t_str not in times:
                times.append(t_str)
            if d_str and "gust" not in d_str.lower():
                descs_set.add(d_str)
            if pop and pop > max_pop:
                max_pop = pop

        times_str = ", ".join(times)
        descs_str = f" ({', '.join(sorted(descs_set))})" if descs_set else ""

        if "now" in times:
            other_times = [t for t in times if t != "now"]
            if other_times:
                phrase = f"Today there is {phrasing} happening now, and also at {', '.join(other_times)}{descs_str}"
            else:
                phrase = f"Today there is {phrasing} happening right now{descs_str}"
        else:
            time_word = "at" if len(times) == 1 else "multiple times at"
            phrase = f"Today there will be {phrasing} {time_word} {times_str}{descs_str}"

        short_summaries.append(f"{emoji} {phrase}")

        detail_line = f"• {emoji} *{cat_name}:* {phrase}"
        if max_pop > 0:
            detail_line += f" — 🌧️ {max_pop}% chance"
        detailed_lines.append(detail_line)

    summary_str = "; ".join(short_summaries)
    return summary_str, detailed_lines


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

    # Extract Today's Weather Events (Rain, Storms, Snow, High Winds, Fog, etc.)
    summary_event_str, detailed_event_lines = extract_today_events(
        current_data, today_items, upcoming_items, tz, local_now
    )

    lines = [
        f"🌍 *Weather Report for {location_title}*",
        f"📅 *Date:* {date_str}",
        f"⏰ *Local Time:* {time_str}\n",
        f"🌡️ *Temperature:* {temp}°C (Feels like {feels_like}°C)",
        f"📊 *Today's Range:* High {day_max}°C / Low {day_min}°C",
        f"{emoji} *Condition:* {condition}",
        f"📢 *Today's Events:* {summary_event_str}",
        f"💧 *Humidity:* {humidity}%",
        f"🌬️ *Pressure:* {pressure} hPa",
        f"💨 *Wind:* {wind_str}",
        f"👁️ *Visibility:* {visibility_str}",
        f"☁️ *Cloud Cover:* {clouds}%",
        f"🌅 *Sunrise:* {sunrise_str}  |  🌇 *Sunset:* {sunset_str}",
    ]

    # Detailed Events Section
    lines.append("\n━━━━━━━━━━━━━━━━━━━━")
    lines.append("📢 *Today's Expected Events & Alerts:*")
    for ev_line in detailed_event_lines:
        lines.append(ev_line)

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
    # If the user passed a city argument to /start (e.g. /start Tokyo)
    if context.args:
        await weather(update, context)
        return

    txt = (
        "☀️ *Welcome to your Weather Assistant!* 🌧️\n\n"
        "I provide the **complete daily weather report** and **today's forecast** for any location worldwide for the present date!\n\n"
        "✨ *Features in the daily report:*\n"
        "• 📅 *Present Date & Local Time:* Accurately calculated for the city's timezone\n"
        "• 🌡️ *Temperature:* Current temp & Feels-like temp\n"
        "• 📊 *Today's Range:* Daily High & Low temperatures\n"
        "• 📢 *Today's Weather Events:* Live alerts for rain, thunderstorms, snow, fog, high winds with exact times & multiple occurrences\n"
        "• ☁️ *Live Condition:* With day/night responsive emojis\n"
        "• 💧 *Atmospheric Metrics:* Humidity, Pressure, Visibility & Cloud cover\n"
        "• 💨 *Wind Speed & Direction:* With compass bearings (e.g. NE, SSW)\n"
        "• 🌅 *Sun Cycle:* Local Sunrise & Sunset times\n"
        "• ⏳ *Today's Timeline:* 3-hour forecast intervals with rain probabilities\n\n"
        "🚀 *How to use:*\n"
        "• `/weather <city>` — e.g. `/weather Tokyo`\n"
        "• `/today <city>` — e.g. `/today London`\n"
        "• `/start <city>` — e.g. `/start New York`\n"
        "• Or simply send the city name directly in the chat!\n\n"
        "Go ahead and type `/weather <your_city>` now! ⬇️"
    )
    await update.message.reply_text(txt, parse_mode="Markdown")


async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        city = " ".join(context.args)
    elif update.message and update.message.text and not update.message.text.startswith("/"):
        city = update.message.text.strip()
    else:
        await update.message.reply_text(
            "Please provide a city name! Example: `/weather Tokyo`",
            parse_mode="Markdown"
        )
        return

    report = await fetch_weather(city)
    await update.message.reply_text(report, parse_mode="Markdown")


if __name__ == '__main__':
    Keep_alive()

    application = ApplicationBuilder().token(TELEGRAM_API).build()

    start_handler = CommandHandler('start', start)
    weather_handler = CommandHandler('weather', weather)
    today_handler = CommandHandler('today', weather)
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, weather)

    application.add_handler(start_handler)
    application.add_handler(weather_handler)
    application.add_handler(today_handler)
    application.add_handler(message_handler)

    application.run_polling()
