import os
from aws_cdk import (
    Duration,
    Stack,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_lambda as _lambda,
)
from constructs import Construct

class NotifierStack(Stack):
    def __init__(self, scope: Construct, id: str, lambdas: list[_lambda.Function], **kwargs):
        super().__init__(scope, id, **kwargs)

        discord_notifier = _lambda.Function(
            self, "DiscordNotifier",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="discord_notifier.handler",
            code=_lambda.Code.from_asset("lambdas/discordNotifier"),
            environment={
                "DISCORD_WEBHOOK_URL": os.environ["DISCORD_WEBHOOK_URL"],
            },
        )


        alarm_topic = sns.Topic(self, "LambdaAlarmTopic")
        alarm_topic.add_subscription(
            subscriptions.LambdaSubscription(discord_notifier)
        )

        for fn in lambdas:
            alarm = cloudwatch.Alarm(
                self, f"{fn.node.id}ErrorAlarm",
                metric=fn.metric_errors(period=Duration.minutes(1)),
                threshold=1,
                evaluation_periods=1,
                alarm_description=f"{fn.node.id} lambda failed",
            )
            alarm.add_alarm_action(cw_actions.SnsAction(alarm_topic))