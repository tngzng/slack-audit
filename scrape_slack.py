"""
Fetches messages and users from a given channel in order to perform a Slack audit.

General Usage:
  python scrape_slack.py -t <SLACK_TOKEN> -c <CHANNEL_NAME>

Example:
  python scrape_slack.py -t XXXXXXXXXXXXXXXX -c lnl-help-engineering
"""
import argparse
import datetime
from typing import List
import logging

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import pandas as pd


# define DataFrame column names once
USER_NAME_COL = "user_name"
USER_ID_COL = "user_id"
USER_EMAIL_COL = "user_email"
MSG_TYPE_COL = "message_type"
USER_ID_COL = "user_id"
MSG_TEXT_COL = "message_text"
MSG_TS_COL = "message_ts"


def get_channel_id(slack: WebClient, channel_name: str) -> str:
    logging.info(f"Fetching channel_id for channel {channel_name}...")
    response = slack.conversations_list(types="public_channel, private_channel")
    channels = response["channels"]
    channel_id = next(
        (c["id"] for c in channels if c["name_normalized"] == channel_name), []
    )
    return channel_id


def get_all_members(slack: WebClient, channel_id: str) -> List[str]:
    logging.info(f"Fetching users in channel_id {channel_id}...")
    response = slack.conversations_members(channel=channel_id)
    return response["members"]


def get_user_data(slack: WebClient, user_ids: List[str]) -> pd.DataFrame:
    logging.info(f"Fetching user data for {len(user_ids)} users...")
    user_df = pd.DataFrame(columns=[USER_NAME_COL, USER_ID_COL, USER_EMAIL_COL])
    for user_id in user_ids:
        response = slack.users_profile_get(user=user_id)
        profile = response["profile"]
        user_df = user_df.append(
            {
                USER_NAME_COL: profile["display_name_normalized"],
                USER_ID_COL: user_id,
                USER_EMAIL_COL: profile.get("email", ""),
            },
            ignore_index=True,
        )

    return user_df


def get_channel_messages(
    slack: WebClient, channel_id: str, days_to_fetch: int
) -> pd.DataFrame:
    logging.info(f"Fetching messages for channel_id {channel_id}...")
    LIMIT = 200
    message_df = pd.DataFrame(
        columns=[MSG_TYPE_COL, USER_ID_COL, MSG_TEXT_COL, MSG_TS_COL]
    )
    start_date = datetime.datetime.now() - datetime.timedelta(days=days_to_fetch)
    start_ts = start_date.timestamp()
    cursor = None
    while True:
        response = slack.conversations_history(
            channel=channel_id, oldest=start_ts, limit=LIMIT, cursor=cursor
        )
        messages = response["messages"]
        logging.info(f"FETCHED {len(messages)} messages")
        for message in messages:
            # bot messages will not have a user
            if not message.get("user"):
                continue

            message_df = message_df.append(
                {
                    MSG_TYPE_COL: message["type"],
                    USER_ID_COL: message["user"],
                    MSG_TEXT_COL: message["text"],
                    MSG_TS_COL: message["ts"],
                },
                ignore_index=True,
            )

        if response["has_more"]:
            cursor = response["response_metadata"]["next_cursor"]
        else:
            break

    return message_df


def run_audit(channel_name: str, slack_token: str, days_to_fetch: int) -> None:
    logging.info("Starting audit...")
    slack = WebClient(token=slack_token)
    channel_id = get_channel_id(slack, channel_name)
    if not channel_id:
        logging.info(f"No channel found matching name: {channel_name}")
        return
    user_ids = get_all_members(slack, channel_id)
    user_df = get_user_data(slack, user_ids)
    message_df = get_channel_messages(slack, channel_id, days_to_fetch)
    message_df = message_df.merge(user_df, on=USER_ID_COL)
    output_path = f"/app/outputs/{channel_name}.csv"
    message_df.to_csv(output_path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--channel", required=True, help="Channel to audit")
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
    channel = args["channel"]
    token = args["token"]
    days_to_fetch = args["days"]
    run_audit(channel, token, days_to_fetch)
