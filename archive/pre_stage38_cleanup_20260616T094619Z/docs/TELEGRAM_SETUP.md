# Telegram Notification Setup

## Purpose

Telegram is used only for pipeline/report notifications.

It must not be interpreted as a trading signal, paper-order instruction, or live order approval.

## Key definitions

- Bot token: the private token created by BotFather for your Telegram bot.
- Chat ID: the numeric identifier of the private chat, group, or channel where the bot sends messages.
- Notification: a short status report from the research pipeline.

## Required GitHub Secrets

Add these repository secrets:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Keep existing data-provider secret too:

```text
TWELVEDATA_API_KEY
```

## How to create the bot

1. Open Telegram.
2. Search for `@BotFather`.
3. Send `/newbot`.
4. Choose a display name.
5. Choose a username ending in `bot`.
6. Copy the token.

Do not paste the token into Git files.

## How to get chat ID

Private chat method:

1. Open your new bot in Telegram.
2. Press Start or send a test message.
3. In a browser, open:

```text
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
```

4. Find:

```text
"chat":{"id":123456789,...}
```

5. Use that number as `TELEGRAM_CHAT_ID`.

Group method:

1. Add the bot to the group.
2. Send a message in the group.
3. Call `getUpdates`.
4. Use the group chat id. Group ids are often negative.

## Local test

```bash
cd ~/Desktop/xauusd-trader
export TELEGRAM_BOT_TOKEN='PASTE_BOT_TOKEN'
export TELEGRAM_CHAT_ID='PASTE_CHAT_ID'
python3 -m app.telegram_notify --status local-test
```

If no summary file exists, the message will say summary not found. That is acceptable for a connection test.

## Workflow

The Stage 2A workflow sends a Telegram message after the baseline lab step.

The notification includes:

- workflow status,
- decision status,
- candidate count,
- top baseline snapshot,
- cost warning,
- run link.

## Strict warning

The Telegram text is deliberately not a signal.

No ML, no paper order, and no live trading decision is allowed from these messages.
