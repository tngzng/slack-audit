## slack-audit
A helper that uses the [Slack SDK](https://github.com/slackapi/python-slack-sdk) to fetch messages and user information to audit a team's usage of the platform.   

### run locally
1. Download the requirements:
```
pip install -r /app/requirements.txt
```
2. Scrape the last 90 days of messages in a Slack channel:
```
python scrape_slack.py -t <your_slack_token> -c <the_channel_to_scrape> -d 90
```
