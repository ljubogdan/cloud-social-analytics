from aws_cdk import (
        Stack,
        Duration,
        Size,
        aws_lambda as _lambda,
        aws_iam as iam,
        aws_events as events,
        aws_events_targets as targets,
    )
from constructs import Construct

class HackerNewsPostsSilverStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, data_bucket, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        role = iam.Role(
            self,
            "HackerNewsPostsSilverRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        data_bucket.grant_read(role, "bronze/hacker-news/*")
        data_bucket.grant_write(role, "silver/posts/*")
        data_bucket.grant_write(role, "silver/post_relations/*")

        wrangler_layer = _lambda.LayerVersion.from_layer_version_arn(
            self,
            "WranglerLayer",
            "arn:aws:lambda:eu-central-1:336392948345:layer:AWSSDKPandas-Python312:1"
        )

        fn = _lambda.Function(
            self,
            "HackerNewsPostsSilverLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="hacker_news_posts_extraction.handler",
            code=_lambda.Code.from_asset("lambdas/hackerNewsPostsExtraction"),
            role=role,
            timeout=Duration.minutes(15),
            memory_size=3007,
            ephemeral_storage_size=Size.gibibytes(10),
            environment={
                "BUCKET_NAME": data_bucket.bucket_name,
            },
            layers=[wrangler_layer],
        )

        events.Rule(
            self,
            "HackerNewsPostsTrigger",
            event_pattern=events.EventPattern(
                source=["socialanalytics.hackernews"],
                detail_type=["HackerNewsIngestionCompleted"]
            ),
            targets=[
                targets.LambdaFunction(fn)
            ]
        )