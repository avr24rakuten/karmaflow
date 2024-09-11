from airflow import DAG
from airflow.utils.dates import days_ago
from airflow.operators.python import PythonOperator
from airflow.models import Variable
import numpy as np
import datetime
import requests
import json
import os
import pandas as pd
import random
import logging
import boto3
from botocore.exceptions import NoCredentialsError
from airflow.providers.amazon.aws.hooks.s3 import S3Hook

logger = logging.getLogger('airflow.task')

my_dag = DAG(
    dag_id='bucket_push_test',
    description='bucket_push_test',
    tags=['project', 'karmaflow'],
    schedule_interval=None,
    default_args={
        'owner': 'airflow',
        'start_date': days_ago(0, minute=1),
    },
    catchup = False
)

def pull2bucket(task_instance):
    s3 = boto3.client('s3')
    bucket_name = 'my-karma-bucket'
    s3_key = 'train_model_metadata.json'
    file_path = '/app/shared_volume/data/train_model_metadata.json'  # Chemin local du fichier
    try:
        # Upload du fichier
        s3.upload_file(file_path, bucket_name, s3_key)
        print(f"Fichier {file_path} uploadé avec succès dans {bucket_name}/{s3_key}")
    except FileNotFoundError:
        print(f"Le fichier {file_path} est introuvable.")
    except NoCredentialsError:
        print("Credentials AWS non disponibles.")
    except Exception as e:
        print(f"Une erreur s'est produite : {e}")
    logger.info('MAYDE MAYDE')

def upload_to_s3(**kwargs):
    s3_hook = S3Hook(aws_conn_id='aws_default')
    s3_hook.load_file(
        filename='/app/shared_volume/data/train_model_metadata.json',
        key='train_model_metadata.json',
        bucket_name='my-karma-bucket',
        replace=True
    )

task1 = PythonOperator(
    task_id='upload_to_s3',
    python_callable=upload_to_s3,
    dag=my_dag
)