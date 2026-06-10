#!/usr/bin/env python3
from aws_cdk import App, Environment
from cloud_social_analytics_stacks.bronze_layer_stacks.data_stack.data_stack import DataStack
from cloud_social_analytics_stacks.bronze_layer_stacks.function_stacks.twitter_fetcher_function_stack import TwitterFetcherFunctionStack
from cloud_social_analytics_stacks.bronze_layer_stacks.function_stacks.hacker_news_fetcher_function_stack import HackerNewsFetcherFunctionStack
from cloud_social_analytics_stacks.silver_layer_stacks.twitter_posts_function_stack import TwitterPostsSilverStack
from cloud_social_analytics_stacks.silver_layer_stacks.twitters_users_function_stack import TwitterUsersSilverStack

app = App()

env = Environment(region = "eu-central-1")

data_stack = DataStack(app, "SocialAnalyticsDataStack", env = env)

twitter_function_stack = TwitterFetcherFunctionStack(
    app,
    "SocialAnalyticsTwitterFunctionStack",
    data_stack.data_lake,
    env = env
)

hacker_news_function_stack = HackerNewsFetcherFunctionStack(
    app,
    "SocialAnalyticsHackerNewsFunctionStack",
    data_stack.data_lake,
    env = env
)

twitter_users_silver_stack = TwitterUsersSilverStack(
    app,
    "SocialAnalyticsTwitterUsersSilverStack",
    data_stack.data_lake,
    env = env
)

twitter_posts_silver_stack = TwitterPostsSilverStack(
    app,
    "SocialAnalyticsTwitterPostsSilverStack",
    data_stack.data_lake,
    env = env
)

app.synth()