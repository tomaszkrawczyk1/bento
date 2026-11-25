"""Forecast request validation shared by the gateway and Timestral worker."""
import pandas as pd
import numpy as np
from app import store

def prepare(spec,user):
 history=store.dataset(spec['dataset'],user)
 future=store.dataset(spec['future'],user) if spec.get('future') else None
 df=pd.read_parquet(history['path']);ff=pd.read_parquet(future['path']) if future else None
 targets=spec.get('targets',[]);past=(spec.get('past_covariates') or []);known=(spec.get('known_covariates') or [])
 if any(not isinstance(v,list) or any(not isinstance(c,str) for c in v) for v in (targets,past,known)):raise ValueError('targets and covariates must be lists of column names')
 cols=targets+past+known;timestamp=spec.get('timestamp');series=spec.get('series_id')
 horizon=int(spec.get('prediction_length',96))
 if not targets or len(set(cols))!=len(cols):raise ValueError('Provide target columns and distinct target/covariate column names')
 if not 1<=horizon<=1024:raise ValueError('prediction_length must be 1..1024')
 if not timestamp or timestamp in cols or (series and (series in cols or series==timestamp)):raise ValueError('Timestamp, series ID and numerical columns must be distinct')
 if not set(cols+[timestamp]+([series] if series else []))<=set(df.columns):raise ValueError('Missing history columns')
 if known and ff is None:raise ValueError('Known-future covariates require a future dataset')
 if ff is not None and not set(known+[timestamp]+([series] if series else []))<=set(ff.columns):raise ValueError('Missing future columns')
 df=df.copy();df[timestamp]=pd.to_datetime(df[timestamp],utc=True,errors='raise')
 if df[timestamp].isna().any() or (series and df[series].isna().any()):raise ValueError('Missing timestamp or series identifier')
 if ff is not None:
  ff=ff.copy();ff[timestamp]=pd.to_datetime(ff[timestamp],utc=True,errors='raise')
  if ff[timestamp].isna().any() or (series and ff[series].isna().any()):raise ValueError('Missing future timestamp/identifier')
 if any(not pd.api.types.is_numeric_dtype(df[c]) for c in cols):raise ValueError('Targets/covariates must be numeric; categorical covariates are not exposed by this API yet')
 if np.isinf(df[cols].to_numpy(dtype=float)).any():raise ValueError('Infinite history values')
 groups=list(df.groupby(series,sort=False)) if series else [('series_0',df)]
 prepared=[]
 for ident,part in groups:
  part=part.sort_values(timestamp)
  if part[timestamp].duplicated().any() or len(part)<32 or part[targets].count().min()<32:raise ValueError('Each series requires unique timestamps and at least 32 observed values per target')
  times=part[timestamp];delta=times.diff().dropna()
  frequency=pd.infer_freq(pd.DatetimeIndex(times))
  if frequency is None:
   if not (delta==delta.iloc[0]).all() or delta.iloc[0]<=pd.Timedelta(0):raise ValueError('This API requires a regular fixed or calendar frequency; resample irregular history explicitly')
   frequency=delta.iloc[0]
  expected=pd.date_range(times.iloc[-1],periods=horizon+1,freq=frequency)[1:]
  tail=None
  if ff is not None:
   tail=ff[ff[series]==ident] if series else ff
   tail=tail.sort_values(timestamp)
   if len(tail)!=horizon or not np.array_equal(tail[timestamp].to_numpy(),expected.to_numpy()):raise ValueError('Future rows must match the next horizon timestamps, exactly once per series')
   if known and (any(not pd.api.types.is_numeric_dtype(tail[c]) for c in known) or not np.isfinite(tail[known].to_numpy(dtype=float)).all()):raise ValueError('Known-future covariates must contain finite numeric values')
  # Only explicitly known covariates are selected from future; targets are never read.
  prepared.append((str(ident),part,tail,expected))
 if series and ff is not None and set(ff[series])!=set(df[series]):raise ValueError('History and future series must match')
 return history,future,prepared

def submit(spec,user):
 spec={**spec,'backend':'timestral','task':'forecast','operation':'forecast','workspace':user['workspace'],'time_limit':120,'prediction_length':int(spec.get('prediction_length',96)),'targets':spec.get('targets',[]),'past_covariates':(spec.get('past_covariates') or []),'known_covariates':(spec.get('known_covariates') or []),'use_cache':bool(spec.get('use_cache',False))}
 prepare(spec,user)
 return store.enqueue(spec,user)
