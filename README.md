# Why using Lambda Layers?

The benefits of AWS Lambda Layers should not be missed. With Lambda Layers you get the possibility to package code which can then be reused in different functions.

In big environments usually all Lambda Layers are located in one specific account and then shared via RAM (?) to then get used by the corresponding functions.

You can use Lambda layers either to write your own functions or to make entire packages available which are not covered by the Lambda [runtimes](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html). This blog article will provide you a solution on how you can upload Lambda layer packages with complex folder structures to a S3 Bucket. As you should always deploy your resources with Infrastructure as Code, a manual upload is not a satisfying solution here.

# Deep-Dive into the Lambda Function

All steps are covered in one Lambda function. Depending on your favor, you can also split them up. In this example I will guide you through all steps being executed in one function.

## Summary of the procedure

The base procedure is as follows: 
The package is placed in our Customizations for Control Tower (CfCT) repository. A Lambda functions checks the path where the package is located, and recursively loop through all folder, sub folders and files. 
The solution leverages the non-persistent storage provided by default in every Lambda function. The same folder and file structure then gets created in the local `/tmp` directory. 
After that the local directory gets zipped and uploaded to S3 where another automatism gets the Zip File to then add it to the Lambda layers.

![Architecture](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/i698rmwb8e8myqj2ymed.png)

This blog article should only focus on the upload part to S3. This part is quite tricky, because the folder structure is not clear and the automatism should stay dynamic enough to also be used for further packages which should get added as a layer with different folder structures.

## Necessary environment variables

This example uses Bitbucket as a repository hosting service. Prerequisites are a working CodeStar Connection between the CfCT pipeline including authentication to have the necessary access to the repository. 

Corresponding environment variables should be set in the Lambda function which have all necessary Bitbucket information included like the Bitbucket workspace, the repository name, the token parameter and the branch name. 

Another environment parameter is a list of the folder paths, where the packages are located. Also the S3 bucket where the Zip file will get uploaded should be set as an environment variable

## How to trigger the Lambda function

The Lambda function gets triggered as soon as the CodePipeline starts. You can realize this with a separate CodePipeline or an EventBridge Trigger which listens to the corresponding CloudTrail event.

First the API token is retrieved from an encrypted SSM Parameter to be able to set up the connection to the Bitbucket repository 

## Collecting all items from the repository

The Lambda functions loops through every entry of the folder path variable and calls the `getFolder` method

In the `getFolder` method the base URL for Bitbucket is joined and the token is set in the headers variable. This step is necessary to access the remote repository.


After that the `getAllItems` method gets called. An empty list variable gets initialized and with the help of the request package  a `get` method gets called to capture all the files from the provided folder path out of the repository


Back to the `getFolder` method, the `localFolderPath` gets set to `/tmp`  because this is where the package structure should be temporarily saved. With the help of the `os` package and the `makedirs` package a folder with the same name gets created in the Lambda functions environment. 


## Local creation of the package structure

Now comes the complicated part: The function iterates through all items retrieved from the getAllItems method using a for-loop. The item object looks like this: 

```
{
  "path": "lambda/layers/xxxxx",
  "commit": {
    "hash": "xxxxx",
    "links": {
      "self": {
        "href": "https://api.bitbucket.org/2.0/repositories/xxxxx/commit/xxxxx"
      },
      "html": {
        "href": "https://bitbucket.org/xxxxx/commits/xxxxx"
      }
    },
    "type": "commit"
  },
  "type": "commit_file",
  "attributes": [],
  "escaped_path": "lambda/layers/xxxx",
  "size": 1779,
  "mimetype": "text/x-python",
  "links": {
    "self": {
      "href": "https://api.bitbucket.org/2.0/repositories/xxxxx"
    },
    "meta": {
      "href": "https://api.bitbucket.org/2.0/repositories/xxxxx"
    },
    "history": {
      "href": "https://api.bitbucket.org/2.0/repositories/xxxxx"
    }
  }
}
```

The item path and the item type of the current file gets saved into two variables

If the item_type equals `commit directory`, the old path plus the name of the item gets set as the new_folder_path and the folder gets created in the `/tmp`  directory as well. After that, the `getFolder` function gets called again with the new folder path. 


If the `itemType` equals `commit_file`, the file name gets read out of the whole path. Then the `url` variable gets set to point to the file in the Bitbucket directory and is created in the `/tmp` directory under the correct sub folder.

## Zip and upload of the package to S3

After the for loop is finished, the processFolder function gets called to read out the package name of the Lambda package
The `addFolderToArchive` function gets called next.

This method is responsible for uploading the package structure to S3. First the current timestamp is generated, then the name of the Zip file is set. With the `shutil` package the folder gets zipped via the `make_archive` function and uploaded to the provided bucket from the environment variable. The last step is to save the package name with the timestamp in the end in a SSM parameter which can then further be used to build the part where the layer itself gets created and shared with the other accounts.

The local zip file gets created from the Lambda environment and the function is finished. 

