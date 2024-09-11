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
    dag_id='update_data_after_retrain',
    description='update_data_after_retrain',
    tags=['project', 'karmaflow'],
    schedule_interval='0 12 * * *',
    default_args={
        'owner': 'airflow',
        'start_date': days_ago(0, minute=1),
    },
    catchup = False
)

def update_data_after_retrain(task_instance):
    # check d'abord si entrainement en cours, train_finish = True
    # Récuperer les données du bucket TO DO
    s3_hook = S3Hook(aws_conn_id='aws_default')
    
    # Récupérer l'objet S3
    s3_object = s3_hook.get_key(
        key='train_model_metadata.json',  # Chemin du fichier dans le bucket S3
        bucket_name='my-karma-bucket'
    )

    # Vérifier si l'objet a été récupéré correctement
    if s3_object:
        # Télécharger le fichier dans un répertoire local
        s3_object.download_file('/app/shared_volume/data/train_model_metadata.json')
        print("Fichier téléchargé avec succès")
    else:
        print("Erreur : L'objet S3 n'a pas pu être récupéré")

    # load le json 'train_model_metadata.json'
    with open('/app/shared_volume/data/train_model_metadata.json', 'r') as jf:
        train_model_metadata_json = json.load(jf)
    train_finished = train_model_metadata_json[0]["train_finished"]
    logger.info("L'entrainenement est terminé : " + str(train_finished))
    new_model_keep = train_model_metadata_json[0]["new_model_keep"]
    logger.info("Garder le modèle réentrainé : " + str(new_model_keep))
    sent_to_retrain = train_model_metadata_json[0]["sent_to_retrain"]
    logger.info("Data deja intégré dans le modèle : " + str(sent_to_retrain))
    # TO DELETE :
    if train_finished and sent_to_retrain:
        #Push data from temp
        logger.info("now let push data from temp")
        
        data_new_folder = '/app/shared_volume/data/new/'
        X_new_file = data_new_folder + 'data_train_new.csv'
        df_new = pd.read_csv(X_new_file, index_col = 0)

        # Créer un DataFrame df_train_new vide
        df_train_new = pd.DataFrame(columns=df_new.columns)
        # Exporter le DataFrame avec uniquement les titres de colonnes en CSV
        df_train_new.to_csv(X_new_file, index=True)
        logger.info('repo new cleaned')

        if new_model_keep:
            data_temp_folder = '/app/shared_volume/data/temp/'
            X_train_file = data_temp_folder + 'X_train.csv'
            y_train_file = data_temp_folder + 'y_train.csv'
            df_X_train = pd.read_csv(X_train_file, index_col = 0)
            df_y_train = pd.read_csv(y_train_file, index_col = 0)

            data_train_folder = '/app/shared_volume/data/train/'
            df_X_train.to_csv(data_train_folder + 'X_train.csv', index=True)
            df_y_train.to_csv(data_train_folder + 'y_train.csv', index=True)

            logger.info('X_train, y_train are updated in train repo')
            #Now I push in bucket X_train, y_train : PAS A FAIRE NORMALEMENT

        for entry in train_model_metadata_json:
            entry['sent_to_retrain'] = False
        with open('/app/shared_volume/data/train_model_metadata.json', 'w') as file:
            json.dump(train_model_metadata_json, file, indent=4)
        #Now I push in bucket json : TO DO
        s3_hook.load_file(
            filename='/app/shared_volume/data/train_model_metadata.json',
            key='train_model_metadata.json',
            bucket_name='my-karma-bucket',
            replace=True
        )

task1 = PythonOperator(
    task_id='update_data_after_retrain',
    python_callable=update_data_after_retrain,
    dag=my_dag
)
