import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from mastodon import Mastodon, MastodonAPIError, MastodonNetworkError


class BoostOnlyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().startswith("Boosted ")


def parse_bool(value: str, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_state(path: Path) -> dict:
    if not path.exists():
        return {
            "last_notification_id": None,
            "last_boost_per_user": {},
            "boosted_status_ids": {},
        }
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_state(path: Path, state: dict) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle)
    tmp_path.replace(path)


def prune_state(state: dict, now: float, min_interval: int) -> None:
    user_expire = min_interval * 2
    status_expire = 24 * 3600
    state["last_boost_per_user"] = {
        acct: ts
        for acct, ts in state["last_boost_per_user"].items()
        if now - ts <= user_expire
    }
    state["boosted_status_ids"] = {
        sid: ts
        for sid, ts in state["boosted_status_ids"].items()
        if now - ts <= status_expire
    }


def main() -> int:
    load_dotenv()

    base_url = os.getenv("MASTODON_BASE_URL")
    access_token = os.getenv("ACCESS_TOKEN")
    poll_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
    min_interval = int(os.getenv("MIN_BOOST_INTERVAL_SECONDS", "3600"))
    state_file = Path(os.getenv("STATE_FILE", "state.json"))
    log_file = os.getenv("LOG_FILE", "bot.log")
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    startup_skip_existing = parse_bool(
        os.getenv("STARTUP_SKIP_EXISTING", "true"), True
    )

    if not base_url or not access_token:
        logging.error(
            "Missing config: MASTODON_BASE_URL and ACCESS_TOKEN are required."
        )
        return 2

    logger = logging.getLogger()
    logger.setLevel(log_level)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(BoostOnlyFilter())
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(log_level)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    mastodon = Mastodon(api_base_url=base_url, access_token=access_token)
    bot_acct = mastodon.account_verify_credentials()["acct"]
    logging.info("Authenticated as %s on %s", bot_acct, base_url)

    state = load_state(state_file)

    while True:
        now = time.time()
        prune_state(state, now, min_interval)

        if state["last_notification_id"] is None and startup_skip_existing:
            notifications = mastodon.notifications()
            if notifications:
                max_id = max(int(item["id"]) for item in notifications)
                state["last_notification_id"] = str(max_id)
                save_state(state_file, state)
                logging.info(
                    "Startup skip enabled, setting last_notification_id=%s",
                    state["last_notification_id"],
                )
            time.sleep(poll_interval)
            continue

        try:
            notifications = mastodon.notifications(
                since_id=state["last_notification_id"]
            )
        except (MastodonNetworkError, MastodonAPIError) as exc:
            logging.warning("Notification fetch failed: %s", exc)
            time.sleep(poll_interval)
            continue

        logging.info(
            "Fetched %s notifications since_id=%s",
            len(notifications),
            state["last_notification_id"],
        )
        if notifications:
            for item in sorted(notifications, key=lambda n: int(n["id"])):
                state["last_notification_id"] = item["id"]
                if item["type"] != "mention":
                    continue
                status = item.get("status")
                if not status:
                    continue
                account = status.get("account", {})
                acct = account.get("acct")
                if not acct or acct == bot_acct:
                    continue

                now = time.time()
                last_boost = state["last_boost_per_user"].get(acct, 0)
                if now - last_boost < min_interval:
                    logging.info(
                        "Skipping %s; boosted %s seconds ago",
                        acct,
                        int(now - last_boost),
                    )
                    continue

                status_id = str(status["id"])
                if status_id in state["boosted_status_ids"]:
                    logging.info("Skipping %s; already boosted", status_id)
                    continue

                try:
                    mastodon.status_reblog(status["id"])
                except (MastodonNetworkError, MastodonAPIError) as exc:
                    logging.warning("Boost failed for %s: %s", status_id, exc)
                    continue

                state["last_boost_per_user"][acct] = now
                state["boosted_status_ids"][status_id] = now
                logging.info("Boosted %s from %s", status_id, acct)

            save_state(state_file, state)

        time.sleep(poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
