#!/usr/bin/env python3
from aws_cdk import App, Environment
from cloud_social_analytics_stacks.bronze_layer_stacks.data_stack.data_stack import DataStack
from cloud_social_analytics_stacks.bronze_layer_stacks.function_stacks.twitter_fetcher_function_stack import TwitterFetcherFunctionStack
from cloud_social_analytics_stacks.bronze_layer_stacks.function_stacks.hacker_news_fetcher_function_stack import HackerNewsFetcherFunctionStack


app = App()

env = Environment(region = "eu-central-1")

data_stack = DataStack(app, "SocialAnalyticsDataStack", env = env)

twitter_function_stack = TwitterFetcherFunctionStack(app, "SocialAnalyticsTwitterFunctionStack", data_stack.data_lake, env = env)
hacker_news_function_stack = HackerNewsFetcherFunctionStack(app, "SocialAnalyticsHackerNewsFunctionStack", data_stack.data_lake, env = env)

app.synth()