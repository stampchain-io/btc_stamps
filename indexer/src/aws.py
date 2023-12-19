import boto3
import config
from botocore.exceptions import NoCredentialsError
import logging
from tqdm import tqdm

import src.log as log

logger = logging.getLogger(__name__)
log.set_logger(logger)  # set root logger

''' this is intended for optional file upload to AWS S3 and Cloudfront CDN.'''


def get_s3_objects(db, bucket_name, s3_client):
    ''' this gets existing objects in S3 so we don't reupload existing files which can add to AWS costs'''
    cursor = db.cursor()
    cursor.execute("SELECT path_key, md5 FROM s3objects")
    results = cursor.fetchall() or []
    results = [{'key': row[0], 'md5': row[1]} for row in results]
    cursor.close()
    if results:
        logger.info(f"Found {len(results)} existing S3 objects")
    else:
        paginator = s3_client.get_paginator('list_objects_v2')
        logger.info(f"Fetching S3 objects from bucket: {bucket_name}/{config.AWS_S3_IMAGE_DIR}...")
        pages = list(paginator.paginate(Bucket=bucket_name, Prefix=config.AWS_S3_IMAGE_DIR))
        total_pages = len(pages)
        current_page = 0

        for current_page, page in enumerate(pages, start=1):
            if 'Contents' in page:
                for obj in tqdm(page['Contents'], desc=f'Fetching S3 objects (Page {current_page}/{total_pages})', unit=' object', bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}'):
                    s3_object = s3_client.head_object(Bucket=bucket_name, Key=obj['Key'])
                    results.append({'key': obj['Key'], 'md5': s3_object['ETag'].strip('"')})

    if results:
        logger.info(f"Found {len(results)} existing S3 objects")
        add_s3_objects_to_db(db, results)
    else:
        logger.info(f"No existing S3 objects found")

    return results


def update_dbobjects(db, filename, file_obj_md5):
    ''' this updates the s3objects db table with any new objects that have been uploaded to S3'''
    try:
        s3_file_path = f"{config.AWS_S3_IMAGE_DIR}{filename}"
        id = f"{s3_file_path}_{file_obj_md5}"

        cursor = db.cursor()
        
        # Check if the filename already exists in the table
        cursor.execute("SELECT id FROM s3objects WHERE path_key = %s", (s3_file_path,))
        existing_id = cursor.fetchone()
        
        if existing_id:
            # Delete the existing row
            cursor.execute("DELETE FROM s3objects WHERE id = %s", (existing_id[0],))
        
        # Insert the new object
        cursor.execute("INSERT IGNORE INTO s3objects (id, path_key, md5) VALUES (%s, %s, %s)", (id, s3_file_path, file_obj_md5))
        
        cursor.close()
    except Exception as e:
        logger.warning(f"ERROR: Unable to update the s3objects table. Error: {e}")


def add_s3_objects_to_db(db, s3_objects):
    ''' Add S3 objects to the s3objects table'''
    try:
        cursor = db.cursor()

        for s3_object in s3_objects:
            path_key = s3_object['key']
            md5 = s3_object['md5']
            id = path_key + md5

            query = "INSERT IGNORE INTO s3objects (id, path_key, md5) VALUES (%s, %s, %s)"
            values = (id, path_key, md5)
            cursor.execute(query, values)

        cursor.close()

        logger.info("S3 objects added to the database successfully")
    except Exception as e:
        logger.warning(f"ERROR: Unable to add S3 objects to the database. Error: {e}")


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
        logger.warning(f"failure uploading to aws {e}")


def check_existing_and_upload_to_s3(db, filename, mime_type, file_obj, file_obj_md5):
    s3_file_path = f"{config.AWS_S3_IMAGE_DIR}{filename}"
    if mime_type is None:
        mime_type = 'binary/octet-stream'

    existing_obj = next((obj for obj in config.S3_OBJECTS if obj['key'] == s3_file_path), None)
    if existing_obj:
        if existing_obj['md5'] == file_obj_md5:
            logger.debug(f"File {filename} with hash {file_obj_md5} already exists in S3. Skipping upload.")
        else:
            try:
                file_obj.seek(0)
                logger.debug(f"Uploading {filename} with changed hash {file_obj_md5} to S3...")
                upload_file_to_s3(file_obj, config.AWS_S3_BUCKETNAME, s3_file_path, config.AWS_S3_CLIENT, content_type=mime_type)
                update_dbobjects(db, filename, file_obj_md5)
                if config.AWS_CLOUDFRONT_DISTRIBUTION_ID:
                    logger.debug(f"Invalidating {filename} with changed hash {file_obj_md5} in Cloudfront...")
                    invalidate_s3_files(["/" + s3_file_path], config.AWS_CLOUDFRONT_DISTRIBUTION_ID)
            except Exception as e:
                logger.warning(f"ERROR: Unable to upload {filename} to S3. Error: {e}")
    else:
        try:
            file_obj.seek(0)
            logger.debug(f"Uploading new {filename} with hash {file_obj_md5} to S3...")
            upload_file_to_s3(file_obj, config.AWS_S3_BUCKETNAME, s3_file_path, config.AWS_S3_CLIENT, content_type=mime_type)
            # need to delete old object from s3objects table
            update_dbobjects(db, filename, file_obj_md5)
        except Exception as e:
            logger.warning(f"ERROR: Unable to upload {filename} to S3. Error: {e}")
