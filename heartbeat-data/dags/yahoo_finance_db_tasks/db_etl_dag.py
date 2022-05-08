import yfinance as yf
import psycopg2
import pandas as pd 
import json 
import time
import datetime
import os

from sqlalchemy import create_engine

# airflow dag package and operator 
from airflow import DAG
import datetime as dt
from airflow.operators.python_operator import PythonOperator

################## Connection schema ##################
conn = psycopg2.connect(
                        database="yahoo_finance",
                        user='erdmkbc',
                        password='admin',
                        host='localhost',
                        port= '5432'
                        )
cursor = conn.cursor()
#########################################################

################ data collection from ticker ############ 
def data_extract_from_ticker(*op_args):
    ticker = yf.Ticker('BTC-USD')
    ticker.history(period='1D').to_csv('/home/erdem/investing_dash/landing_file_static/BTC-USD.csv')

################## PostgreSQL Table Management ################### 
def create_table_postgres(*op_args):
    
    sql_create_table ='''CREATE TABLE IF NOT EXISTS btc_usd_data_scheduler(
                            Date INT,
                            Open FLOAT,
                            High FLOAT,
                            Low FLOAT,
                            Close FLOAT
                            )'''
    cursor.execute(sql_create_table)
##################################################################

################## PostgreSQL Flying tasks #######################
def transform_data(ti):
    
    # read from landing file
    df = pd.read_csv('/home/erdem/investing_dash/landing_file_static/BTC-USD.csv')

    # formatting 
    df['Date'] = df['Date'].astype('datetime64') 
    df['Volume'] = df['Volume'].astype('float64') 

    # drop the irrevelant columns 
    df.drop(['Volume', 'Dividends', 'Stock Splits'], axis=1, inplace = True)

    ti.xcom_push(key = 'formatted_processed_data', value = df.to_json())

################## Load to data to Postgres ######################
def load_data(ti):
    
    # create engine from flying tasks 
    engine = create_engine('postgresql+psycopg2://erdmkbc:admin@localhost:5432/yahoo_finance')
    data_json = ti.xcom_pull(key = 'formatted_processed_data', task_ids = ['transform_data'])

    #### Parsing json to dataframe

    # Dumped 
    data_json_dump = json.dumps(data_json)

    # to load 
        # returning a list
    json_object = json.loads(data_json_dump)
    
    # take first index 
    json_records = json_object[0]

    # parse to to dict 
    dict_parsed = json.loads(json_records)

    # the dict to dataframe 
    df_flying = pd.DataFrame.from_dict(dict_parsed)

    # load to postgres 
    df_flying.to_sql('btc_usd_data_scheduler', 
                    con=engine, 
                    if_exists='append',
                    index=False)

##################################################################

with DAG(
    dag_id = 'db_etl_dag',
    schedule_interval='@daily',
    start_date=dt.datetime(year = 2022, month=4, day=2),
    catchup=False

) as dag:

    collect_data_from_ticker_task = PythonOperator(task_id = 'extract_data_from_ticker',
                                                provide_context = True, 
                                                python_callable = data_extract_from_ticker, 
                                                dag = dag)
    
    connection_postgres_task = PythonOperator(task_id = 'connection_postgres',
                                                provide_context = True, 
                                                python_callable = create_table_postgres, 
                                                dag = dag)

    formatting_data_task = PythonOperator(task_id = 'transform_data',
                                                provide_context = True, 
                                                python_callable = transform_data, 
                                                dag = dag)
    
    load_data_task = PythonOperator(task_id = 'load_data',
                                    provide_context = True, 
                                    python_callable = load_data, 
                                    dag = dag)
                            
    
    collect_data_from_ticker_task >> connection_postgres_task >> formatting_data_task >> load_data_task

    
    