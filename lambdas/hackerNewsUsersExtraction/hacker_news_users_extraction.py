from concurrent.futures import ThreadPoolExecutor
import os
import json
import uuid
import boto3
import awswrangler as wr
import pandas as pd
import requests

BUCKET_NAME = os.environ["BUCKET_NAME"]
s3 = boto3.client("s3")

def get_karma(username):
    try:
        response = requests.get(
            f"https://hacker-news.firebaseio.com/v0/user/{username}/karma.json",
            timeout=5
        )

        if response.status_code == 200:
            return int(response.text)

    except Exception:
        pass

    return None

def make_user_id(username: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"HN:{username}"))

def handler(event, context):
    prefix = event["detail"]["prefix"]

    response = s3.list_objects_v2(
        Bucket=BUCKET_NAME,
        Prefix=prefix
    )

    if "Contents" not in response:
        return {"status": "No files found"}

    users = {}

    for obj in response["Contents"]:
        key = obj["Key"]

        if not key.endswith(".json"):
            continue

        file_obj = s3.get_object(Bucket=BUCKET_NAME, Key=key)
        data = json.loads(file_obj["Body"].read())

        for item in data:
            author = item.get("author")

            if not author:
                continue

            created_at = item.get("created_at")

            if author in users:
                continue

            users[author] = {
                "user_id": make_user_id(author),
                "username": author,
                "platform": "HackerNews",
                "karma_score": None,
                "is_verified": None,
                "created_at": pd.to_datetime(created_at, utc=True, errors="coerce")
            }

    if not users:
        return {"status": "No users found"}

    df = pd.DataFrame(list(users.values()))
    df = df.dropna(subset=["created_at"])

    existing = wr.s3.read_parquet(
        path=f"s3://{BUCKET_NAME}/silver/users/platform=HackerNews/"
    )

    existing_usernames = set(existing["username"])

    df = df[
        ~df["username"].isin(existing_usernames)
    ]

    if df.empty:
        return {"status": "No new users to process"}

    with ThreadPoolExecutor(max_workers=20) as executor:
        df["karma_score"] = list(
            executor.map(get_karma, df["username"])
        )

    wr.s3.to_parquet(
        df=df,
        path=f"s3://{BUCKET_NAME}/silver/users/",
        dataset=True,
        mode="append",
        partition_cols=["platform"]
    )

    return {
        "status": "Completed",
        "users_count": len(df)
    }