“””
TShirt Mockup Bot - Telegram Bot para generar imágenes de modelos con remeras
Conecta con APIs gratuitas de generación de imágenes (Hugging Face Inference API)
“””

import os
import io
import logging
import asyncio
import base64
import httpx
from telegram import Update, InputFile
from telegram.ext import (
Application,
CommandHandler,
MessageHandler,
filters,
ContextTypes,
)
from dotenv import load_dotenv
from prompts import build_prompt

load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
format=”%(asctime)s | %(levelname)s | %(name)s | %(message)s”,
level=logging.INFO,
)
logger = logging.getLogger(**name**)

# ── Config ─────────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN = os.getenv(“TELEGRAM_TOKEN”)
HF_TOKEN = os.getenv(“HF_TOKEN”)          # Hugging Face token (gratuito)

# Modelos gratuitos en Hugging Face (en orden de preferencia)

HF_MODELS = [
“stabilityai/stable-diffusion-xl-base-1.0”,
“runwayml/stable-diffusion-v1-5”,
“CompVis/stable-diffusion-v1-4”,
]

HF_API_URL = “https://api-inference.huggingface.co/models/{model}”
TIMEOUT = 120  # segundos

# ── Generación de imagen ───────────────────────────────────────────────────────

async def generate_image_hf(prompt: str, image_bytes: bytes) -> bytes | None:
“””
Intenta generar imagen usando Hugging Face Inference API (img2img vía pipeline).
Si el modelo está cargando o sin tokens devuelve None.
“””
headers = {“Authorization”: f”Bearer {HF_TOKEN}”}

```
# Encode image to base64 for img2img
img_b64 = base64.b64encode(image_bytes).decode("utf-8")

payload = {
    "inputs": prompt,
    "parameters": {
        "num_inference_steps": 30,
        "guidance_scale": 7.5,
        "strength": 0.65,          # cuánto se aleja del mockup original
        "negative_prompt": (
            "deformed, blurry, bad anatomy, disfigured, poorly drawn face, "
            "mutation, ugly, duplicate, morbid, out of frame, extra limbs, "
            "missing arms, missing legs, logo, watermark, text, cropped"
        ),
    },
    "image": img_b64,
}

for model in HF_MODELS:
    url = HF_API_URL.format(model=model)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=payload)

        if resp.status_code == 200:
            logger.info(f"✅ Imagen generada con modelo: {model}")
            return resp.content

        elif resp.status_code == 503:
            logger.warning(f"⏳ Modelo {model} cargando, probando siguiente...")
            continue

        elif resp.status_code == 429:
            logger.error("❌ Sin tokens gratuitos disponibles en Hugging Face.")
            return None

        else:
            logger.warning(f"⚠️ {model} respondió {resp.status_code}: {resp.text[:200]}")
            continue

    except httpx.TimeoutException:
        logger.warning(f"⏱️ Timeout con {model}, probando siguiente...")
        continue
    except Exception as e:
        logger.error(f"Error con {model}: {e}")
        continue

return None
```

# ── Handlers de Telegram ───────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
await update.message.reply_text(
“👕 *TShirt Mockup Bot*\n\n”
“Enviame una foto de tu mockup (remera con diseño) y voy a generar “
“una imagen de modelo usando esa remera, lista para Instagram o web.\n\n”
“📌 *Cómo usar:*\n”
“1. Enviame la imagen del mockup directamente\n”
“2. (Opcional) Agregá una descripción como caption:\n”
“   • `hombre` / `mujer` / `unisex`\n”
“   • `casual` / `urbano` / `deportivo`\n”
“   • `interior` / `exterior`\n\n”
“Ejemplo de caption: `mujer casual exterior`\n\n”
“⚡ Usa la API gratuita de Hugging Face. Si no hay tokens disponibles te aviso.”,
parse_mode=“Markdown”,
)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
await update.message.reply_text(
“📋 *Comandos disponibles:*\n\n”
“/start - Bienvenida e instrucciones\n”
“/help - Este mensaje\n\n”
“📸 *Uso principal:*\n”
“Enviá una imagen (foto del mockup de tu remera). “
“Podés agregar un caption para personalizar:\n\n”
“• *Género:* `hombre`, `mujer`, `unisex`\n”
“• *Estilo:* `casual`, `urbano`, `deportivo`, `elegante`\n”
“• *Ambiente:* `interior`, `exterior`, `estudio`\n\n”
“🆓 *Servicio gratuito - limitado por tokens de Hugging Face*”,
parse_mode=“Markdown”,
)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
“”“Recibe foto del mockup y genera imagen de modelo.”””
message = update.message
caption = message.caption or “”

```
# Mensaje de "en proceso"
processing_msg = await message.reply_text("⏳ En proceso…")

try:
    # Descargar la imagen de mayor resolución
    photo = message.photo[-1]
    photo_file = await photo.get_file()
    image_bytes = await photo_file.download_as_bytearray()

    # Construir prompt según caption del usuario
    prompt = build_prompt(caption)
    logger.info(f"Prompt generado: {prompt[:100]}...")

    # Generar imagen
    result_bytes = await generate_image_hf(prompt, bytes(image_bytes))

    if result_bytes is None:
        await processing_msg.delete()
        await message.reply_text(
            "😔 *Sin tokens disponibles*\n\n"
            "La API gratuita de Hugging Face llegó al límite de requests "
            "por hora. Probá de nuevo en unos minutos o mañana.\n\n"
            "💡 También podés conseguir un token gratis en "
            "https://huggingface.co/join y agregarlo al bot.",
            parse_mode="Markdown",
        )
        return

    # Enviar imagen generada
    await processing_msg.delete()
    bio = io.BytesIO(result_bytes)
    bio.name = "modelo_remera.png"
    await message.reply_photo(
        photo=InputFile(bio),
        caption=(
            "✅ *Imagen generada*\n"
            f"_Prompt usado: {prompt[:80]}..._"
        ),
        parse_mode="Markdown",
    )

except Exception as e:
    logger.error(f"Error procesando imagen: {e}", exc_info=True)
    await processing_msg.delete()
    await message.reply_text(
        "❌ Ocurrió un error al procesar la imagen. Intentá de nuevo."
    )
```

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
“”“Maneja imágenes enviadas como documento (mayor calidad).”””
doc = update.message.document
if not doc.mime_type or not doc.mime_type.startswith(“image/”):
await update.message.reply_text(
“⚠️ Por favor enviá una imagen (JPG, PNG) ya sea como foto o documento.”
)
return
# Redirigir al handler de fotos simulando el mismo flujo
await update.message.reply_text(
“📁 Imagen recibida como documento. “
“Para mejor experiencia, enviá la imagen directamente como *foto*.”,
parse_mode=“Markdown”,
)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
await update.message.reply_text(
“📸 Enviame una *foto* de tu mockup para generar la imagen del modelo.\n”
“Podés agregar un caption con el estilo deseado.”,
parse_mode=“Markdown”,
)

# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
if not TELEGRAM_TOKEN:
raise ValueError(“❌ TELEGRAM_TOKEN no está configurado en .env”)
if not HF_TOKEN:
raise ValueError(“❌ HF_TOKEN no está configurado en .env”)

```
app = Application.builder().token(TELEGRAM_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

logger.info("🤖 Bot iniciado y escuchando...")
app.run_polling(allowed_updates=Update.ALL_TYPES)
```

if **name** == “**main**”:
main()