#!/usr/bin/env python3
from aws_cdk import App, Environment
from cloud_social_analytics_stacks.data_stack import DataStack
from cloud_social_analytics_stacks.function_stack import FunctionStack



app = App()

env = Environment(region = "eu-central-1")

data_stack = DataStack(app, "SocialAnalyticsDataStack", env = env)

function_stack = FunctionStack(app, "SocialAnalyticsFunctionStack", data_stack.data_lake, env = env)

app.synth()