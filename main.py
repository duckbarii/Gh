#!/usr/bin/env python3
"""
tg_simple_bot.py
A minimal Telegram bot using only 'requests' (no python-telegram-bot) so it works on Python 3.13.
Features:
  - Hardcode TELEGRAM_TOKEN below (replace placeholder)
  - Optional ALLOWED_CHAT_ID: set to your Telegram numeric id to restrict usage
  - Commands: /start, /ip, /user, /sudo, /tmate
Requires:
  - pip install requests
Run:
  python3 tg_simple_bot.py
"""

import time
import requests
import shlex
import subprocess
import tempfile
from pathlib import Path

# ----------------- CONFIG -----------------
TELEGRAM_TOKEN = "8598252838:AAH9vTbHGwy997NqRkbIZ9IMPGfBY6YUOaQ"

# If you want to restrict who can use the bot, put your Telegram chat id (int).
# Leave as None to allow any chat.
ALLOWED_CHAT_ID = 7824798767  # e.g. 123456789

POLL_INTERVAL = 2  # seconds between getUpdates
# ------------------------------------------

if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "1234567890:ABCDEF_your_real_token_here":
    raise SystemExit("Edit TELEGRAM_TOKEN in this file and put your real bot token.")

API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def api_request(method, **params):
    url = f"{API_URL}/{method}"
    try:
        r = requests.post(url, data=params, timeout=20)
        return r.json()
    except Exception as e:
        print("HTTP error:", e)
        return None

def send_message(chat_id, text, parse_mode=None):
    params = {"chat_id": chat_id, "text": text}
    if parse_mode:
        params["parse_mode"] = parse_mode
    api_request("sendMessage", **params)

