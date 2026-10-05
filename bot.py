#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import csv
import io
import requests
from datetime import datetime

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_FILE = "database.json"

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")
if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID environment variable is missing.")

BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
session = requests.Session()

users = {}
submissions = []
withdrawals = []
rates = {"task": 5.0}
settings = {
    "support_url": "https://t.me/EasyIncomeX_Support",
    "must_join_channel": "",
    "referral_tasks_required": 5,
    "referral_bonus": 10.0,
    "guide": "Welcome! Work from the menu, submit your task proof, and wait for admin review."
}
states = {}
temp = {}


def api(method, payload=None, timeout=60):
    try:
        if payload is None:
            r = session.get(f"{BASE_URL}/{method}", timeout=timeout)
        else:
            r = session.post(f"{BASE_URL}/{method}", json=payload, timeout=timeout)
        return r.json()
    except Exception:
        return {}


def send(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return api("sendMessage", payload)


def load_db():
    global users, submissions, withdrawals, rates, settings
    if not os.path.exists(DB_FILE):
        save_db()
        return
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        users = {int(k): v for k, v in data.get("users", {}).items()}
        submissions = data.get("submissions", [])
        withdrawals = data.get("withdrawals", [])
        rates.update(data.get("rates", {}))
        settings.update(data.get("settings", {}))
    except Exception:
        pass


def save_db():
    data = {
        "users": {str(k): v for k, v in users.items()},
        "submissions": submissions,
        "withdrawals": withdrawals,
        "rates": rates,
        "settings": settings,
    }
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_admin(uid):
    return int(uid) == ADMIN_ID


def ensure_user(msg, ref=None):
    u = msg.get("from", {})
    uid = int(u["id"])
    if uid not in users:
        referred = None
        if ref and str(ref).isdigit() and int(ref) != uid:
            referred = int(ref)
        users[uid] = {
            "id": uid,
            "username": u.get("username", ""),
            "first_name": u.get("first_name", ""),
            "balance": 0.0,
            "total_earned": 0.0,
            "referred_by": referred,
            "referral_paid": False,
            "joined_at": time.time(),
        }
        save_db()
    else:
        users[uid]["username"] = u.get("username", users[uid].get("username", ""))
        users[uid]["first_name"] = u.get("first_name", users[uid].get("first_name", ""))


def force_join_ok(uid):
    channel = settings.get("must_join_channel", "")
    if not channel:
        return True
    res = api("getChatMember", {"chat_id": channel, "user_id": uid})
    if not res.get("ok"):
        return False
    return res.get("result", {}).get("status") in ("member", "administrator", "creator")


def force_join_prompt(uid):
    channel = settings.get("must_join_channel", "")
    username = channel.lstrip("@")
    kb = {
        "inline_keyboard": [
            [{"text": "Join Channel", "url": f"https://t.me/{username}"}],
            [{"text": "I Joined", "callback_data": "check_join"}],
        ]
    }
    send(uid, "⚠️ <b>Channel Join Required</b>\n\nPlease join our channel first.", kb)


def main_menu():
    return {
        "keyboard": [
            [{"text": "💼 Work"}, {"text": "💰 Balance"}],
            [{"text": "💸 Withdraw"}, {"text": "🎁 Referrals"}],
            [{"text": "📖 Guide"}, {"text": "💬 Support"}],
        ],
        "resize_keyboard": True,
    }


def admin_menu():
    return {
        "inline_keyboard": [
            [{"text": "👥 Users", "callback_data": "users"},
             {"text": "📊 Pending", "callback_data": "pending"}],
            [{"text": "📢 Broadcast", "callback_data": "broadcast"},
             {"text": "💰 Set Rate", "callback_data": "rate"}],
            [{"text": "🎁 Referral Settings", "callback_data": "ref_settings"},
             {"text": "📢 Force Join", "callback_data": "force_join"}],
            [{"text": "📥 Export", "callback_data": "export"},
             {"text": "💾 Backup DB", "callback_data": "backup"}],
        ]
    }


def work_menu():
    return {
        "keyboard": [
            [{"text": f"Complete Task (৳{rates['task']:.2f})"}],
            [{"text": "⬅️ Back"}],
        ],
        "resize_keyboard": True,
    }


def cancel_menu():
    return {"keyboard": [[{"text": "❌ Cancel"}]], "resize_keyboard": True}


def submit_task(uid, username, proof):
    submissions.append({
        "id": len(submissions) + 1,
        "user_id": uid,
        "username": username,
        "proof": proof,
        "reward": float(rates["task"]),
        "status": "pending",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_db()


def approve_submission(sub):
    if sub["status"] != "pending":
        return
    sub["status"] = "approved"
    uid = int(sub["user_id"])
    reward = float(sub["reward"])
    if uid not in users:
        return
    users[uid]["balance"] += reward
    users[uid]["total_earned"] += reward

    u = users[uid]
    required = int(settings.get("referral_tasks_required", 5))
    approved_count = sum(
        1 for x in submissions
        if int(x["user_id"]) == uid and x["status"] == "approved"
    )
    ref = u.get("referred_by")
    if ref and not u.get("referral_paid") and approved_count >= required:
        if int(ref) in users:
            bonus = float(settings.get("referral_bonus", 10))
            users[int(ref)]["balance"] += bonus
            users[int(ref)]["total_earned"] += bonus
            u["referral_paid"] = True
            send(int(ref), f"🎁 <b>Referral Bonus</b>\nYou earned ৳{bonus:.2f}.")
    save_db()


def reject_submission(sub):
    if sub["status"] == "pending":
        sub["status"] = "rejected"
        save_db()


def handle_message(msg):
    chat = msg.get("chat", {})
    uid = chat.get("id")
    if not uid:
        return
    text = msg.get("text", "")
    username = msg.get("from", {}).get("username", "")
    ref = None
    if text.startswith("/start "):
        ref = text.split(maxsplit=1)[1]
    ensure_user(msg, ref)

    if text.startswith("/start"):
        states.pop(uid, None)
        if not force_join_ok(uid):
            force_join_prompt(uid)
            return
        send(uid, "👋 <b>Welcome!</b>\nChoose an option:", main_menu())
        return

    if not force_join_ok(uid):
        force_join_prompt(uid)
        return

    if text == "/admin":
        if is_admin(uid):
            send(uid, "🛠 <b>Admin Panel</b>", admin_menu())
        return

    state = states.get(uid, "main")

    if text == "❌ Cancel":
        states.pop(uid, None)
        temp.pop(uid, None)
        send(uid, "❌ Cancelled.", main_menu())
        return

    if state == "broadcast":
        count = 0
        for target in list(users):
            if api("sendMessage", {
                "chat_id": target,
                "text": text,
                "parse_mode": "HTML"
            }).get("ok"):
                count += 1
        states.pop(uid, None)
        send(uid, f"✅ Broadcast sent to <b>{count}</b> users.", main_menu())
        return

    if state == "set_rate":
        try:
            value = float(text)
            if value < 0:
                raise ValueError
            rates["task"] = value
            save_db()
            states.pop(uid, None)
            send(uid, f"✅ Task rate set to ৳{value:.2f}.", main_menu())
        except ValueError:
            send(uid, "❌ Enter a valid number.")
        return

    if state == "set_ref_tasks":
        try:
            n = int(text)
            if n < 1:
                raise ValueError
            settings["referral_tasks_required"] = n
            save_db()
            states.pop(uid, None)
            send(uid, f"✅ Referral requirement: {n} approved tasks.", main_menu())
        except ValueError:
            send(uid, "❌ Enter a valid whole number.")
        return

    if state == "set_ref_bonus":
        try:
            value = float(text)
            if value < 0:
                raise ValueError
            settings["referral_bonus"] = value
            save_db()
            states.pop(uid, None)
            send(uid, f"✅ Referral bonus: ৳{value:.2f}.", main_menu())
        except ValueError:
            send(uid, "❌ Enter a valid amount.")
        return

    if state == "set_force_join":
        settings["must_join_channel"] = "" if text.lower() == "none" else (text if text.startswith("@") else "@" + text)
        save_db()
        states.pop(uid, None)
        send(uid, "✅ Force Join updated.", main_menu())
        return

    if state == "proof":
        if len(text) < 2:
            send(uid, "❌ Please send a valid proof.", cancel_menu())
            return
        submit_task(uid, username, text)
        states.pop(uid, None)
        send(uid, "✅ <b>Proof submitted!</b>\nAdmin will review it.", main_menu())
        return

    if state == "withdraw_amount":
        try:
            amount = float(text)
            if amount <= 0:
                raise ValueError
            if amount > users[uid]["balance"]:
                send(uid, "❌ Insufficient balance.", main_menu())
                states.pop(uid, None)
                return
            temp[uid] = {"amount": amount}
            states[uid] = "withdraw_method"
            send(uid, "Send your payout method/account details.\nExample: bKash 01XXXXXXXXX", cancel_menu())
        except ValueError:
            send(uid, "❌ Enter a valid amount.", cancel_menu())
        return

    if state == "withdraw_method":
        amount = temp.get(uid, {}).get("amount")
        if not amount:
            states.pop(uid, None)
            send(uid, "❌ Withdrawal session expired.", main_menu())
            return
        users[uid]["balance"] -= amount
        withdrawals.append({
            "id": len(withdrawals) + 1,
            "user_id": uid,
            "amount": amount,
            "method": text,
            "status": "pending",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })
        save_db()
        states.pop(uid, None)
        temp.pop(uid, None)
        send(uid, "✅ Withdrawal request submitted.", main_menu())
        send(ADMIN_ID, f"💸 <b>New Withdrawal</b>\nUser: <code>{uid}</code>\nAmount: ৳{amount:.2f}\nMethod: <code>{text}</code>")
        return

    if text == "💼 Work":
        send(uid, "Select a task:", work_menu())
    elif text.startswith("Complete Task"):
        send(uid, "📌 Complete the assigned task, then send a simple proof/screenshot description here.\n\nDo not send passwords, 2FA secrets, session cookies, or other login credentials.", cancel_menu())
        states[uid] = "proof"
    elif text == "💰 Balance":
        u = users[uid]
        pending = sum(1 for x in submissions if x["user_id"] == uid and x["status"] == "pending")
        send(uid, f"💰 <b>Balance</b>\n\nAvailable: ৳{u['balance']:.2f}\nTotal Earned: ৳{u['total_earned']:.2f}\nPending Tasks: {pending}", main_menu())
    elif text == "💸 Withdraw":
        min_amount = 50
        send(uid, f"💸 Enter withdrawal amount.\nMinimum: ৳{min_amount}", cancel_menu())
        states[uid] = "withdraw_amount"
    elif text == "🎁 Referrals":
        username = bot_info.get("username", "your_bot")
        total = sum(1 for x in users.values() if x.get("referred_by") == uid)
        qualified = sum(1 for x in users.values() if x.get("referred_by") == uid and x.get("referral_paid"))
        send(uid, f"🎁 <b>Referrals</b>\n\nLink:\n<code>https://t.me/{username}?start={uid}</code>\n\nTotal: {total}\nQualified: {qualified}\nBonus: ৳{settings['referral_bonus']:.2f} after {settings['referral_tasks_required']} approved tasks.", main_menu())
    elif text == "📖 Guide":
        send(uid, settings.get("guide", ""), main_menu())
    elif text == "💬 Support":
        kb = {"inline_keyboard": [[{"text": "Contact Support", "url": settings["support_url"]}]]}
        send(uid, "💬 Contact support:", kb)
    elif text == "⬅️ Back":
        send(uid, "Main menu:", main_menu())
    elif state == "main":
        send(uid, "Please choose an option from the menu.", main_menu())


def send_document_bytes(chat_id, filename, data):
    try:
        r = session.post(
            f"{BASE_URL}/sendDocument",
            data={"chat_id": chat_id},
            files={"document": (filename, data, "text/csv")},
            timeout=60
        )
        return r.json()
    except Exception:
        return {}


def handle_callback(call):
    uid = call.get("message", {}).get("chat", {}).get("id")
    data = call.get("data", "")
    if not uid:
        return

    api("answerCallbackQuery", {"callback_query_id": call["id"]})

    if data == "check_join":
        if force_join_ok(uid):
            send(uid, "✅ Verified!", main_menu())
        else:
            api("answerCallbackQuery", {
                "callback_query_id": call["id"],
                "text": "Please join first.",
                "show_alert": True
            })
        return

    if not is_admin(uid):
        return

    if data == "users":
        send(uid, f"👥 <b>Total Users:</b> {len(users)}")
    elif data == "pending":
        pending = [x for x in submissions if x["status"] == "pending"]
        if not pending:
            send(uid, "✅ No pending tasks.")
            return
        kb = []
        for s in pending[:50]:
            kb.append([{
                "text": f"#{s['id']} User {s['user_id']} — ৳{s['reward']:.2f}",
                "callback_data": f"review_{s['id']}"
            }])
        send(uid, "📋 <b>Pending Tasks</b>", {"inline_keyboard": kb})
    elif data.startswith("review_"):
        sid = int(data.split("_")[1])
        sub = next((x for x in submissions if int(x["id"]) == sid), None)
        if not sub:
            send(uid, "Not found.")
            return
        temp[uid] = {"review_id": sid}
        kb = {"inline_keyboard": [
            [{"text": "✅ Approve", "callback_data": f"approve_{sid}"},
             {"text": "❌ Reject", "callback_data": f"reject_{sid}"}]
        ]}
        send(uid, f"<b>Task #{sid}</b>\nUser: <code>{sub['user_id']}</code>\nReward: ৳{sub['reward']:.2f}\n\n<b>Proof:</b>\n{sub['proof']}", kb)
    elif data.startswith("approve_"):
        sid = int(data.split("_")[1])
        sub = next((x for x in submissions if int(x["id"]) == sid), None)
        if sub:
            approve_submission(sub)
            send(uid, f"✅ Task #{sid} approved.")
            send(int(sub["user_id"]), f"✅ Your task #{sid} was approved. ৳{sub['reward']:.2f} added.")
    elif data.startswith("reject_"):
        sid = int(data.split("_")[1])
        sub = next((x for x in submissions if int(x["id"]) == sid), None)
        if sub:
            reject_submission(sub)
            send(uid, f"❌ Task #{sid} rejected.")
            send(int(sub["user_id"]), f"❌ Your task #{sid} was rejected.")
    elif data == "broadcast":
        states[uid] = "broadcast"
        send(uid, "📢 Send the broadcast message.", cancel_menu())
    elif data == "rate":
        states[uid] = "set_rate"
        send(uid, "💰 Enter new task rate:", cancel_menu())
    elif data == "ref_settings":
        kb = {"inline_keyboard": [
            [{"text": f"Tasks: {settings['referral_tasks_required']}", "callback_data": "ref_tasks"},
             {"text": f"Bonus: ৳{settings['referral_bonus']:.2f}", "callback_data": "ref_bonus"}]
        ]}
        send(uid, "🎁 Referral settings:", kb)
    elif data == "ref_tasks":
        states[uid] = "set_ref_tasks"
        send(uid, "Enter required approved tasks:", cancel_menu())
    elif data == "ref_bonus":
        states[uid] = "set_ref_bonus"
        send(uid, "Enter referral bonus:", cancel_menu())
    elif data == "force_join":
        states[uid] = "set_force_join"
        send(uid, "Enter channel username, e.g. @mychannel\nOr type <code>none</code> to disable.", cancel_menu())
    elif data == "export":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "user_id", "username", "reward", "status", "created_at", "proof"])
        for s in submissions:
            writer.writerow([s["id"], s["user_id"], s["username"], s["reward"], s["status"], s["created_at"], s["proof"]])
        send_document_bytes(uid, "submissions.csv", output.getvalue().encode("utf-8-sig"))
    elif data == "backup":
        try:
            with open(DB_FILE, "rb") as f:
                session.post(f"{BASE_URL}/sendDocument", data={"chat_id": uid}, files={"document": f}, timeout=60)
        except Exception:
            send(uid, "❌ Backup failed.")


bot_info = {}


def main():
    global bot_info
    load_db()
    me = api("getMe")
    if not me.get("ok"):
        raise RuntimeError("Telegram API connection failed. Check BOT_TOKEN.")
    bot_info = me["result"]
    print(f"Bot started: @{bot_info.get('username')}")

    offset = None
    while True:
        try:
            params = {"timeout": 50}
            if offset is not None:
                params["offset"] = offset
            result = api("getUpdates", params, timeout=65)
            for update in result.get("result", []):
                offset = update["update_id"] + 1
                if "message" in update:
                    handle_message(update["message"])
                elif "callback_query" in update:
                    handle_callback(update["callback_query"])
        except Exception as e:
            print("Loop error:", e)
            time.sleep(3)


if __name__ == "__main__":
    main()
