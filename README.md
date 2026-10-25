# dellog

A drop-in discord.py cog that logs deleted and edited messages to a mod
channel, with before/after embeds. Load it, run one command, done.

I kept running into the same thing on my own servers: someone deletes a
message right after sending it, a mod asks "what did it say?", and nobody
knows. There are big logging bots for this, but I didn't want to hand a
whole bot's worth of permissions to a third party just for one feature —
so I wrote the one feature, as a cog I can drop into any bot I already run.

## What a log looks like

A deleted message shows up in your mod channel like this:

```
Message deleted
SomeUser (42)
Channel: #general  |  Author: @SomeUser
Content: "wait, never mind —"
```

An edit shows the before and after side by side, and a bulk delete (like a
purge) shows up as a one-line summary with the count, since Discord doesn't
hand you the individual messages for those.

## Install

```bash
pip install git+https://github.com/codewithkrrish/dellog.git
```

Needs Python 3.10+ and discord.py 2.3+. Your bot needs the **Message
Content intent** enabled in the Discord developer portal, or it will only
see empty messages — that's a Discord rule, not a bug in this cog.

## Usage

Load it like any extension:

```python
await bot.load_extension("dellog")
```

Then in your server, a mod with Manage Server runs:

```
/dellog setup #mod-logs
```

That's the whole setup. Everything else is optional:

| Command | What it does |
|---|---|
| `/dellog setup #channel` | Set (or move) the log channel |
| `/dellog ignore add #channel` | Stop logging one channel (e.g. a bot-spam channel) |
| `/dellog ignore remove #channel` | Start logging it again |
| `/dellog toggle deletes` | Turn delete logging on/off |
| `/dellog toggle edits` | Turn edit logging on/off |
| `/dellog status` | Show the current setup for this server |

Defaults, for the curious: bots are ignored, DMs are never logged,
attachment links are included (up to 5 per message), and edit events that
don't change the text — like a link preview loading — are skipped so your
mod channel doesn't get spammed.

Config lives in a `dellog.json` file next to wherever you run the bot, one
entry per server. Writes are atomic (temp file + rename), so a crash
mid-save can't corrupt it. If the file ever gets mangled, the cog logs a
warning and starts empty instead of refusing to load — you just re-run
`/dellog setup`.

## Project structure

```
src/dellog/
  cog.py      # the cog: listeners + slash commands (thin layer)
  config.py   # per-server config + atomic JSON store
  embeds.py   # the log embed builders (pure, tested)
examples/
  bot.py      # minimal bot that loads the cog
tests/        # pytest: config, embeds, listener behaviour
```

## Limitations, honestly

- **Only messages the bot has seen.** Discord only tells your bot about
  deletes for messages in its cache. If the bot restarts and someone deletes
  an old message, there's nothing to log — no bot can fix that.
- **No message content without the intent.** If you forget the Message
  Content intent, logs will show empty content. Enable it in the portal.
- **Bulk deletes are summaries only.** Discord sends the purge as a batch
  of bare IDs, so dellog logs the count and channel, not the texts.
- **One log channel per server.** If you want separate channels for edits
  and deletes, that's not here yet — open an issue and I'll look at it.

## License

MIT — see [LICENSE](LICENSE).

## Author

Built by [Krrish](https://github.com/codewithkrrish) — I make Discord bots
and small Python tools. If this saved your mods a headache, a star is
appreciated.
