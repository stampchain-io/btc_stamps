import boto3
import config
from botocore.exceptions import NoCredentialsError
import logging
from tqdm import tqdm

import src.log as log

logger = logging.getLogger(__name__)
log.set_logger(logger)  # set root logger

''' this file is intended for optional file upload to AWS S3 - WIP - NOT IMPLEMENTED'''


def get_s3_objects(bucket_name, s3_client):
    ''' this gets existing objects in S3 so we don't reupload existing files'''
    result = []
    paginator = s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket_name, Prefix=config.AWS_S3_IMAGE_DIR)
    logger.info(f"Fetching S3 objects from bucket: {bucket_name}/{config.AWS_S3_IMAGE_DIR}...")
    total_pages = len(list(pages))
    print(f"Total number of pages expected: {total_pages}")

    for page in pages:
        if 'Contents' in page:
            for obj in tqdm(page['Contents'], desc='Fetching S3 objects', unit=' object'):
                s3_object = s3_client.head_object(Bucket=bucket_name, Key=obj['Key'])
                result.append({'key': obj['Key'], 'md5': s3_object['ETag'].strip('"')})

    return result


def invalidate_s3_files(file_paths, aws_cloudfront_distribution_id):
    client = boto3.client('cloudfront')
    response = client.create_invalidation(
        DistributionId=aws_cloudfront_distribution_id,
        InvalidationBatch={
            'Paths': {
                'Quantity': len(file_paths),
                'Items': file_paths
            },
            'CallerReference': str(hash(tuple(file_paths)))
        }
    )
    return response


def upload_file_to_s3(file_obj_or_path, bucket_name, s3_file_path, s3_client, content_type='binary/octet-stream'):
    try:
        extra_args = {'ContentType': content_type}
        if hasattr(file_obj_or_path, 'read'):
            file_obj_or_path.seek(0)
            s3_client.upload_fileobj(file_obj_or_path, bucket_name, s3_file_path, ExtraArgs=extra_args)
        else:
            s3_client.upload_file(file_obj_or_path, bucket_name, s3_file_path, ExtraArgs=extra_args)
    except Exception as e:
        print(f"failure uploading to aws {e}")


def check_existing_and_upload_to_s3(filename, mime_type, file_obj, file_obj_md5):
    s3_file_path = f"{config.AWS_S3_IMAGE_DIR}{filename}"
    if mime_type is None:
        mime_type = 'binary/octet-stream'

    try:
        if s3_file_path not in [obj['key'] for obj in config.S3_OBJECTS] or any(obj['key'] == s3_file_path and obj['md5'] != file_obj_md5 for obj in config.S3_OBJECTS):
            try:
                file_obj.seek(0)
                upload_file_to_s3(file_obj, config.AWS_S3_BUCKETNAME, s3_file_path, config.AWS_S3_CLIENT, content_type=mime_type)
            except Exception as e:
                logger.warning(f"ERROR: Unable to upload", filename, "to S3. Error:", e)
        elif s3_file_path in [obj['key'] for obj in config.S3_OBJECTS]:
            try:
                invalidate_s3_files(["/" + s3_file_path], config.AWS_CLOUDFRONT_DISTRIBUTION_ID)
            except Exception as e:
                logger.warning(f"ERROR: Unable to invalidate S3 file. Error:", e)
    except NoCredentialsError as e:
        logger.warning(f"ERROR: Unable to upload", filename, "to S3. Error:", e)
