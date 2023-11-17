import boto3

''' this file is intended for optional file upload to AWS S3 - WIP - NOT IMPLEMENTED'''

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
