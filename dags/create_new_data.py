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
    dag_id='create_new_data',
    description='create_new_data',
    tags=['project', 'karmaflow'],
    schedule_interval=None,
    default_args={
        'owner': 'airflow',
        'start_date': days_ago(0, minute=1),
    },
    catchup = False
)

# definition of the function to execute
def create_new_data():
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
    task_id='create_new_data_task',
    python_callable=create_new_data,
    dag=my_dag
)
