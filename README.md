This bot monitors Mastodon notifications and reacts automatically.
It follows back new followers and boosts mentions of the bot, while enforcing a configurable minimum interval per user. The bot persists its state to avoid duplicate boosts and runs in regular polling intervals.

Create a .env file in the working directory of the bot and add the following environment variables:

```env
MASTODON_BASE_URL=https://mastodon.social
ACCESS_TOKEN=<ADDYOURTOKEN>
POLL_INTERVAL_SECONDS=30
MIN_BOOST_INTERVAL_SECONDS=3600
STATE_FILE=state.json
STARTUP_SKIP_EXISTING=true
LOG_FILE=bot.log
LOG_LEVEL=INFO
```

