import logging
import hashlib
import io
import os
import index_core.log as log

from index_core.aws import (
    check_existing_and_upload_to_s3,
)

from config import (
    AWS_SECRET_ACCESS_KEY,
    AWS_ACCESS_KEY_ID,
    AWS_S3_IMAGE_DIR,
    AWS_S3_BUCKETNAME
)

logger = logging.getLogger(__name__)
log.set_logger(logger)  # set root logger


def get_fileobj_and_md5(decoded_base64):
    """
    Get the file object and MD5 hash of a decoded base64 string.

    Args:
        decoded_base64 (str): The decoded base64 string.

    Returns:
        tuple: A tuple containing the file object and the MD5 hash.

    Raises:
        Exception: If an error occurs during the process.
    """
    if decoded_base64 is None:
        logger.warning("decoded_base64 is None")
        return None, None
    try:
        file_obj = io.BytesIO(decoded_base64)
        file_obj.seek(0)
        file_obj_md5 = hashlib.md5(file_obj.read()).hexdigest()
        return file_obj, file_obj_md5
    except Exception as e:
        logger.error(f"Error: {e}")
        raise


def store_files(db, filename, decoded_base64, mime_type):
    """
    Store files in either AWS S3 or disk storage.

    Args:
        db (Database): The database object.
        filename (str): The name of the file.
        decoded_base64 (str): The decoded base64 file content.
        mime_type (str): The MIME type of the file.

    Returns:
        str: The MD5 hash of the stored file.
    """
    file_obj, file_obj_md5 = get_fileobj_and_md5(decoded_base64)
    if (AWS_SECRET_ACCESS_KEY and AWS_ACCESS_KEY_ID and AWS_S3_BUCKETNAME and AWS_S3_IMAGE_DIR):
        # FIXME: there may be cases where we want both aws and disk storage
        logger.info(f"uploading {filename} to aws")
        check_existing_and_upload_to_s3(
            db, filename, mime_type, file_obj, file_obj_md5
        )
    else:
        store_files_to_disk(filename, decoded_base64)
    return file_obj_md5, filename


def store_files_to_disk(filename, decoded_base64):
    """
    Stores the decoded base64 data to disk with the given filename.

    Args:
        filename (str): The name of the file to be stored.
        decoded_base64 (bytes): The decoded base64 data to be stored.

    Raises:
        Exception: If there is an error while storing the file.

    Returns:
        None
    """
    if decoded_base64 is None:
        logger.info("decoded_base64 is None")
        return
    if filename is None:
        logger.info("filename is None")
        return
    try:
        cwd = os.path.abspath(os.getcwd())
        base_directory = os.path.join(cwd, "files")
        os.makedirs(base_directory, mode=0o777, exist_ok=True)
        file_path = os.path.join(base_directory, filename)
        with open(file_path, "wb") as f:
            f.write(decoded_base64)
    except Exception as e:
        logger.error(f"Error: {e}")
        raise
