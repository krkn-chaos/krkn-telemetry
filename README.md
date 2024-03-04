# krkn-telemetry

This project aims to provide a basic, but fully working example on how to deploy your own [Krkn](https://github.com/redhat-chaos)
telemetry collection API.
We currently do not support the telemetry collection as a service for community users and we discourage to handover 
your infrastructure telemetry metadata to third parties since may contain confidential infos.

This guide will explain how to deploy the service automatically as an AWS lambda function, but you can easily deploy it as a
flask application in a VM or in any python runtime environment.

## Python env setup
Be sure that you have python 3.9 (we currently support this version) installed in your system.
To install the project dependency:

- create a new venv with `python3.9 -m venv venv`
- activate the venv with `source venv/bin/activate`
- install poetry `pip install poetry`
- install the dependencies with `poetry install`

## AWS Setup

### AWS CLI configuration
Be sure to have installed [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
in your system. 
[Create ACCESS_KEY and SECRET](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html) for the AWS IAM user
and then configure a profile with `aws configure --profile <profile_name>`.

### S3 Buckets
You must create two private buckets one to store the compiled code that will be published as a lambda function and the other
to store your telemetry data. We strongly suggest to name the buckets with the same prefix so will be easier to define
the IAM policy required to let zappa deploy your application stack.
Remember that S3 bucket names are unique across all the AWS accounts so choose the prefix wisely.

### IAM Permissions
In order to be able to deploy the application stack automatically, the designated IAM account must have the following policy attached.

**⚠️ Be sure to replace the <bucket_name_prefix> placeholder with the prefix of your choice**.
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "iam:AttachRolePolicy",
                "iam:GetRole",
                "iam:CreateRole",
                "iam:PassRole",
                "iam:PutRolePolicy",
                "lambda:*"
            ],
            "Resource": [
                "arn:aws:iam::452958939641:role/*-ZappaLambdaExecutionRole"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "apigateway:DELETE",
                "apigateway:GET",
                "apigateway:PATCH",
                "apigateway:POST",
                "apigateway:PUT",
                "events:DeleteRule",
                "events:DescribeRule",
                "events:ListRules",
                "events:ListRuleNamesByTarget",
                "events:ListTargetsByRule",
                "events:PutRule",
                "events:PutTargets",
                "events:RemoveTargets",
                "lambda:AddPermission",
                "lambda:CreateFunction",
                "lambda:DeleteFunction",
                "lambda:GetAlias",
                "lambda:GetFunction",
                "lambda:GetFunctionConfiguration",
                "lambda:GetPolicy",
                "lambda:InvokeFunction",
                "lambda:ListVersionsByFunction",
                "lambda:RemovePermission",
                "lambda:UpdateFunctionCode",
                "lambda:UpdateFunctionConfiguration",
                "cloudformation:CreateStack",
                "cloudformation:DeleteStack",
                "cloudformation:DescribeStackResource",
                "cloudformation:DescribeStacks",
                "cloudformation:ListStackResources",
                "cloudformation:UpdateStack",
                "logs:DeleteLogGroup",
                "logs:DescribeLogStreams",
                "logs:FilterLogEvents",
                "lambda:*"
            ],
            "Resource": [
                "*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:CreateBucket",
                "s3:ListBucket",
                "s3:ListBucketMultipartUploads"
            ],
            "Resource": [
                "arn:aws:s3:::<bucket_name_prefix>-*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:DeleteObject",
                "s3:GetObject",
                "s3:PutObject",
                "s3:AbortMultipartUpload",
                "s3:ListMultipartUploadParts",
                "lambda:*"
            ],
            "Resource": [
                "arn:aws:s3:::<bucket_name_prefix>-*/*"
            ]
        }
    ]
}
```


## Lambda Deployment

### zappa_settings.json
```json
{
    "production": {
        "app_function": "app.app",
        "aws_region": "us-west-1",
        "project_name": "krkn-telemetry",
        "runtime": "python3.9",
        "s3_bucket": "krkn-telemetry-test",
        "slim_handler": true
    }
}
```

Before launching the deployment configure the `zappa_settings.json` file with your preferences:
- **app_function**: flask application entrypoint (do not change)
- **aws_region**: AWS region of your choice
- **project_name**: the CloudFormation stack name that will be deployed
- **runtime**: the python runtime (do not change)
- **sr_bucket**: the S3 bucket previously created that will contain the application code
- **slim_handler**: enable the slim lambda handler for application bigger than 262.144MB uncompressed (do not change)

### Deployment
Export your preferred CLI lambda profile name as a variable with `export AWS_PROFILE=<profile_name>` and launch from your
activated python venv the command `zappa deploy` if it's your first deployment or `zappa update` if you're updating the stack.
This will deploy a preconfigured API gateway and a lambda function that will respond to the application queries.
If everything goes well, at the end of the process will be printed the lambda URL with a message like:
`Deployment complete!: https://8hl4t8kzec.execute-api.us-west-1.amazonaws.com/production`.
If you eventually want to delete the resources created (API Gateway and lambda function) run `zappa undeploy`.

⚠️ This example do not provide authentication, so your data will be publicly accessible visiting the lambda endpoint
at the path `https://<lambda_url>/production/download`.If you want to protect your data you'll have to put in place something
like a Gateway lambda authorizer ([Documentation](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-use-lambda-authorizer.html)) and 
implement your own authentication mechanism.

For more fine-grained zappa settings please refer to [zappa Documentation](https://github.com/zappa/Zappa).

### Lambda environment configuration

Once the lambda has been deployed it needs two environment variables to be set:

-  **BUCKET_NAME** The name of the bucket where the telemetry data will be stored
- **S3_LINK_EXPIRATION** The lifespan of the upload links generated by the API to allow Krkn to upload telemetry data.

To set a lambda environment variable please refer to the [AWS Documentation](https://docs.aws.amazon.com/lambda/latest/dg/configuration-envvars.html#configuration-envvars-config).

### Usage
If every step succeeded you should be able to configure your Krkn installation to point to your freshly installed API simply setting the [api_url](https://github.com/redhat-chaos/krkn/blob/c00328cc2b6966c3638cad55d7b6787504bb74fd/config/config.yaml#L70) 
value and enabling the various telemetry options in the Krkn config.yaml.
You'll be able to check and download the data collected visiting the telemetry service UI at the address `https://<lambda_url>/production/files`.
You will find a folder per each `telemetry_group` defined in krkn (all the runs without a `telemetry_group`  will be placed in the `default` folder) and each group folder containing run folders named with the krkn Run Id and a timestamp prefix and, if set, the value of the [run_tag](https://github.com/redhat-chaos/krkn/blob/c00328cc2b6966c3638cad55d7b6787504bb74fd/config/config.yaml#L78) string
that can be used as search term in the UI. 

## DISCLAIMER

This tutorial represents a basic example on how to deploy an **unauthenticated** and **unthrottled** AWS lambda function, that if targeted
by bad actors, **<u>may lead to sensitive data leaks and expensive AWS bills</u>**. 
Run this workload wisely and at **<u>your own risk</u>**.
