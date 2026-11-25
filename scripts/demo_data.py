import json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sklearn.datasets import load_breast_cancer,load_diabetes
from sklearn.model_selection import train_test_split
from app.store import ROOT
out=Path(__file__).resolve().parents[1]/'demo';out.mkdir(exist_ok=True)
con=sqlite3.connect(ROOT/'demo.sqlite')
for name,loader in [('classification',load_breast_cancer),('regression',load_diabetes)]:
 d=loader(as_frame=True);df=d.frame.rename(columns={'target':'target'})
 train,test=train_test_split(df,test_size=.2,random_state=42,stratify=df.target if name=='classification' else None)
 train.to_csv(out/(name+'-train.csv'),index=False)
 test.drop(columns='target').to_csv(out/(name+'-test.csv'),index=False)
 df.to_sql(name+'_data',con,index=False,if_exists='replace')
con.close();print('Generated demo CSVs and read-only source database')
