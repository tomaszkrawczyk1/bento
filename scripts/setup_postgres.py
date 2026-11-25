"""Initialize the local synthetic-data demo and a restricted SQL reader."""
import json,secrets,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
env=root/'.env'
if not env.exists():
 env.write_text('DEMO_POSTGRES_PASSWORD='+secrets.token_urlsafe(24)+'\nDEMO_READ_PASSWORD='+secrets.token_urlsafe(24)+'\n');env.chmod(0o600)
settings=dict(line.split('=',1) for line in env.read_text().splitlines() if '=' in line)
reader=settings['DEMO_READ_PASSWORD']
if 'DEMO_POSTGRES_DSN' not in settings:
 with env.open('a') as f:f.write('DEMO_POSTGRES_DSN=postgresql://bento_reader:'+reader+'@postgres:5432/bento_demo\n')
# The administrator credential stays in the container environment, outside source control.
subprocess.run(['docker','compose','--env-file',str(env),'-f',str(root/'demo/compose.postgres.yaml'),'up','-d'],check=True)
import time
for _ in range(60):
 if subprocess.run(['docker','exec','bento-postgres-1','pg_isready','-U','bento_admin','-d','bento_demo'],stdout=subprocess.DEVNULL).returncode==0:break
 time.sleep(1)
def sql(text):
 subprocess.run(['docker','exec','-i','bento-postgres-1','psql','-v','ON_ERROR_STOP=1','-U','bento_admin','-d','bento_demo'],input=text,text=True,check=True,stdout=subprocess.DEVNULL)
sql(f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='bento_reader') THEN CREATE ROLE bento_reader LOGIN PASSWORD '{reader}'; END IF; END $$; ALTER ROLE bento_reader SET default_transaction_read_only=on; REVOKE CREATE ON SCHEMA public FROM PUBLIC;")
import pandas as pd
for task in ('classification','regression'):
 df=pd.read_csv(root/'demo'/f'{task}-train.csv');table=task+'_data'
 columns=','.join('"'+c.replace('"','""')+'" DOUBLE PRECISION' for c in df.columns)
 sql(f'CREATE TABLE IF NOT EXISTS {table} ({columns});TRUNCATE {table};')
 csv=df.to_csv(index=False,header=False)
 subprocess.run(['docker','exec','-i','bento-postgres-1','psql','-v','ON_ERROR_STOP=1','-U','bento_admin','-d','bento_demo','-c',f'COPY {table} FROM STDIN WITH CSV'],input=csv,text=True,check=True,stdout=subprocess.DEVNULL)
sql('GRANT CONNECT ON DATABASE bento_demo TO bento_reader;GRANT USAGE ON SCHEMA public TO bento_reader;GRANT SELECT ON classification_data,regression_data TO bento_reader;')
print('PostgreSQL demo ready: bento_reader has SELECT only on the two demo tables')
