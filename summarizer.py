#!/usr/bin/env python3
# https://github.com/masuidrive/slack-summarizer
# by [masuidrive](https://twitter.com/masuidrive) @ [Bloom&Co., Inc.](https://www.bloom-and-co.com/) 2023- [APACHE LICENSE, 2.0](https://www.apache.org/licenses/LICENSE-2.0)
import os
import re
import time
import pytz
from slack_sdk.errors import SlackApiError
from slack_sdk import WebClient
from datetime import datetime, timedelta

import openai
openai.api_key = str(os.environ.get('OPEN_AI_TOKEN')).strip()

# OpenAIのAPIを使って要約を行う


def summarize(text):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        temperature=0.5,
        messages=[
            {"role": "system", "content": "チャットログのフォーマットは発言者: 本文\\nになっている。\\nは改行を表しています。これを踏まえて指示に従います"},
            {"role": "user", "content": f"下記のチャットログを箇条書きで要約してください。。1行ずつの説明ではありません。全体として短く。\n\n{text}"}
        ]
    )
    return response["choices"][0]["message"]['content']


# APIトークンとチャンネルIDを設定する
TOKEN = str(os.environ.get('SLACK_BOT_TOKEN')).strip()
CHANNEL_ID = str(os.environ.get('SLACK_POST_CHANNEL_ID')).strip()

# 取得する期間を計算する
HOURS_BACK = 25
JST = pytz.timezone('Asia/Tokyo')
now = datetime.now(JST)
yesterday = now - timedelta(hours=HOURS_BACK)
start_time = datetime(yesterday.year, yesterday.month, yesterday.day,
                      yesterday.hour, yesterday.minute, yesterday.second)
end_time = datetime(now.year, now.month, now.day,
                    now.hour, now.minute, now.second)

# Slack APIクライアントを初期化する
client = WebClient(token=TOKEN)

# ユーザーIDからユーザー名に変換するために、ユーザー情報を取得する
try:
    users_info = client.users_list()
    all_members = users_info['members']
    print(f"users count = {len(all_members)}")

    while users_info["response_metadata"] and users_info["response_metadata"]["next_cursor"]:
        users_info = client.users_list(
            cursor=users_info["response_metadata"]["next_cursor"]
        )
        all_members.extend(users_info['members'])
        print(f"users count = {len(all_members)}")

    users_dict = []
    for user in all_members:
        if user["deleted"]:
            continue
        if user["is_bot"]:
            continue
        users_dict.append({"id": user['id'], "name": user["real_name"]})

except SlackApiError as e:
    print("Error : {}".format(e))
    exit(1)

# チャンネルIDからチャンネル名に変換するために、チャンネル情報を取得する
try:
    channels_info = client.conversations_list(
        types="public_channel",
        exclude_archived=True,
    )
    all_channels = channels_info['channels']
    print(f"channels count = {len(all_channels)}")

    while channels_info["response_metadata"] and channels_info["response_metadata"]["next_cursor"]:
        channels_info = client.conversations_list(
            types="public_channel",
            exclude_archived=True,
            cursor=channels_info["response_metadata"]["next_cursor"]
        )
        all_channels.extend(channels_info['channels'])
        print(f"channels count = {len(all_channels)}")

    channels = [channel for channel in all_channels
                if not channel["is_archived"] and channel["is_channel"]]
    channels = sorted(channels, key=lambda x: int(re.findall(
        r'\d+', x["name"])[0]) if re.findall(r'\d+', x["name"]) else float('inf'))
    
    channels_dict = []
    for channel in channels:
        channels_dict.append({"id": channel['id'], "name": channel["name"]})
except SlackApiError as e:
    print("Error : {}".format(e))
    exit(1)

# 指定したチャンネルの履歴を取得する

def load_messages(channel_id):
    try:
        response = client.conversations_history(
            channel=channel_id,
            oldest=start_time.timestamp(),
            latest=end_time.timestamp()
        )
        all_messages = response['messages']
        print(f"messages count = {len(all_messages)}")

        while response["response_metadata"] and response["response_metadata"]["next_cursor"]:
            response = client.conversations_history(
                channel=channel_id,
                oldest=start_time.timestamp(),
                latest=end_time.timestamp(),
                cursor=response["response_metadata"]["next_cursor"]
            )
            all_messages.extend(response['messages'])
            print(f"messages count = {len(all_messages)}")
        
    except SlackApiError as e:
        print("Error : {}".format(e))
        return None

    messages = list(filter(lambda m: "subtype" not in m, all_messages))

    if len(messages) < 1:
        return None

    messages_text = []

    for message in messages[::-1]:
        if "bot_id" in message:
            continue
        if message["text"].strip() == '':
            continue
        # ユーザーIDからユーザー名に変換する
        user_id = message['user']
        sender_name = None
        for user in users_dict:
            if user['id'] == user_id:
                sender_name = user['name']
                break
        if sender_name is None:
            sender_name = user_id

        # テキスト取り出し
        text = message["text"].replace("\n", "\\n")

        # メッセージ中に含まれるユーザーIDやチャンネルIDを名前やチャンネル名に展開する
        matches = re.findall(r"<@[A-Z0-9]+>", text)
        for match in matches:
            user_id = match[2:-1]
            user_name = None
            for user in users_dict:
                if user['id'] == user_id:
                    user_name = user['name']
                    break
            if user_name is None:
                user_name = user_id
            text = text.replace(match, f"@{user_name} ")

        matches = re.findall(r"<#[A-Z0-9]+>", text)
        for match in matches:
            channel_id = match[2:-1]
            channel_name = None
            for channel in channels_dict:
                if channel['id'] == channel_id:
                    channel_name = channel['name']
                    break
            if channel_name is None:
                channel_name = channel_id
            text = text.replace(match, f"#{channel_name} ")
        messages_text.append(f"{sender_name}: {text}")
    if len(messages_text) == 0:
        return None
    else:
        print("-----")
        print(f"{messages_text}")
        print("-----")
        return messages_text


result_text = []
channels_dict = [{"id": "C014M35N3DH", "name": "times_technθ"}]
for channel in channels_dict:
    messages = load_messages(channel["id"])
    print(f"channel id={channel['id']} name={channel['name']} messages={len(messages)}")
    if messages != None:
        text = summarize(messages)
        result_text.append(f"----\n<#{channel['id']}>\n{text}")

title = (f"{yesterday.strftime('%Y-%m-%d')}のpublic channelの要約")
print(result_text)

# response = client.chat_postMessage(
#     channel=CHANNEL_ID,
#     text=title+"\n\n"+"\n\n".join(result_text)
# )
print("Message posted: ", response["ts"])
