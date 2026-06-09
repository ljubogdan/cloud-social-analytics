import os
import io
import uuid

import boto3
import pandas as pd
import awswrangler as wr

BUCKET_NAME = os.environ['BUCKET_NAME']
s3 = boto3.client('s3')

def load_df(key: str) -> pd.DataFrame:
    obj = s3.get_object(Bucket=BUCKET_NAME, Key=key)
    data = obj["Body"].read()

    buffer = io.BytesIO(data)

    df = pd.read_csv(
        buffer,
        sep=",",
        engine="python",
        dtype=str,
        on_bad_lines="skip",
        encoding="utf-8-sig",
        quotechar='"',
        escapechar="\\",
        keep_default_na=False
    )

    return df

def load_all_twitter_csvs():
    response = s3.list_objects_v2(
        Bucket = BUCKET_NAME,
        Prefix = "bronze/twitter/"
    )

    dfs = []

    for obj in response.get("Contents", []):
        key = obj["Key"]

        if not key.endswith(".csv"):
            continue

        df = load_df(key)

        dfs.append(df)
    
    if not dfs:
        return pd.DataFrame()
    
    return pd.concat(dfs, ignore_index= True)

def make_user_id(username: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_DNS,
            f"X:{username}"
        )
    )

def build_users_dataframe(raw_df: pd.DataFrame):
    users_df = pd.DataFrame({
        "username": raw_df["user_name"],
        "platform": "X",
        "karma_score": None,
        "is_verified": raw_df["user_verified"],
        "created_at": pd.to_datetime(
            raw_df["user_created"],
            utc = True
        )
    })

    users_df["user_id"] = users_df["username"].apply(
        make_user_id
    )

    users_df = users_df[
        [
            "user_id",
            "username",
            "platform",
            "karma_score",
            "is_verified",
            "created_at"
        ]
    ]

    users_df = users_df.drop_duplicates(
        subset=["user_id"]
    )

    return users_df

def save_users(users_df: pd.DataFrame):
    wr.s3.to_parquet(
        df=users_df,
        path=f"s3://{BUCKET_NAME}/silver/users/",
        dataset=True,
        partition_cols=["platform"],
        mode="overwrite_partitions",
        filename_prefix="users",
    )

def handler(event, context):
    #raw_df = load_all_twitter_csvs()

    raw_df = load_df("bronze/twitter/Bitcoin_tweets_dataset_2.csv")

    if raw_df.empty:
        return {
            "statusCode": 200,
            "body": "No CSV files found"
        }
    
    raw_df["user_created"] = pd.to_datetime(
        raw_df["user_created"],
        errors="coerce",
        utc=True
    )

    users_df = build_users_dataframe(raw_df)

    save_users(users_df)

    return {
        "statusCode": 200,
        "body": f"Processed {len(users_df)} users"
    }