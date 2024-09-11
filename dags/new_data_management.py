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
    dag_id='new_data_management',
    description='new_data_management',
    tags=['project', 'karmaflow'],
    schedule_interval='0 0 * * *',
    default_args={
        'owner': 'airflow',
        'start_date': days_ago(0, minute=1),
    },
    catchup = False
)

# definition of the function to execute
def compare_data2threshold(task_instance):

    with open('/app/shared_volume/data/threshold.json', 'r') as jf:
        threshold_json = json.load(jf)
    unit_threshold = threshold_json[0]["unit_threshold"]
    global_threshold = threshold_json[0]["global_threshold"]

    logger.info('unit_threshold : ' + str(unit_threshold))
    logger.info('global_threshold : ' + str(global_threshold))

    with open('/app/shared_volume/data/code2type.json', 'r') as jf:
        code2type_json = json.load(jf)

    code2type = code2type_json[0]

    data_new_folder = '/app/shared_volume/data/new/'
    X_new_file = data_new_folder + 'data_train_new.csv'
    df_new = pd.read_csv(X_new_file, index_col = 0)
    prdtypecode_counts_new = df_new.groupby('prdtypecode').size().reset_index(name='counts')
    prdtypecode_counts_new['prdtypecode'] = prdtypecode_counts_new['prdtypecode'].astype(str)
    prdtypecode_counts_new['type'] = prdtypecode_counts_new['prdtypecode'].map(code2type)

    total_counts = prdtypecode_counts_new['counts'].sum()
    retrain = False

    logger.info('Total des counts : ' + str(total_counts))

    if total_counts > global_threshold:
        retrain = True
        logger.info('Le total ' + str(total_counts) + ' dépasse le seuil global ' + str(global_threshold))
    else:
        logger.info('Le total ' + str(total_counts) + ' ne dépasse pas le seuil global ' + str(global_threshold))

    prdtypecode_counts_new['above_unit_threshold'] = prdtypecode_counts_new['counts'] > unit_threshold
    if prdtypecode_counts_new['above_unit_threshold'].any():
        retrain = True
        logger.info('Au moins une ligne est au-dessus de unit_threshold')
    else:
        logger.info("Aucune ligne n'est au-dessus de unit_threshold")

    if retrain:
        logger.info('Nous devons reentrainer le model avec les nouvelles data')

    task_instance.xcom_push(
        key='retrain',
        value=retrain
    )

def create_newDataTrain_temp(task_instance):
    retrain = task_instance.xcom_pull(
        key='retrain',
        task_ids='compare_data2threshold', 
        dag_id='new_data_management',
        include_prior_dates=True
    )
    print(f"retrain: {retrain}")
    logger.info('retrain value from task 3 : ' + str(retrain))

    if retrain : 
        data_new_folder = '/app/shared_volume/data/new/'
        X_new_file = data_new_folder + 'data_train_new.csv'
        df_new = pd.read_csv(X_new_file, index_col = 0)
        df_X_train_new = df_new.drop(columns=['prdtypecode'])
        df_y_train_new = df_new[['prdtypecode']]

        data_train_folder = '/app/shared_volume/data/train/'
        X_train_file = data_train_folder + 'X_train.csv'
        y_train_file = data_train_folder + 'y_train.csv'
        df_X_train = pd.read_csv(X_train_file, index_col = 0)
        df_y_train = pd.read_csv(y_train_file, index_col = 0)

        df_X_train = pd.concat([df_X_train, df_X_train_new], ignore_index=True)
        df_y_train = pd.concat([df_y_train, df_y_train_new], ignore_index=True)

        data_temp_folder = '/app/shared_volume/data/temp/'
        df_X_train.to_csv(data_temp_folder + 'X_train.csv', index=True)
        df_y_train.to_csv(data_temp_folder + 'y_train.csv', index=True)
        logger.info('X_train, y_train ready to be sent and retrain model')


