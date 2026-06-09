from aws_cdk import (
    Duration,
    Stack,
    aws_s3 as s3,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    BundlingOptions,
    CfnOutput,
)

from constructs import Construct


class HackerNewsFetcherFunctionStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, data_bucket: s3.IBucket, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        lambda_role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        data_bucket.grant_read_write(lambda_role)

        hacker_news_function = _lambda.Function(
            self,
            "HackerNewsFetcher",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="hacker_news_fetcher.fetch_hacker_news",
            code=_lambda.Code.from_asset("lambdas/hackerNewsFetcher",
                                         bundling=BundlingOptions(
                                             image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                                             command=[
                                                 "bash", "-c",
                                                 "pip install --no-cache -r requirements.txt -t /asset-output && cp -r . /asset-output"
                                             ]
                                         )),
            role=lambda_role,
            timeout=Duration.minutes(10),
            memory_size=512,
            environment={
                "BUCKET_NAME": data_bucket.bucket_name,
            },
        )

        events.Rule(
            self,
            "HackerNewsSchedule",
            schedule=events.Schedule.cron(hour="12", minute="0"),
            targets=[targets.LambdaFunction(hacker_news_function)],
        )

        hn_url = hacker_news_function.add_function_url(
            auth_type=_lambda.FunctionUrlAuthType.AWS_IAM,
            cors=_lambda.FunctionUrlCorsOptions(
                allowed_origins=["*"]
            )
        )

        CfnOutput(
            self,
            "HackerNewsFunctionUrl",
            value=hn_url.url
        )