def run_cmd(cmd, timeout=30, shell=False):
    try:
        if shell:
            proc = subprocess.run(cmd, shell=True, timeout=timeout,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        else:
            if isinstance(cmd, str):
                cmd = shlex.split(cmd)
            proc = subprocess.run(cmd, timeout=timeout,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except Exception as e:
        return 1, "", str(e)

# Utility functions
def get_public_ip():
    services = ["https://api.ipify.org", "https://ifconfig.me/ip", "https://ipinfo.io/ip"]
    for s in services:
        try:
            r = requests.get(s, timeout=6)
            if r.ok and r.text.strip():
                return r.text.strip()
        except Exception:
            pass
    code, out, err = run_cmd("hostname -I")
    return out.split()[0] if out else "Unknown"

def detect_pkg_manager():
    for cmd in ("/usr/bin/apt-get", "/usr/bin/dnf", "/usr/bin/yum", "/usr/bin/pacman"):
        if Path(cmd).exists():
            if "apt-get" in cmd:
                return "apt"
            if "dnf" in cmd:
                return "dnf"
            if "yum" in cmd:
                return "yum"
            if "pacman" in cmd:
                return "pacman"
    return None

def handle_command(chat_id, text):
    text = (text or "").strip()
    if not text:
        return

    if text.startswith("/start"):
        send_message(chat_id, "Bot ready. Commands: /ip /user /sudo /tmate")
        return

    if text.startswith("/ip"):
        ip = get_public_ip()
        send_message(chat_id, f"Public IP: `{ip}`", parse_mode="Markdown")
        return

    if text.startswith("/user"):
        code, out, err = run_cmd("whoami")
        username = out.strip() if out else "unknown"
        send_message(chat_id, f"Current user: `{username}`", parse_mode="Markdown")
        return

    if text.startswith("/sudo"):
        send_message(chat_id, "Checking sudo availability (non-interactive)...")
        code, out, err = run_cmd("sudo -n whoami")
        if code == 0 and out.strip():
            send_message(chat_id, f"Sudo works. `sudo whoami` -> `{out.strip()}`", parse_mode="Markdown")
        else:
            info = err or out or "No output"
            guidance = (
                "Sudo is not available non-interactively for this user.\n\n"
                "If you control the VPS and want to allow passwordless sudo for this user (risky),\n"
                "run as root:\n\n"
                "1) Add to sudo group (Debian/Ubuntu):\n   `usermod -aG sudo <username>`\n\n"
                "2) Or create sudoers file:\n   `echo \"<username> ALL=(ALL) NOPASSWD:ALL\" > /etc/sudoers.d/<username>`\n   `chmod 440 /etc/sudoers.d/<username>`\n\n"
                "These must be run as root. Only do this if you understand the security risk."
            )
            send_message(chat_id, f"Sudo check failed: `{info}`\n\n{guidance}", parse_mode="Markdown")
        return

    if text.startswith("/tmate"):
        send_message(chat_id, "Starting tmate installer/launcher. This may take a minute...")
        # check existing tmate
        code, out, err = run_cmd("tmate -V")
        if code == 0:
            send_message(chat_id, "tmate already installed. Starting a detached session...")
        else:
            pm = detect_pkg_manager()
            if not pm:
                send_message(chat_id, "Could not detect package manager. Please install tmate manually.")
                return
            if pm == "apt":
                cmd = "sudo apt-get update -y && sudo apt-get install -y tmate"
            elif pm == "dnf":
                cmd = "sudo dnf install -y tmate"
            elif pm == "yum":
                cmd = "sudo yum install -y epel-release && sudo yum install -y tmate"
            elif pm == "pacman":
                cmd = "sudo pacman -Sy --noconfirm tmate"
            else:
                send_message(chat_id, "Unsupported package manager. Install tmate manually.")
                return
            send_message(chat_id, f"Installing via `{pm}`. This may require sudo.")
            code, out, err = run_cmd(cmd, timeout=600, shell=True)
            if code != 0:
                send_message(chat_id, f"Installation failed. stderr:\n`{err}`", parse_mode="Markdown")
                return
            send_message(chat_id, "Installation complete. Continuing...")

        socket_path = "/var/run/tmate.sock"
        try:
            Path(socket_path).parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        start_cmd = f"tmate -S {socket_path} new-session -d"
        code, out, err = run_cmd(start_cmd, timeout=20, shell=True)
        if code != 0:
            send_message(chat_id, f"Failed to start tmate session: `{err or out}`", parse_mode="Markdown")
            return

        # wait briefly and fetch strings
        time.sleep(2)
        ssh_cmd = f"tmate -S {socket_path} display -p '#{{tmate_ssh}}'"
        web_cmd = f"tmate -S {socket_path} display -p '#{{tmate_web}}'"
        code1, ssh_out, ssh_err = run_cmd(ssh_cmd, timeout=10, shell=True)
        code2, web_out, web_err = run_cmd(web_cmd, timeout=10, shell=True)

        if (not ssh_out) and (not web_out):
            send_message(chat_id,
                         f"Could not retrieve tmate connection strings. ssh_err:`{ssh_err}` web_err:`{web_err}`",
                         parse_mode="Markdown")
            return

        # try to create systemd unit (best-effort)
        svc = f"""[Unit]
Description=tmate permanent session
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/tmate -S {socket_path} new-session -d
Restart=always
User=root
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        svc_tmp = tempfile.gettempdir() + "/tmate-perm.service.tmp"
        svc_path = "/etc/systemd/system/tmate-perm.service"
        service_msg = ""
        try:
            with open(svc_tmp, "w") as f:
                f.write(svc)
            mv_cmd = f"sudo mv {shlex.quote(svc_tmp)} {svc_path} && sudo systemctl daemon-reload && sudo systemctl enable tmate-perm.service && sudo systemctl start tmate-perm.service"
            code, out, err = run_cmd(mv_cmd, timeout=30, shell=True)
            if code == 0:
                service_msg = "A systemd unit was installed and started to keep tmate persistent across reboots."
            else:
                service_msg = f"Could not install systemd unit (requires sudo): `{err or out}`"
        except Exception as e:
            service_msg = f"Failed to create systemd unit: {e}"

        resp = "tmate session started.\n\n"
        if ssh_out:
            resp += f"SSH: `{ssh_out}`\n"
        if web_out:
            resp += f"Web: `{web_out}`\n"
        resp += f"\n{service_msg}"
        send_message(chat_id, resp, parse_mode="Markdown")
        return

    # unknown command
    send_message(chat_id, "Unknown command. Use /start to see available commands.")

def main():
    offset = None
    print("Bot polling started.")
    while True:
        try:
            params = {"timeout": 10}
            if offset:
                params["offset"] = offset
            r = requests.get(f"{API_URL}/getUpdates", params=params, timeout=30)
            data = r.json() if r.ok else None
            if not data or not data.get("ok"):
                time.sleep(POLL_INTERVAL)
                continue
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                if "message" not in upd:
                    continue
                msg = upd["message"]
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "")
                # restrict by chat id if set
                if ALLOWED_CHAT_ID is not None and chat_id != ALLOWED_CHAT_ID:
                    send_message(chat_id, "Unauthorized.")
                    continue
                # handle commands
                handle_command(chat_id, text)
        except Exception as e:
            print("Polling error:", e)
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
