import logging
import os
import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from keep_alive import Keep_alive

OPENWEATHER_API_KEY=os.environ.get('OPENWEATHER_API_KEY')
TELEGRAM_API=os.environ.get('TELEGRAM_API')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)



async def fetch_weather(city:str):
    url=f"https://api.openweathermap.org/data/2.5/weather"

    params={
        "q": city,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)

    if response.status_code==404:
        return f"Failed ❌ not find the city: {params['q']}, check spelling.\n"
    elif response.status_code!=200:
        return "⚠️ Failed to fetch weather data. Please try again later.\n"

    data = response.json()
    city_name = data["name"]
    country = data["sys"]["country"]
    temp = data["main"]["temp"]
    feels_like = data["main"]["feels_like"]
    humidity = data["main"]["humidity"]
    description = data["weather"][0]["description"].capitalize()
    wind_speed = data["wind"]["speed"]

    return (
        f"🌍 *Weather in {city_name}, {country}*\n"
        f"🌡️ *Temperature:* {temp}°C (Feels like {feels_like}°C)\n"
        f"☁️ *Condition:* {description}\n"
        f"💧 *Humidity:* {humidity}%\n"
        f"💨 *Wind Speed:* {wind_speed} m/s"
    )
            



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt=(
        "☀️ **Hey there! I'm your local Weather Assistant!** 🌧️\n\n"
        "Need to check if you need an umbrella or sunglasses today?\n\n"
        "Just drop a ( /weather city_name ) in the chat below, and I'll fetch the live temperature, humidity, and forecast for you in seconds!\n\n"
        "Go ahead—type /weather city_name now! ⬇️\n"
        "💡 *Tip: Check spelling if a city isn't recognized.*"
    )

    await context.bot.send_message(chat_id=update.effective_chat.id, text=txt)



async def  weather(update: Update, context:ContextTypes.DEFAULT_TYPE):
    if context.args==[]:
        await update.message.reply_text("Please provide a city name! Example: `/weather Tokyo`", parse_mode="Markdown")
        return

    city = " ".join(context.args)
    report = await fetch_weather(city)
    await update.message.reply_text(report, parse_mode="Markdown")




if __name__ == '__main__':

    Keep_alive()

    application = ApplicationBuilder().token(TELEGRAM_API).build()
    
    start_handler = CommandHandler('start', start)

    start_handler_2 = CommandHandler('weather', weather)

    application.add_handler(start_handler)

    application.add_handler(start_handler_2)
    application.run_polling()