def send2bucket(task_instance, **kwargs):
    retrain = task_instance.xcom_pull(
        key='retrain',
        task_ids='compare_data2threshold', 
        dag_id='new_data_management',
        include_prior_dates=True
    )
    print(f"retrain: {retrain}")
    logger.info('retrain value from task 4 : ' + str(retrain))
    if retrain : 
        logger.info('sent to bucket my-karma-bucket')
        # envoyer from temp repo X_train, y_train, train_finish = False
        # et peut etre un new json to_train =True + mail
        with open('/app/shared_volume/data/train_model_metadata.json', 'r') as jf:
            train_model_metadata_json = json.load(jf)

        for entry in train_model_metadata_json:
            entry['train_finished'] = False
            entry['sent_to_retrain'] = True
        with open('/app/shared_volume/data/train_model_metadata.json', 'w') as file:
            json.dump(train_model_metadata_json, file, indent=4)
        #Now I push in bucket json : TO DO
        s3_hook = S3Hook(aws_conn_id='aws_default')
        s3_hook.load_file(
            filename='/app/shared_volume/data/train_model_metadata.json',
            key='train_model_metadata.json',
            bucket_name='my-karma-bucket',
            replace=True
        )
        s3_hook.load_file(
            filename='/app/shared_volume/data/temp/X_train.csv',
            key='csv/X_train.csv',
            bucket_name='my-karma-bucket',
            replace=True
        )
        s3_hook.load_file(
            filename='/app/shared_volume/data/temp/y_train.csv',
            key='csv/y_train.csv',
            bucket_name='my-karma-bucket',
            replace=True
        )


def pull_new_data(task_instance):
    # check d'abord si entrainement en cours, train_finish = True

    with open('/app/shared_volume/data/train_model_metadata.json', 'r') as jf:
        train_model_metadata_json = json.load(jf)
    train_finished = train_model_metadata_json[0]["train_finished"]
    logger.info("L'entrainenement est terminé : " + str(train_finished))
    new_model_keep = train_model_metadata_json[0]["new_model_keep"]
    logger.info("Garder le modèle réentrainé : " + str(new_model_keep))
    sent_to_retrain = train_model_metadata_json[0]["sent_to_retrain"]
    logger.info("Data deja intégré dans le modèle : " + str(sent_to_retrain))
    # TO DELETE :
    if train_finished:
        logger.info('Pull new data from bucket my-karma-bucket')

        stock_folder = '/app/shared_volume/data/temp/'
        new_folder = '/app/shared_volume/data/new/'
        stock_filename = 'data_stock.csv'
        new_filename = 'data_train_new.csv'

        sample_size = np.random.randint(50, 500)
        logger.info('sample_size : ' + str(sample_size))

        df_stock = pd.read_csv(os.path.join(stock_folder, stock_filename), index_col = 0)
        df_train_new = pd.read_csv(os.path.join(new_folder, new_filename), index_col = 0)

        sampled_df_stock = df_stock.sample(n=sample_size)

        df_train_new = pd.concat([df_train_new, sampled_df_stock], ignore_index=True)
        df_stock = df_stock.drop(sampled_df_stock.index)
        logger.info('df_train_new shape : ' + str(df_train_new.shape))
        logger.info('df_stock shape : ' + str(df_stock.shape))

        df_train_new.to_csv(os.path.join(new_folder, new_filename), index=True)
        df_stock.to_csv(os.path.join(stock_folder, stock_filename), index=True)

task1 = PythonOperator(
    task_id='pull_new_data',
    python_callable=pull_new_data,
    dag=my_dag
)

task2 = PythonOperator(
    task_id='compare_data2threshold',
    python_callable=compare_data2threshold,
    dag=my_dag
)

task3 = PythonOperator(
    task_id='create_newDataTrain_temp',
    python_callable=create_newDataTrain_temp,
    dag=my_dag
)

task4 = PythonOperator(
    task_id='send2bucket',
    python_callable=send2bucket,
    dag=my_dag
)

task1 >> task2 >> task3 >> task4