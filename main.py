#!/usr/bin/env python3
"""
Telegram admin helper bot:
Commands:
  /start   - help
  /ip      - returns public IP
  /user    - returns current username
  /sudo    - checks non-interactive sudo (sudo -n whoami)
  /tmate   - installs tmate (if needed), launches a detached session, returns connection strings
Requirements:
  pip install python-telegram-bot requests
Set env var TELEGRAM_TOKEN before running.
"""

import os
import shlex
import subprocess
import time
import tempfile
from pathlib import Path

import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Updater, CommandHandler, CallbackContext

TELEGRAM_TOKEN = "8598252838:AAH9vTbHGwy997NqRkbIZ9IMPGfBY6YUOaQ"

# Helper to run shell commands safely
def run_cmd(cmd, timeout=30, check=False, capture_output=True, shell=False):
    """Run a command. cmd can be list or string."""
    try:
        if shell:
            proc = subprocess.run(cmd, shell=True, timeout=timeout,
                                  check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        else:
            if isinstance(cmd, str):
                cmd = shlex.split(cmd)
            proc = subprocess.run(cmd, timeout=timeout, check=check,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout.strip() if e.stdout else "", e.stderr.strip() if e.stderr else str(e)
    except Exception as e:
        return 1, "", str(e)

# Command handlers
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Bot ready.\nCommands:\n/ip - get public IP\n/user - current username\n/sudo - check sudo (non-interactive)\n/tmate - install & start tmate, return connection"
    )

def ip_cmd(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    msg = "Fetching public IP..."
    update.message.reply_text(msg)
    # Try multiple ways for reliability
    services = ["https://api.ipify.org", "https://ifconfig.me/ip", "https://ipinfo.io/ip"]
    ip = None
    for s in services:
        try:
            r = requests.get(s, timeout=6)
            if r.ok:
                candidate = r.text.strip()
                if candidate:
                    ip = candidate
                    break
        except Exception:
            pass
    if not ip:
        # fallback: try hostname -I (may give local IPs)
        code, out, err = run_cmd("hostname -I")
        ip = out.strip() if out else "Unknown"
    update.message.reply_text(f"Public IP: `{ip}`", parse_mode=ParseMode.MARKDOWN)

def user_cmd(update: Update, context: CallbackContext):
    code, out, err = run_cmd("whoami")
    username = out.strip() if out else "unknown"
    update.message.reply_text(f"Current user: `{username}`", parse_mode=ParseMode.MARKDOWN)

def sudo_cmd(update: Update, context: CallbackContext):
    # Non-interactive sudo check
    update.message.reply_text("Checking sudo availability (non-interactive)...")
    code, out, err = run_cmd("sudo -n whoami")
    if code == 0 and out.strip():
        update.message.reply_text(f"Sudo works. `sudo whoami` -> `{out.strip()}`", parse_mode=ParseMode.MARKDOWN)
    else:
        # If sudo requires password or not allowed, sudo -n exits non-zero and prints message
        info = err or out or "No output"
        # If user wants to enable sudo for their user, we provide safe instructions (must be run as root)
        guidance = (
            "Sudo is not available non-interactively for this user.\n\n"
            "If you control the VPS and want to allow passwordless sudo for this user **(only if you understand the risk)**,\n"
            "run as root:\n\n"
            "1) Add user to sudoers group (Debian/Ubuntu):\n   `usermod -aG sudo <username>`\n\n"
            "2) Or create a sudoers.d file to allow passwordless sudo (risky):\n   `echo \"<username> ALL=(ALL) NOPASSWD:ALL\" > /etc/sudoers.d/<username>`\n   `chmod 440 /etc/sudoers.d/<username>`\n\n"
            "These commands must be executed as root. Do NOT use them unless you know what you are doing."
        )
        update.message.reply_text(f"Sudo check failed: `{info}`\n\n{guidance}", parse_mode=ParseMode.MARKDOWN)

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
    # fallback
    return None

def tmate_cmd(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    update.message.reply_text("Starting tmate installer/launcher. This may take a minute...")
    # 1) detect if tmate exists
    code, out, err = run_cmd("tmate -V")
    if code == 0:
        update.message.reply_text("tmate is already installed. Attempting to start a detached session...")
    else:
        pm = detect_pkg_manager()
        if not pm:
            update.message.reply_text("Could not detect package manager. Please install tmate manually.")
            return
        # Build install command per package manager
        if pm == "apt":
            cmd = "sudo apt-get update -y && sudo apt-get install -y tmate"
        elif pm == "dnf":
            cmd = "sudo dnf install -y tmate"
        elif pm == "yum":
            cmd = "sudo yum install -y epel-release && sudo yum install -y tmate"
        elif pm == "pacman":
            cmd = "sudo pacman -Sy --noconfirm tmate"
        else:
            update.message.reply_text("Unsupported package manager. Install tmate manually.")
            return
        update.message.reply_text(f"Installing via `{pm}`. Command: `{cmd}`", parse_mode=ParseMode.MARKDOWN)
        code, out, err = run_cmd(cmd, timeout=600, shell=True)
        if code != 0:
            update.message.reply_text(f"Installation failed. stderr:\n`{err}`", parse_mode=ParseMode.MARKDOWN)
            return
        update.message.reply_text("Installation complete. Continuing...")

    # 2) create a dedicated socket path and start detached session
    socket_path = "/var/run/tmate.sock"
    # ensure directory exists and writable
    try:
        Path(socket_path).parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    # Start a detached tmate session (works if tmate installed)
    # Use -S to specify socket; new-session -d for detached
    start_cmd = f"tmate -S {socket_path} new-session -d"
    code, out, err = run_cmd(start_cmd, timeout=20, shell=True)
    if code != 0:
        update.message.reply_text(f"Failed to start tmate session: `{err or out}`", parse_mode=ParseMode.MARKDOWN)
        return

    # Wait briefly for tmate to create connections
    time.sleep(2)

    # Fetch ssh and web connection strings
    ssh_cmd = f"tmate -S {socket_path} display -p '#{{tmate_ssh}}'"
    web_cmd = f"tmate -S {socket_path} display -p '#{{tmate_web}}'"
    code1, ssh_out, ssh_err = run_cmd(ssh_cmd, timeout=10, shell=True)
    code2, web_out, web_err = run_cmd(web_cmd, timeout=10, shell=True)

    if (not ssh_out) and (not web_out):
        update.message.reply_text(
            "Could not retrieve tmate connection strings. Maybe tmate needs network access or API key.\n"
            f"ssh_err: `{ssh_err}`\nweb_err: `{web_err}`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Optionally create systemd unit to keep tmate running on reboot
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
    svc_path = "/etc/systemd/system/tmate-perm.service"
    try:
        with open(tempfile.gettempdir() + "/tmate-perm.service.tmp", "w") as f:
            f.write(svc)
        # Need sudo to move into /etc/systemd/system and enable
        mv_cmd = f"sudo mv {shlex.quote(tempfile.gettempdir() + '/tmate-perm.service.tmp')} {svc_path} && sudo systemctl daemon-reload && sudo systemctl enable tmate-perm.service && sudo systemctl start tmate-perm.service"
        code, out, err = run_cmd(mv_cmd, timeout=30, shell=True)
        if code == 0:
            service_msg = "A systemd unit was installed and started to keep tmate persistent across reboots."
        else:
            service_msg = f"Could not install systemd unit (requires sudo): `{err or out}`"
    except Exception as e:
        service_msg = f"Failed to create systemd unit: {e}"

    # Reply with results
    resp = "tmate session started.\n\n"
    if ssh_out:
        resp += f"SSH: `{ssh_out}`\n"
    if web_out:
        resp += f"Web: `{web_out}`\n"
    resp += f"\n{service_msg}"
    update.message.reply_text(resp, parse_mode=ParseMode.MARKDOWN)

def main():
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("ip", ip_cmd))
    dp.add_handler(CommandHandler("user", user_cmd))
    dp.add_handler(CommandHandler("sudo", sudo_cmd))
    dp.add_handler(CommandHandler("tmate", tmate_cmd))

    updater.start_polling()
    print("Bot started.")
    updater.idle()

if __name__ == "__main__":
    main()
    