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

logger = logging.getLogger('airflow.task')

my_dag = DAG(
    dag_id='compare_data2threshold',
    description='compare_data2threshold',
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
        task_ids='compare_data2threshold_task', 
        dag_id='compare_data2threshold',
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

def send2bucket(task_instance):
    retrain = task_instance.xcom_pull(
        key='retrain',
        task_ids='compare_data2threshold_task', 
        dag_id='compare_data2threshold',
        include_prior_dates=True
    )
    print(f"retrain: {retrain}")
    logger.info('retrain value from task 4 : ' + str(retrain))
    if retrain : 
        logger.info('sent to bucket my-karma-bucket')


task2 = PythonOperator(
    task_id='compare_data2threshold_task',
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

task2 >> task3 >> task4