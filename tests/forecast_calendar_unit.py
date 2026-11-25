"""Calendar frequency preserves real month/quarter boundaries; irregular data fails."""
import os,tempfile,unittest
import pandas as pd
sandbox=tempfile.TemporaryDirectory(prefix='calendar-tests-',dir='data');os.environ['BENTO_DATA']=sandbox.name
from app import store,forecast
store.init();USER={'id':'u','workspace':'calendar'}
class CalendarTests(unittest.TestCase):
 def prepare(self,freq):
  times=pd.date_range('2000-01-01',periods=48,freq=freq);df=pd.DataFrame({'date':times,'value':range(48)})
  data=store.save_dataset(df,USER)
  return times,forecast.prepare({'dataset':data['dataset_id'],'timestamp':'date','targets':['value'],'prediction_length':12},USER)[2][0][3]
 def test_hourly_daily_monthly_quarterly(self):
  for freq in ['h','D','MS','ME','QS','YS']:
   times,expected=self.prepare(freq);want=pd.date_range(times[-1],periods=13,freq=freq)[1:]
   self.assertEqual(list(expected),list(want.tz_localize('UTC')))
 def test_gap_rejected(self):
  times=pd.date_range('2000-01-01',periods=50,freq='D').delete(22)
  data=store.save_dataset(pd.DataFrame({'date':times,'value':range(49)}),USER)
  with self.assertRaisesRegex(ValueError,'resample'):forecast.prepare({'dataset':data['dataset_id'],'timestamp':'date','targets':['value']},USER)
if __name__=='__main__':
 try:unittest.main(verbosity=2)
 finally:sandbox.cleanup()
