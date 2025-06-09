import os
import boto3
import datetime
import requests
import shutil
from botocore.exceptions import ClientError

BITBUCKET_WORKSPACE_NAME = os.environ['WORKSPACE_NAME']
BITBUCKET_REPO_NAME = os.environ['REPOSITORY_NAME']
BITBUCKET_TOKEN_PARAMETER = os.environ['BITBUCKET_TOKEN_PARAMETER']
BITBUCKET_BRANCH_NAME = os.environ['BRANCH_NAME']
BUCKET_NAME = os.environ['BUCKET_NAME']

def lambda_handler(event, context):
 
    token = getApiToken()
    # Reading out folder paths from environment variable
    folderPaths = list(os.environ['FOLDER_PATHS'].split(','))
    for folderPath in folderPaths:
        try:
            # Start initalize function for every folderPath
            initialize(token, folderPath)
        except Exception as e:
            print(f'Could not be executed for {folderPath}')
            print(f'Error: {e}')

## Function to read out API Token from encrypted SSM Parameter
def getApiToken():
    ssmClient = boto3.client('ssm')
    try:
        response = ssmClient.get_parameter(
            Name=BITBUCKET_TOKEN_PARAMETER,
            WithDecryption=True
        )
        token = response['Parameter']['Value']
        return token
    except ClientError as e:
        print(e)
        raise e

## Function to initialize the getFolder method
def initialize(token, folderPath):
    s3Client = boto3.client('s3')
    newFolderPath = getFolder(token, folderPath, s3Client)
    processFolder(folderPath, newFolderPath, s3Client)

## Function to get all items from a specific Bitbucket URL
def getAllItems(url, headers):
    files = []
    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  
        data = response.json()
        files.extend(data.get('values', []))

        url = data.get('next', None)
    return files

## Function to process folderPath and packageName
def processFolder(folderPath, newFolderPath, s3Client):
    if folderPath.startswith('/'):
        folderPath = folderPath[1:]
    if newFolderPath.startswith(folderPath):
        remainingPath = newFolderPath[len(folderPath):]
        parts = remainingPath.split('/')
        packageName = parts[1]
        addFolderArchive(packageName, folderPath, s3Client)

## Function looping through all folders, creating local folders and files and uploading the package structure as a Zip File to S3
def getFolder(token, folderPath, s3Client):
    print(f"Checking Folder Path {folderPath}")
    baseUrl = f'https://api.bitbucket.org/2.0/repositories/{BITBUCKET_WORKSPACE_NAME}/{BITBUCKET_REPO_NAME}/src/{BITBUCKET_BRANCH_NAME}/{folderPath}'
    print(f"Base Url: {baseUrl}")
    headers = {'Authorization': f'Bearer {token}'}

    repoItems = getAllItems(baseUrl, headers)

    localFolderPath = os.path.join('/tmp', folderPath.lstrip('/'))
    os.makedirs(localFolderPath, exist_ok=True)
    print(f"Created local folder: {localFolderPath}")
    newFolderPath=""

    # Looping through all items in repoItems
    for item in repoItems:
        itemPath = item['path']
        itemType = item['type']
        
        # Check whether itemType is a directory
        if itemType == 'commit_directory':
            itemPath = itemPath.split('/')[-1]
            newFolderPath = os.path.join(folderPath, itemPath).lstrip('/')
            
            # Folder gets created locally
            localSubfolderPath = os.path.join('/tmp', newFolderPath)
            os.makedirs(localSubfolderPath, exist_ok=True)
            print(f"Found folder and created local subfolder: {localSubfolderPath}")

            # getFolder function gets called again with new folder path
            getFolder(token, newFolderPath, s3Client)

        # Check whether itemType is a file
        elif itemType == 'commit_file':
            print(f"Found file: {itemPath}")
            fullPath = item['path']
            pathParts = fullPath.split('/')
            fileName = pathParts[-1]

            # Get the file content from Bitbucket and upload it to S3
            url = f'https://api.bitbucket.org/2.0/repositories/{BITBUCKET_WORKSPACE_NAME}/{BITBUCKET_REPO_NAME}/src/{BITBUCKET_BRANCH_NAME}/{folderPath}/{fileName}'
            headers = {'Authorization': f'Bearer {token}'}
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                localFilePath = os.path.join(localFolderPath, fileName)
                with open(localFilePath, 'wb') as file:
                    file.write(response.content)
                print(f"Found file and created local file: {localFilePath}")
        else:
            print(f"Unknown item type: {itemType} for {itemPath}")
    return newFolderPath

## Function to create a Zip File out of the package and upload it to S3
def addFolderArchive(folderName, folderPath, s3Client):
    timeStamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    zipFileName = f'{folderName}_{timeStamp}.zip'

    fullFolderPath = f'/tmp/{folderPath}/{folderName}'
    tempZipFile = f'/tmp/{zipFileName}'

    # Zip File gets created and uploaded to S3
    shutil.make_archive(tempZipFile[:-4], 'zip', fullFolderPath)
    s3Client.upload_file(tempZipFile, BUCKET_NAME, zipFileName)

    # SSM Parameter gets set with package name
    ssm_client = boto3.client('ssm')
    ssm_client.put_parameter(
        Name=f'/org/layer/package/{folderPath}/{folderName}/zipArchive',
        Description=f'Archive name for {folderName} in s3 Bucket {BUCKET_NAME}',
        Value=zipFileName,
        Type='String',
        Overwrite=True
    )

    # Local files are removed
    if os.path.exists(tempZipFile):
        os.remove(tempZipFile)
    if os.path.exists(fullFolderPath):
        shutil.rmtree(fullFolderPath)
    print(f"Folder {folderName} archived as {zipFileName} and uploaded to S3")


