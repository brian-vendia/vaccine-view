import os
import tempfile
import urllib3

from aws_lambda_powertools import Logger
from aws_lambda_powertools import Tracer
import boto3
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

urllib3.disable_warnings()

# Vendia Share node data
share_node_url = os.getenv('SHARE_NODE_URL')
share_node_api_key = os.getenv('SHARE_NODE_API_KEY')
aws_region = os.getenv('AWS_REGION')

s3_resource = boto3.resource('s3', region_name=aws_region)

logger = Logger()
tracer = Tracer()

transport=RequestsHTTPTransport(
    url=share_node_url,
    use_json=True,
    headers={
        "Content-type": "application/json",
        "x-api-key": share_node_api_key
    },
    verify=False,
    retries=3,
)

gql_client = Client(
    transport=transport,
    fetch_schema_from_transport=True,
)


@tracer.capture_method
def get_s3_object(bucket, key_name, local_file):
    """Download a S3 object to a local file in the execution environment

    Parameters
    ----------
    bucket: string, required
        S3 bucket that holds the image
    
    key_name: string, required
    
    Returns
    -------
    result: Boolean; True if download successful, False if not 
    """
    tracer.put_metadata('object', f's3://{bucket}/{key_name}')

    try:
        tracer.put_annotation('OBJECT_DOWNLOAD', 'SUCCESS')
        log.info
    except Exception as e:
        tracer.put_annotation('OBJECT_DOWNLOAD', 'FAILURE')
        result = f'Error: {str(e)}'

    return(result)

@tracer.capture_method
def write_vaccine_card_to_share(source_bucket, key_name, source_region, destination_key):
    """Write data to Vendia Share GraphQL Endpoint

    Parameters
    ----------
    source_bucket: string, required
        Source bucket of Vendia Share blob data
    
    key_name: string, required
        Key of blob data to be uploaded to Vendia Share
    
    Returns
    -------
    boolean (True if successful, False if not successful)
    """
    tracer.put_metadata('object', f's3://{source_bucket}/{key_name}')

    params = {
        "sourceBucket": source_bucket,
        "sourceKey": key_name,
        "sourceRegion": source_region,
        "destinationKey": destination_key
    }

    try:
        add_file_mutation = gql(
            """
            mutation writeAttachment(
                $sourceBucket: String!,
                $sourceKey: String!,
                $sourceRegion: String!,
                $destinationKey: String!
            ) {
                add_File_async(
                    input: {
                        SourceBucket: $sourceBucket,
                        SourceKey: $sourceKey,
                        SourceRegion: $sourceRegion,
                        DestinationKey: $destinationKey
                    }
                ) {
                        error
                        result {
                            id
                            node_owner
                            submission_time
                            tx_id
                        }
                    }
                }
            """
        )

        result = gql_client.execute(
            add_file_mutation,
            variable_values=params
        )

        logger.info(f'Query result: {result}')
        tracer.put_annotation('STORE_VACCINE_CARD_IN_SHARE', 'SUCCESS')
        return(True)
    except Exception as e:
        logger.error(str(e))
        tracer.put_annotation('STORE_VACCINE_CARD_IN_SHARE', 'FAILURE')
        return(False)

    


@tracer.capture_method
@logger.inject_lambda_context
def handler(event, context):
    """Sample pure Lambda function

    Parameters
    ----------
    event: dict, required
        S3 Put Event Format

        Event doc: https://docs.aws.amazon.com/lambda/latest/dg/with-s3.html

    context: object, required
        Lambda Context runtime methods and attributes

        Context doc: https://docs.aws.amazon.com/lambda/latest/dg/python-context-object.html

    Returns
    -------
    aggregate_results: dict (Results of Vendia Share file upload operation indexed by key_name)
    """

    aggregate_results = {}

    for record in event['Records']:
        tmpdir = tempfile.mkdtemp()

        try:
            bucket_name = record['s3']['bucket']['name']
            key_name = record['s3']['object']['key']
            source_region = record['awsRegion']
        except Exception as e:
            logger.error(str(e))
            raise Exception(str(e))
            
        try:
            local_file = os.path.join(
                            tmpdir, 
                            key_name.split('/')[-1]
                        )
        except Exception as e:
            logger.error(f'Could not define local_file: {str(e)}')
            raise Exception(f'Could not define local_file: {str(e)}')
        
        # Get object from S3
        download_status = get_s3_object(
                                bucket_name,
                                key_name,
                                local_file
                            )
        
        if download_status:
            success_message = f'Successful download of s3://{bucket_name}/{key_name} '
            success_message += f'to {local_file} '
            success_message += f'for processing'
            logger.info(success_message)
        else:
            logger.error(f'Download failure to {local_file}: {download_status}')
            raise Exception(f'Download failure to {local_file}: {download_status}')

        # Try to write to Vendia Share file storage
        blob_result = write_vaccine_card_to_share(bucket_name, key_name, source_region, key_name)
        if blob_result:
            logger.info(f'Successful upload of image {key_name} to Vendia Share blob storage')
        else:
            logger.error(f'Could not write image {key_name} to Vendia Share blob storage')
        
        aggregate_results[key_name] = blob_result

    return(aggregate_results)

