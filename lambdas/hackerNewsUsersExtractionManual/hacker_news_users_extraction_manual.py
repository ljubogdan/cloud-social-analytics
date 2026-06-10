import os
import json
import uuid
import boto3
import awswrangler as wr
import pandas as pd

BUCKET_NAME = os.environ["BUCKET_NAME"]
s3 = boto3.client("s3")

def make_user_id(username: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"HN:{username}"))

def handler(event, context):
    prefix = "bronze/hacker-news/"

    response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)

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

    wr.s3.to_parquet(
        df=df,
        path=f"s3://{BUCKET_NAME}/silver/users/",
        dataset=True,
        mode="overwrite_partitions",
        partition_cols=["platform"]
    )

    return {
        "status": "Completed",
        "users_count": len(df)
    }