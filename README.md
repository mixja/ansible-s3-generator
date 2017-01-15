# Ansible CloudFormation S3 Generator

This repository defines the Lamdba function `ansibleS3Generator`.

This function supports the build and publishing of the following CloudFormation deployment artifacts suitable for use with the AWS CodePipeline CloudFormation deployment action:

- CloudFormation template file
- CloudFormation configuration file including stack input parameters and stack policy

This function generates the above for each environment defined in a given Ansible deployment repository `inventory` file, and then zips and publishes all artifacts to an S3 bucket.

The function is triggered via SNS notifications sent from GitHub each time the GitHub repository is committed to.  

The following actions are executed by this function:

- Parse GitHub event received via SNS
- Clone deployment repository locally
- Run Ansible playbook to generate template and configuration files for each environment defined in the local `inventory` file
- Create ZIP archive of all environment template and configuration files
- Push ZIP archive to configured S3 bucket and object

## Build Instructions

Any dependencies need to defined in `src/requirements.txt`.  Note that you do not need to include `boto3`, as this is provided by AWS for Python Lambda functions.

To build the function and its dependencies:

`make build`

This will create the necessary dependencies in the `src` folder and create a ZIP package in the `build` folder.  This file is suitable for upload to the AWS Lambda service to create a Lambda function.

```
$ make build
=> Removed all distributions
=> Building ansibleS3Generator.zip...
Collecting ansible (from -r requirements.txt (line 1))
Collecting dulwich (from -r requirements.txt (line 2))Successfully installed cfn-lambda-handler-1.0.2
...
...
=> Built build/ansibleS3Generator.zip
```

### Function Naming

The default name for this function is `ansibleS3Generator` and the corresponding ZIP package that is generated is called `ansibleS3Generator.zip`.

If you want to change the function name, set the `FUNCTION_NAME` environment variable to the custom function name.

## Publishing the Function

When you publish the function, you are simply copying the built ZIP package to an S3 bucket.  Before you can do this, you must ensure your environment is configured correctly with appropriate AWS credentials.

To deploy the built ZIP package:

`make publish`

This will upload the built ZIP package to an appropriate S3 bucket as defined via the `S3_BUCKET` Makefile/Environment variable.

### Publish Example

```
$ export AWS_PROFILE=caintake-admin
$ make publish
=> Publishing ansibleS3Generator.zip to s3://429614120872-cfn-lambda...
=> Published to S3 URL: https://s3-us-west-2.amazonaws.com/429614120872-cfn-lambda/ansibleS3Generator.zip
=> S3 Object Version: 86jHvErMu.CpTjqBvSlJabgr22pYGa9S
```

## CloudFormation Usage

This function is designed to be called from a CloudFormation template as a custom resource.

The custom resource Lambda function must first be created with the following requirements:

- The Lambda handler must be configured as `cfn_kms_decrypt.handler`
- The Lambda runtime must be `python2.7`
- The Lambda function must be published to an S3 bucket, with a known S3 object key and object version
- The KMS key used for encryption must be exist before the CloudFormation stack is used (i.e. it cannot be created as part of the same stack)
- The Lambda function must have KMS decrypt privileges for the KMS key used to encrypt the credentials 
- The Lambda function must have privileges to manage its own log group for logging

The following CloudFormation snippet demonstrates creating an AWS Lambda function with an example IAM role.

