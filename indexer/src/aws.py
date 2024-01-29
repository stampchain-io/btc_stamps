import boto3
import config
from botocore.exceptions import NoCredentialsError
import logging
from tqdm import tqdm

import src.log as log

logger = logging.getLogger(__name__)
log.set_logger(logger)  # set root logger

''' these functions are for optional file upload to AWS S3 and Cloudfront CDN file invalidation when there is an update.'''


def get_s3_objects(db, bucket_name, s3_client):
    """
    Retrieves existing file paths and md5 hashes in S3 to avoid reuploading existing files, which can add to AWS costs.

    Args:
        db (object): The database connection object.
        bucket_name (str): The name of the S3 bucket.
        s3_client (object): The S3 client object.

    Returns:
        list: A list of dictionaries containing the keys and MD5 hashes of the existing S3 objects.
    """

    logger.warning(f"Checking for existing S3 objects in database: {bucket_name}/{config.AWS_S3_IMAGE_DIR}...")
    cursor = db.cursor()
    cursor.execute("SELECT path_key, md5 FROM s3objects")
    results = cursor.fetchall() or []
    results = [{'key': row[0], 'md5': row[1]} for row in results]
    cursor.close()
    if results:
        logger.warning(f"Found {len(results)} existing S3 objects from database")
    else:
        paginator = s3_client.get_paginator('list_objects_v2')
        logger.warning(f"Fetching S3 objects from bucket: {bucket_name}/{config.AWS_S3_IMAGE_DIR}...")
        pages = list(paginator.paginate(Bucket=bucket_name, Prefix=config.AWS_S3_IMAGE_DIR))
        total_pages = len(pages)
        current_page = 0

        for current_page, page in enumerate(pages, start=1):
            if 'Contents' in page:
                for obj in tqdm(page['Contents'], desc=f'Fetching S3 objects (Page {current_page}/{total_pages})', unit=' object', bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}'):
                    s3_object = s3_client.head_object(Bucket=bucket_name, Key=obj['Key'])
                    results.append({'key': obj['Key'], 'md5': s3_object['ETag'].strip('"')})
        logger.warning(f"Found {len(results)} existing S3 objects")

        if results:
            add_s3_objects_to_db(db, results)
        else:
            logger.warning(f"No existing S3 objects found")

    return results


def update_s3_db_objects(db, filename, file_obj_md5):
    """
    This function updates the s3objects db table with any new objects that have been uploaded to S3.
    
    Parameters:
    - db: The database connection object.
    - filename: The name of the file that has been uploaded to S3.
    - file_obj_md5: The MD5 hash of the file object.
    """
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
    """
    Add S3 objects to the s3objects table

    Args:
        db (object): The database connection object
        s3_objects (list): List of S3 objects to be added to the database

    Returns:
        None

    Raises:
        Exception: If there is an error adding S3 objects to the database
    """
    try:
        cursor = db.cursor()

        query = "INSERT IGNORE INTO s3objects (id, path_key, md5) VALUES (%s, %s, %s)"
        values = [(s3_object['key'] + s3_object['md5'], s3_object['key'], s3_object['md5']) for s3_object in s3_objects]

        # Execute the multi-insert operation
        cursor.executemany(query, values)

        cursor.close()

        logger.info("S3 objects added to the database successfully")
    except Exception as e:
        logger.warning(f"ERROR: Unable to add S3 objects to the database. Error: {e}")


def invalidate_s3_files(file_paths, aws_cloudfront_distribution_id):
    """
    Invalidates the specified files in the AWS CloudFront distribution.

    Args:
        file_paths (list): A list of file paths to be invalidated.
        aws_cloudfront_distribution_id (str): The ID of the AWS CloudFront distribution.

    Returns:
        dict: The response from the create_invalidation API call.
    """
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
    """
    Uploads a file to Amazon S3.

    Args:
        file_obj_or_path (file-like object or str): The file-like object or path to the file to be uploaded.
        bucket_name (str): The name of the S3 bucket.
        s3_file_path (str): The desired path of the file in the S3 bucket.
        s3_client (boto3.client): The S3 client object used for uploading the file.
        content_type (str, optional): The content type of the file. Defaults to 'binary/octet-stream'.

    Raises:
        Exception: If there is a failure during the upload process.

    """
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
    """
    Checks if a file with the given filename and hash already exists in the S3 bucket.
    If the file exists and has the same MD5 hash as the provided file object, it skips the upload.
    If the file exists but has a different MD5 hash, it uploads the new file to S3, updates the S3 database objects,
    and invalidates the file in Cloudfront if a Cloudfront distribution ID is provided.
    If the file does not exist, it uploads the new file to S3 and updates the S3 database objects.

    Parameters:
    - db: The database object.
    - filename: The name of the file.
    - mime_type: The MIME type of the file.
    - file_obj: The file object to be uploaded.
    - file_obj_md5: The MD5 hash of the file object.

    Returns:
    None
    """
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
                update_s3_db_objects(db, filename, file_obj_md5)
                if config.AWS_CLOUDFRONT_DISTRIBUTION_ID:
                    logger.warning(f"Invalidating {filename} with changed hash {file_obj_md5} in Cloudfront...")
                    invalidate_s3_files(["/" + s3_file_path], config.AWS_CLOUDFRONT_DISTRIBUTION_ID)
            except Exception as e:
                logger.warning(f"ERROR: Unable to upload {filename} to S3. Error: {e}")
    else:
        try:
            file_obj.seek(0)
            logger.debug(f"Uploading new {filename} with hash {file_obj_md5} to S3...")
            upload_file_to_s3(file_obj, config.AWS_S3_BUCKETNAME, s3_file_path, config.AWS_S3_CLIENT, content_type=mime_type)
            # need to delete old object from s3objects table
            update_s3_db_objects(db, filename, file_obj_md5)
        except Exception as e:
            logger.warning(f"ERROR: Unable to upload {filename} to S3. Error: {e}")
