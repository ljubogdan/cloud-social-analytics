import datetime
import os
import boto3
import requests
import json


bucket_name = os.environ['BUCKET_NAME']
s3 = boto3.resource('s3')

def fetch_hacker_news(event, context):
    base_url = "http://hn.algolia.com/api/v1"

    bucket = s3.Bucket(bucket_name)

    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date()
    yesterday = today - datetime.timedelta(days=1)
    start_yesterday = datetime.datetime.combine(yesterday, datetime.datetime.min.time(), tzinfo=datetime.timezone.utc).timestamp()
    end_yesterday = datetime.datetime.combine(yesterday, datetime.datetime.max.time(), tzinfo=datetime.timezone.utc).timestamp()

    tags = ["story", "comment", "ask_hn", "job", "poll"]

    for tag in tags:
        page = 0
        prefix = f"bronze/hacker-news/year:{yesterday.year}/month:{yesterday.month:02d}/day:{yesterday.day:02d}/{tag}"
        while True:
            response = requests.get(
                base_url + "/search_by_date",
                params={
                    "tags": tag,
                    "numericFilters": f"created_at_i>{start_yesterday},created_at_i<{end_yesterday}",
                    "hitsPerPage": 1000,
                    "page": page
                }
            )

            data = response.json()
            hits = data["hits"]
            print(data["nbPages"])
            print(len(hits))
            print(data.get("query"))

            if not hits:
                break

            bucket.put_object(
                Key=f"{prefix}/page_{page}.json",
                Body=json.dumps(hits),
                ContentType='application/json'
            )

            page += 1

if __name__ == "__main__":
    fetch_hacker_news("a", "c")
