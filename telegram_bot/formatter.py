"""Formats outgoing Telegram messages (signals, heartbeat, summaries)."""

from __future__ import annotations

from datetime import datetime, timezone

from core.signal_engine import Signal


def format_signal_message(signal: Signal, signal_number: int) -> str:
    direction_emoji = "🟢" if signal.direction == "buy" else "🔴"
    arrow = "📈" if signal.direction == "buy" else "📉"
    reasons_block = "\n".join(f"  • {r}" for r in signal.reasons)

    return (
        f"{direction_emoji} <b>{signal.direction.upper()} SIGNAL #{signal_number:03d}</b> {arrow}\n\n"
        f"<b>Pair:</b> {signal.symbol}\n"
        f"<b>Timeframe:</b> {signal.timeframe}\n\n"
        f"🎯 <b>Entry:</b> {signal.entry}\n"
        f"🛑 <b>Stop Loss:</b> {signal.stop_loss}\n"
        f"✅ <b>Take Profit:</b> {signal.take_profit}\n"
        f"⚖️ <b>Risk:Reward:</b> 1:{signal.rr_ratio}\n"
        f"🔥 <b>Confidence:</b> {signal.confidence:.0f}%\n\n"
        f"<b>Confluence:</b>\n{reasons_block}\n\n"
        f"⚠️ <i>Manual execution only — this bot does not auto-trade.</i>"
    )


def format_heartbeat_message() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"💓 <b>Bot Heartbeat</b>\nStill online and scanning.\n🕒 {now}"


def format_daily_summary(rows: list[dict]) -> str:
    if not rows:
        return "📊 <b>Daily Summary</b>\nNo signals were generated today."

    buys = sum(1 for r in rows if r["direction"] == "BUY")
    sells = sum(1 for r in rows if r["direction"] == "SELL")
    avg_confidence = sum(float(r["confidence"]) for r in rows) / len(rows)

    lines = [f"📊 <b>Daily Summary</b>", f"Total signals: {len(rows)}", f"🟢 Buys: {buys}  🔴 Sells: {sells}", f"Average confidence: {avg_confidence:.1f}%", ""]
    for row in rows[-10:]:
        emoji = "🟢" if row["direction"] == "BUY" else "🔴"
        lines.append(f"{emoji} #{row['signal_number']} {row['pair']} {row['timeframe']} @ {row['entry']} ({row['confidence']}%)")

    return "\n".join(lines)


def format_status_message(mt5_connected: bool, active_signal_count: int, symbols: list[str]) -> str:
    status_emoji = "✅" if mt5_connected else "❌"
    return (
        f"🤖 <b>Bot Status</b>\n"
        f"MT5 Connection: {status_emoji}\n"
        f"Active signals: {active_signal_count}\n"
        f"Monitoring: {', '.join(symbols)}\n"
        f"Mode: Signal-only (no auto-trading)"
    )


def format_pairs_message(symbols: list[str], timeframes: list[str]) -> str:
    return (
        f"📋 <b>Monitored Pairs</b>\n"
        + "\n".join(f"• {s}" for s in symbols)
        + f"\n\n<b>Timeframes:</b> {', '.join(timeframes)}"
    )


def format_last_signal_message(row: dict | None) -> str:
    if row is None:
        return "No signals have been generated yet."
    emoji = "🟢" if row["direction"] == "BUY" else "🔴"
    return (
        f"{emoji} <b>Last Signal #{row['signal_number']}</b>\n"
        f"Pair: {row['pair']} ({row['timeframe']})\n"
        f"Entry: {row['entry']}  SL: {row['sl']}  TP: {row['tp']}\n"
        f"Confidence: {row['confidence']}%\n"
        f"Time: {row['date']} {row['time']} UTC"
    )


def format_today_message(rows: list[dict]) -> str:
    if not rows:
        return "No signals generated today yet."
    lines = ["📅 <b>Today's Signals</b>", ""]
    for row in rows:
        emoji = "🟢" if row["direction"] == "BUY" else "🔴"
        lines.append(f"{emoji} #{row['signal_number']} {row['pair']} {row['timeframe']} @ {row['entry']} ({row['confidence']}%)")
    return "\n".join(lines)


def format_help_message() -> str:
    return (
        "🤖 <b>Available Commands</b>\n\n"
        "/status — bot &amp; MT5 connection status\n"
        "/pairs — list monitored pairs and timeframes\n"
        "/lastsignal — show the most recent signal\n"
        "/today — show all signals sent today\n"
        "/help — show this message"
    )
