"""
Fetches messages and users from a given channel in order to perform a Slack audit.

General Usage:
  python scrape_slack.py -t <SLACK_TOKEN> -c <CHANNEL_NAME>

Example:
  python scrape_slack.py -t XXXXXXXXXXXXXXXX -c lnl-help-engineering
"""
import argparse
import datetime
from typing import List, Set
import logging
import re

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import pandas as pd


# define DataFrame column names once
USER_ID_COL = "user_id"
MSG_TS_COL = "message_ts"
MENTIONS_COL = "mentioned_users"
CHANNEL_NAME_COL = "channel_name"
CHANNEL_ID_COL = "channel_id"


class ChannelNotFound(Exception):
    pass


def get_channel(name: str, channels: List[dict]) -> dict:
    channel = next((c for c in channels if c["name_normalized"] == name), [])
    if not channel:
        logging.error(f"No channel found for: '{name}'")
        raise ChannelNotFound
    return channel


def get_channels(slack: WebClient, channel_names: List[str]) -> str:
    logging.debug("Fetching channels...")
    response = slack.conversations_list(types="public_channel, private_channel")
    channels = response["channels"]
    filtered_channels = [get_channel(name, channels) for name in channel_names]
    return filtered_channels


def get_all_members(slack: WebClient, channels: List[dict]) -> Set[str]:
    users = set()
    [users.update(get_channel_members(slack, c["id"])) for c in channels]
    return users


def get_channel_members(slack: WebClient, channel_id: str) -> Set[str]:
    logging.debug(f"Fetching users in channel_id {channel_id}...")
    response = slack.conversations_members(channel=channel_id)
    return set(response["members"])


# TODO delete this func if additional user data is no longer needed
def get_user_data(slack: WebClient, user_ids: Set[str]) -> pd.DataFrame:
    logging.debug(f"Fetching user data for {len(user_ids)} users...")
    user_df = pd.DataFrame(columns=[USER_ID_COL])
    for user_id in user_ids:
        response = slack.users_profile_get(user=user_id)
        profile = response["profile"]
        user_df = user_df.append(
            {
                USER_ID_COL: user_id,
            },
            ignore_index=True,
        )

    return user_df


def get_mentions(text: str) -> List[str]:
    # mentioned user syntax look like: <@U123ABC>
    # the following regex strips just the id's out: U123ABC
    prog = re.compile(r"<@(U\S*)>")
    return prog.findall(text)


def get_channel_messages(
    slack: WebClient, channel: dict, days_to_fetch: int
) -> pd.DataFrame:
    channel_id = channel["id"]
    logging.debug(f"Fetching messages for channel_id {channel_id}...")
    LIMIT = 200
    message_df = pd.DataFrame(columns=[USER_ID_COL, MSG_TS_COL, MENTIONS_COL])
    start_date = datetime.datetime.now() - datetime.timedelta(days=days_to_fetch)
    start_ts = start_date.timestamp()
    cursor = None
    while True:
        response = slack.conversations_history(
            channel=channel_id, oldest=start_ts, limit=LIMIT, cursor=cursor
        )
        messages = response["messages"]
        for message in messages:
            # bot messages will not have a user
            if not message.get("user"):
                continue

            message_df = message_df.append(
                {
                    USER_ID_COL: message["user"],
                    MSG_TS_COL: message["ts"],
                    MENTIONS_COL: get_mentions(message["text"]),
                    CHANNEL_NAME_COL: channel["name_normalized"],
                    CHANNEL_ID_COL: channel["id"],
                },
                ignore_index=True,
            )

        if response["has_more"]:
            cursor = response["response_metadata"]["next_cursor"]
        else:
            break

    return message_df


def get_file_name() -> str:
    return (
        str(datetime.datetime.now())
        .replace(" ", "-")
        .replace(":", "-")
        .replace(".", "-")
    )


def scrape_messages(channels: str, slack_token: str, days_to_fetch: int) -> None:
    logging.info("Fetching messages...")
    channel_names = channels.split(",")
    slack = WebClient(token=slack_token)
    try:
        channels = get_channels(slack, channel_names)
    except ChannelNotFound:
        logging.error("Please try again with valid channel names")
        return

    user_ids = get_all_members(slack, channels)
    user_df = get_user_data(slack, user_ids)
    message_df = pd.DataFrame()
    for channel in channels:
        _message_df = get_channel_messages(slack, channel, days_to_fetch)
        message_df = message_df.append(_message_df)

    message_df = message_df.merge(user_df, on=USER_ID_COL)
    file_name = get_file_name()
    relative_path = f"outputs/{file_name}.csv"
    message_df.to_csv(f"/app/{relative_path}")
    logging.info(f"Fetch complete. Output saved to: '{relative_path}'")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-c",
        "--channels",
        required=True,
        help="Comma-separated channels to audit",
    )
    ap.add_argument(
        "-t",
        "--token",
        required=True,
        help=f"Slack token from your app: https://api.slack.com/apps",
    )
    ap.add_argument(
        "-d",
        "--days",
        required=False,
        help="Number of days to scrape",
        type=int,
        default=365,
    )
    args = vars(ap.parse_args())
    channels = args["channels"]
    token = args["token"]
    days_to_fetch = args["days"]
    scrape_messages(channels, token, days_to_fetch)
