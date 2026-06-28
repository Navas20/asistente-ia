import os
import httpx
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

API_URL = os.getenv("API_URL", "http://localhost:8000")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "cambia-este-token")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0"))

user_conversations = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        await update.message.reply_text("No autorizado")
        return
    user_conversations[update.effective_user.id] = None
    await update.message.reply_text(
        "J.A.R.V.I.S. v4.0 en línea.\n"
        "Memoria persistente + herramientas en vivo + subida de archivos.\n\n"
        "Comandos:\n"
        "/memoria — ver lo que sé de ti\n"
        "/nueva — nueva conversación\n"
        "/buscar <query> — buscar en internet\n"
        "/ejecutar <comando> — ejecutar comando\n"
        "/archivos — listar archivos subidos\n"
        "/olvidar — borrar mi memoria\n\n"
        "O solo háblame normal. Si necesito ejecutar algo, lo haré solo."
    )

async def memoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{API_URL}/memories",
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"}
            )
            if resp.status_code == 200:
                mems = resp.json().get("memories", {})
                if mems:
                    lines = ["📌 *Lo que sé de ti:*"]
                    for k, v in sorted(mems.items()):
                        lines.append(f"• *{k.replace('_', ' ').title()}*: {v}")
                    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
                else:
                    await update.message.reply_text("Aún no sé nada personal. Cuéntame cosas.")
            else:
                await update.message.reply_text(f"Error: {resp.status_code}")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usa: /buscar <consulta>")
        return
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{API_URL}/search",
                params={"query": query},
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"}
            )
            if resp.status_code == 200:
                results = resp.json().get("results", "Sin resultados")
                await update.message.reply_text(f"🔍 *Resultados para:* {query}\n\n{results}", parse_mode="Markdown")
            else:
                await update.message.reply_text(f"Error: {resp.status_code}")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def ejecutar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    cmd = " ".join(context.args)
    if not cmd:
        await update.message.reply_text("Usa: /ejecutar <comando>")
        return
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{API_URL}/execute",
                data={"command": cmd},
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                out = data.get("output", "(sin salida)")
                status = "✅" if data.get("success") else "❌"
                await update.message.reply_text(
                    f"{status} `{cmd}`\n```\n{out[:3000]}\n```",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(f"Error: {resp.status_code}")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def list_archivos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{API_URL}/files",
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"}
            )
            if resp.status_code == 200:
                files = resp.json().get("files", [])
                if files:
                    lines = ["📁 *Archivos:*"]
                    for f in files:
                        lines.append(f"• {f['name']} ({f['size']} bytes) — ID: `{f['id']}`")
                    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
                else:
                    await update.message.reply_text("No hay archivos subidos.")
            else:
                await update.message.reply_text(f"Error: {resp.status_code}")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    user_conversations[update.effective_user.id] = None
    await update.message.reply_text("[Nueva conversación. Memoria intacta.]")

async def forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{API_URL}/memories",
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"}
            )
            if resp.status_code == 200:
                for k in resp.json().get("memories", {}):
                    await client.delete(
                        f"{API_URL}/memories/{k}",
                        headers={"Authorization": f"Bearer {AUTH_TOKEN}"}
                    )
        await update.message.reply_text("[Memoria borrada.]")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    user_msg = update.message.text
    uid = update.effective_user.id
    payload = {"message": user_msg}
    if uid in user_conversations and user_conversations[uid]:
        payload["conversation_id"] = user_conversations[uid]

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{API_URL}/chat",
                json=payload,
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                user_conversations[uid] = data["conversation_id"]
                msg = data["response"]

                if data.get("tool_executed") and data.get("tool_output"):
                    msg += f"\n\n⚙️ *Ejecutado:* `{data['tool_command']}`\n```\n{data['tool_output'][:1500]}\n```"

                await update.message.reply_text(msg, parse_mode="Markdown")
            else:
                await update.message.reply_text(f"Error: {resp.status_code}")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    doc = update.message.document
    file = await doc.get_file()
    file_bytes = await file.download_as_bytearray()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{API_URL}/upload",
                files={"file": (doc.file_name, file_bytes, doc.mime_type)},
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                await update.message.reply_text(
                    f"📎 Archivo recibido: `{data['filename']}` ({data['size']} bytes)\n"
                    f"ID: `{data['file_id']}`\n"
                    f"Puedo analizarlo si me lo pides."
                )
            else:
                await update.message.reply_text(f"Error al subir: {resp.status_code}")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("memoria", memoria))
    app.add_handler(CommandHandler("buscar", buscar))
    app.add_handler(CommandHandler("search", buscar))
    app.add_handler(CommandHandler("ejecutar", ejecutar))
    app.add_handler(CommandHandler("run", ejecutar))
    app.add_handler(CommandHandler("archivos", list_archivos))
    app.add_handler(CommandHandler("files", list_archivos))
    app.add_handler(CommandHandler("new", new))
    app.add_handler(CommandHandler("nueva", new))
    app.add_handler(CommandHandler("forget", forget))
    app.add_handler(CommandHandler("olvidar", forget))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.run_polling()

if __name__ == "__main__":
    main()
