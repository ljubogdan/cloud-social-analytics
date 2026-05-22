import os
import boto3

os.environ["KAGGLEHUB_CACHE"] = "/tmp/kaggle"
import kagglehub


bucket_name = os.environ['BUCKET_NAME']
s3 = boto3.resource('s3')

def twitter_fetcher(event, context):
    dataset_path = kagglehub.dataset_download("kaushiksuresh147/bitcoin-tweets")

    bucket = s3.Bucket(bucket_name)
    for root, dirs, files in os.walk(dataset_path):
        for file in files:
            local_path = os.path.join(root, file)
            relative_path = os.path.relpath(local_path, dataset_path)
            s3_key = f"bronze/twitter/{relative_path}"
            print(f"Uploading {local_path} to s3://{bucket_name}/{s3_key}")
            bucket.upload_file(
                Filename=local_path,
                Key=s3_key
            )

    return {
        "statusCode": 200,
        "body": f"Twitter dataset successfully uploaded to: '{bucket_name}'"
    }

if __name__ == "__main__":
    data_path = kagglehub.dataset_download("kaushiksuresh147/bitcoin-tweets")
    print(data_path)