```
Resources:
  ...
  ...
  KMSDecrypter:
    Type: "AWS::Lambda::Function"
    Properties:
      Description: 
        Fn::Sub: "${AWS::StackName} KMS Decrypter"
      Handler: "cfn_kms_decrypt.handler"
      MemorySize: 128
      Runtime: "python2.7"
      Timeout: 300
      Role: 
        Fn::Sub: ${KMSDecrypterRole.Arn}
      FunctionName: 
        Fn::Sub: "${AWS::StackName}-ansibleS3Generator"
      Code:
        S3Bucket: 
          Fn::Sub: "${AWS::AccountId}-cfn-lambda"
        S3Key: "ansibleS3Generator.zip"
        S3ObjectVersion: "86jHvErMu.CpTjqBvSlJabgr22pYGa9S"
  KMSDecrypterRole:
    Type: "AWS::IAM::Role"
    Properties:
      Path: "/"
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
        - Effect: "Allow"
          Principal: {"Service": "lambda.amazonaws.com"}
          Action: [ "sts:AssumeRole" ]
      Policies:
      - PolicyName: "KMSDecrypterPolicy"
        PolicyDocument:
          Version: "2012-10-17"
          Statement:
          - Sid: "Decrypt"
            Effect: "Allow"
            Action:
            - "kms:Decrypt"
            - "kms:DescribeKey"
            Resource:
              Fn::Sub: "arn:aws:kms:${AWS::Region}:${AWS::AccountId}:key/<key-id>"
          - Sid: "ManageLambdaLogs"
            Effect: "Allow"
            Action:
            - "logs:CreateLogGroup"
            - "logs:CreateLogStream"
            - "logs:PutLogEvents"
            - "logs:PutRetentionPolicy"
            - "logs:PutSubscriptionFilter"
            - "logs:DescribeLogStreams"
            - "logs:DeleteLogGroup"
            - "logs:DeleteRetentionPolicy"
            - "logs:DeleteSubscriptionFilter"
            Resource: 
              Fn::Sub: "arn:aws:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/${AWS::StackName}-ansibleS3Generator:*:*"
```

With the Lambda function in place, the following custom resource calls the Lambda function when the resource is created, updated or deleted:

```
Resources:
  ...
  ...
  DbPasswordDecrypt:
    Type: "Custom::KMSDecrypt"
    Properties:
      ServiceToken: 
        Fn::Sub: ${KMSDecrypter.Arn}
      Ciphertext: "<ciphertext>"
  ...
  ...
```

The `Ciphertext` value is required and must include valid KMS ciphertext output in a Base64 encoded format.

### Generating Ciphertext

You can generate the ciphertext to pass to your CloudFormation stacks by using the AWS CLI, specifying the appropriate KMS Key Id and plaintext you want to encrypt.  The returned `CiphertextBlob` value is the Base64 encoded ciphertext that is expected for the KMS decrypt custom resource.

> NOTE: You must have permissions to be able to encrypt using the KMS Key Id specified

```
$ aws kms encrypt --key-id 3ea941bf-ee54-4941-8f77-f1dd417667cd --plaintext 'Hello World!'
{
    "KeyId": "arn:aws:kms:us-west-2:429614120872:key/3ea941bf-ee54-4941-8f77-f1dd417667cd",
    "CiphertextBlob": "AQECAHgohc0dbuzR1L3lEdEkDC96PMYUEV9nITogJU2vbocgQAAAAGowaAYJKoZIhvcNAQcGoFswWQIBADBUBgkqhkiG9w0BBwEwHgYJYIZIAWUDBAEuMBEEDB4uW3mVBu3L8ErR1AIBEIAnSkLisBBGibq5wjbMR/0Ew9QDAbP37gXU8jdOYYZFzNOO8IwbnvHS"
}
```

### Return Values

This function will return the following properties to CloudFormation:

| Property  | Description                                  |
|-----------|----------------------------------------------|
| Plaintext | Plaintext output of the decrypted Ciphertext |

For example, you can obtain the plaintext value of encrypted ciphertext as demonstrated below.  In this example, the DbPassword parameter is KMS encrypted ciphertext that is supplied as an input parameter to the stack.

```
Parameters:
  DbPassword:
    Type: String
    Description: KMS encrypted database password
Resources:
  DbPasswordDecrypt:
    Type: "Custom::KMSDecrypt"
    Properties:
      ServiceToken: "arn:aws:lambda:us-west-2:429614120872:function:my-product-dev-ansibleS3Generator"
      Ciphertext: { "Ref": "DbPassword" }
  DbInstance:
    Type: "AWS::RDS::DBInstance"
    Properties:
      ...
      MasterUserPassword:
        Fn::Sub: ${DbPasswordDecrypt.Plaintext}
```