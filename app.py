#!/usr/bin/env python3
from aws_cdk import App, Environment
from cloud_social_analytics_stacks.bronze_layer_stacks.data_stack.data_stack import DataStack
from cloud_social_analytics_stacks.bronze_layer_stacks.function_stacks.twitter_fetcher_function_stack import TwitterFetcherFunctionStack
from cloud_social_analytics_stacks.bronze_layer_stacks.function_stacks.hacker_news_fetcher_function_stack import HackerNewsFetcherFunctionStack
from cloud_social_analytics_stacks.notifier_stack import NotifierStack
from cloud_social_analytics_stacks.silver_layer_stacks.hacker_news_posts_function_stack import HackerNewsPostsSilverStack
from cloud_social_analytics_stacks.silver_layer_stacks.hacker_news_posts_manual_function_stack import HackerNewsPostsManualSilverStack
from cloud_social_analytics_stacks.silver_layer_stacks.hacker_news_users_function_stack import HackerNewsUsersSilverStack
from cloud_social_analytics_stacks.silver_layer_stacks.hacker_news_users_manual_function_stack import HackerNewsUsersManualSilverStack
from cloud_social_analytics_stacks.silver_layer_stacks.twitter_posts_function_stack import TwitterPostsSilverStack
from cloud_social_analytics_stacks.silver_layer_stacks.twitters_users_function_stack import TwitterUsersSilverStack
from cloud_social_analytics_stacks.gold_layer_stacks.gold_hn_metrics_stack import GoldHnMetricsStack
from cloud_social_analytics_stacks.gold_layer_stacks.gold_twitter_metrics_stack import GoldTwitterMetricsStack

from dotenv import load_dotenv
load_dotenv()


app = App()

env = Environment(region = "eu-central-1")

data_stack = DataStack(app, "SocialAnalyticsDataStack", env = env)

lambdas = []

twitter_function_stack = TwitterFetcherFunctionStack(
    app,
    "SocialAnalyticsTwitterFunctionStack",
    data_stack.data_lake,
    env = env
)
lambdas.append(twitter_function_stack.twitter_function)


hacker_news_function_stack = HackerNewsFetcherFunctionStack(
    app,
    "SocialAnalyticsHackerNewsFunctionStack",
    data_stack.data_lake,
    env = env
)
lambdas.append(hacker_news_function_stack.hacker_news_function)

twitter_users_silver_stack = TwitterUsersSilverStack(
    app,
    "SocialAnalyticsTwitterUsersSilverStack",
    data_stack.data_lake,
    env = env
)
lambdas.append(twitter_users_silver_stack.fn)

twitter_posts_silver_stack = TwitterPostsSilverStack(
    app,
    "SocialAnalyticsTwitterPostsSilverStack",
    data_stack.data_lake,
    env = env
)
lambdas.append(twitter_posts_silver_stack.fn)

hacker_news_users_manual_silver_stack = HackerNewsUsersManualSilverStack(
    app,
    "SocialAnalyticsHackerNewsUsersManualSilverStack",
    data_stack.data_lake,
    env = env
)
lambdas.append(hacker_news_users_manual_silver_stack.fn)

hacker_news_posts_manual_silver_stack = HackerNewsPostsManualSilverStack(
    app,
    "SocialAnalyticsHackerNewsPostsManualSilverStack",
    data_stack.data_lake,
    env = env
)
lambdas.append(hacker_news_posts_manual_silver_stack.fn)

hacker_news_users_silver_stack = HackerNewsUsersSilverStack(
    app,
    "SocialAnalyticsHackerNewsUsersSilverStack",
    data_stack.data_lake,
    env = env
)
lambdas.append(hacker_news_users_silver_stack.fn)

hacker_news_posts_silver_stack = HackerNewsPostsSilverStack(
    app,
    "SocialAnalyticsHackerNewsPostsSilverStack",
    data_stack.data_lake,
    env = env
)
lambdas.append(hacker_news_posts_silver_stack.fn)


gold_hn_metrics_stack = GoldHnMetricsStack(
    app,
    "SocialAnalyticsGoldHnMetricsStack",
    data_stack.data_lake,
    env = env
)
lambdas.append(gold_hn_metrics_stack.fn)

gold_twitter_metrics_stack = GoldTwitterMetricsStack(
    app,
    "SocialAnalyticsGoldTwitterMetricsStack",
    data_stack.data_lake,
    env = env
)
lambdas.append(gold_twitter_metrics_stack.fn)

notifier_stack = NotifierStack(app, "NotifierStack", lambdas=lambdas, env=env)

app.synth()