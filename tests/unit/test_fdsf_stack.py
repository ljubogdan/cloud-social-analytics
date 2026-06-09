import aws_cdk as core
import aws_cdk.assertions as assertions

from cloud_social_analytics_stacks.bronze_layer_stacks.function_stacks.function_stack import CloudSocialAnalyticsStack

# example tests. To run these tests, uncomment this file along with the example
# resource in cloud_social_analytics/cloud_social_analytics_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = CloudSocialAnalyticsStack(app, "cloud_social_analytics")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
