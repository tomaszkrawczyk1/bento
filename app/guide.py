"""Server-side playbook for MCP clients: short user prompts work because workflow, defaults and reporting live here."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import httpx,pandas as pd
from app.store import save_dataset

INSTRUCTIONS="""Bento Tabular GPU: TabICLv2 / Mitra (klasyfikacja, regresja) i Timestral-209M (prognozy szeregów czasowych) na serwerze GPU.
Użytkownik zwykle pisze krótko ("weź dataset cen domów i zrób regresję", "jaka będzie jutro pogoda w Katowicach"). Resztę robisz sam, do końca, bez pytań o zgodę i bez proszenia o pliki. Nigdy nie kończ na samym planie.

DANE
- Brak podanego zbioru: wywołaj dataset_catalog(topic) (np. "ceny domów", "wino", "pasażerowie"), wybierz najlepszy wpis i zaimportuj go dataset_from_url z podanymi w katalogu options.
- Użytkownik podał URL / Kaggle / link: dataset_from_url (serwer sam pobiera). Rekordów nie wklejaj do czatu ani argumentów narzędzi. Potem describe_dataset i sam wybierz target i cechy.
- Cechy: wszystkie poza targetem, identyfikatorami, nazwami i kolumnami wyciekającymi (np. wartość znana dopiero po zdarzeniu). Wyjątki krótko uzasadnij.

KLASYFIKACJA / REGRESJA
- evaluate(train=dataset_id, target, task='classification'|'regression', backend='tabicl', test_size=0.2, seed=42), jeden raz. Potem get_job (nie częściej niż co 3 s) aż succeeded i get_result.
- Nigdy nie trenuj zamiennika lokalnie (sklearn itp.) i nie zmyślaj metryk ani predykcji. Mitra tylko na wyraźną prośbę.
- Raport: dataset_id, job_id, rows train/test, liczba i lista cech, metryki (regresja: R², RMSE, MAE; klasyfikacja: accuracy, F1), czasy z API (duration_seconds). Zaznacz, że to mała receptura demo, nie benchmark.

SZEREGI CZASOWE
- forecast(dataset, targets, timestamp, prediction_length). Wymaga regularnego kroku (stałego lub kalendarzowego), min. 32 obserwacje. Przy lukach dat nie uzupełniaj wymyślonych pomiarów: opisz problem i zaimportuj ciągły fragment (options csv_skiprows/row_limit).
- Pogoda: wywołaj weather_history(city) – zwraca dataset_id świeżych danych godzinowych, datę ostatniego pomiaru i gotowe forecast_args na jutro. Timestral to ekstrapolacja szeregu, a nie model atmosfery: napisz to wprost. Jeśli masz dostęp do sieci, porównaj z publiczną prognozą (np. Interia, IMGW) i podaj różnicę.
- Raport: dataset_id, job_id, wiersze wejściowe, serie, targety, horyzont, czasy z API; mediana i kwantyle z get_result (get_result zwraca max 20 wierszy, pełne wyniki są pod csv_download_url).

WYNIK
- Na końcu zawsze zrób czytelny wykres (artifact HTML/SVG) z faktycznych liczb z MCP (metryki lub prognoza z przedziałem niepewności) i 2–3 zdania interpretacji po polsku. Nie wymyślaj punktów, których narzędzia nie zwróciły.
"""

CATALOG=[
 {'id':'california_housing','topics':'ceny domów mieszkania nieruchomości housing house prices kalifornia','url':'https://raw.githubusercontent.com/ageron/handson-ml2/master/datasets/housing/housing.csv','task':'regression','target':'median_house_value','note':'20640 wierszy, ocean_proximity kategoryczna, total_bedrooms ma braki'},
 {'id':'boston_housing','topics':'ceny domów housing boston nieruchomości house prices','url':'https://raw.githubusercontent.com/selva86/datasets/master/BostonHousing.csv','task':'regression','target':'medv','note':'506 wierszy, mały i szybki'},
 {'id':'diamonds','topics':'diamenty ceny diamonds price','url':'https://raw.githubusercontent.com/mwaskom/seaborn-data/master/diamonds.csv','task':'regression','target':'price','note':'53940 wierszy'},
 {'id':'mpg','topics':'samochody auta spalanie mpg cars','url':'https://raw.githubusercontent.com/mwaskom/seaborn-data/master/mpg.csv','task':'regression','target':'mpg','features':'cylinders,displacement,horsepower,weight,acceleration,model_year,origin','note':'pomiń kolumnę name'},
 {'id':'insurance','topics':'ubezpieczenia koszty medyczne insurance charges','url':'https://raw.githubusercontent.com/stedy/Machine-Learning-with-R-datasets/master/insurance.csv','task':'regression','target':'charges'},
 {'id':'tips','topics':'napiwki rachunek restauracja tips','url':'https://raw.githubusercontent.com/mwaskom/seaborn-data/master/tips.csv','task':'regression','target':'total_bill','features':'sex,smoker,day,time,size','note':'pomiń tip (wyciek)'},
 {'id':'wine_red','topics':'wino jakość wine quality','url':'https://archive.ics.uci.edu/ml/machine-learning-databases/wine-quality/winequality-red.csv','task':'regression','target':'quality','options':{'delimiter':';'},'note':'11 cech fizykochemicznych'},
 {'id':'iris','topics':'kwiaty irysy iris gatunek klasyfikacja','url':'https://raw.githubusercontent.com/mwaskom/seaborn-data/master/iris.csv','task':'classification','target':'species'},
 {'id':'titanic','topics':'titanic przeżycie pasażerowie klasyfikacja survival','url':'https://raw.githubusercontent.com/mwaskom/seaborn-data/master/titanic.csv','task':'classification','target':'survived','note':'pomiń alive i alone (duplikaty/wyciek)'},
 {'id':'penguins','topics':'pingwiny penguins gatunek klasyfikacja','url':'https://raw.githubusercontent.com/mwaskom/seaborn-data/master/penguins.csv','task':'classification','target':'species'},
 {'id':'airline_passengers','topics':'pasażerowie linie lotnicze airline passengers sezonowość szereg czasowy','url':'https://raw.githubusercontent.com/jbrownlee/Datasets/master/airline-passengers.csv','task':'forecast','targets':['Passengers'],'timestamp':'Month','note':'miesięczne 1949-1960, 144 punkty'},
 {'id':'melbourne_temperatures','topics':'temperatura melbourne dzienna szereg czasowy temperatures','url':'https://raw.githubusercontent.com/jbrownlee/Datasets/master/daily-min-temperatures.csv','task':'forecast','targets':['Temp'],'timestamp':'Date','note':'brakuje 29 lutego → dla forecast użyj ciągłego fragmentu (np. rok 1990)'},
]

def dataset_catalog(topic=''):
 words=[w for w in topic.lower().replace(',',' ').split() if len(w)>2]
 def score(e):return sum(w in (e['topics']+' '+e['id']).lower() or any(w[:5]==t[:5] for t in e['topics'].split()) for w in words)
 hits=sorted(CATALOG,key=score,reverse=True)
 if words and score(hits[0])==0:hits=CATALOG
 return {'usage':'Import best match with dataset_from_url(url, options), then describe_dataset and evaluate/forecast. For other topics use any public URL or Kaggle link.','datasets':hits[:5] if words else CATALOG}

def weather_history(city,days=45,user=None):
 with httpx.Client(timeout=30) as c:
  g=c.get('https://geocoding-api.open-meteo.com/v1/search',params={'name':city,'count':1,'language':'pl'}).json().get('results')
  if not g:raise ValueError('City not found: '+city)
  g=g[0];days=max(14,min(int(days),365));now=datetime.now(timezone.utc)
  r=c.get('https://archive-api.open-meteo.com/v1/archive',params={'latitude':g['latitude'],'longitude':g['longitude'],'start_date':(now-timedelta(days=days)).date().isoformat(),'end_date':now.date().isoformat(),'hourly':'temperature_2m','timezone':'UTC'});r.raise_for_status()
 h=r.json()['hourly'];df=pd.DataFrame({'time':pd.to_datetime(h['time']),'temperature_2m':h['temperature_2m']}).dropna()
 df=df[df['time']<=pd.Timestamp(now.replace(tzinfo=None,minute=0,second=0,microsecond=0))].reset_index(drop=True)  # archive can already hold model values for later hours today; never use the future
 last=df['time'].iloc[-1].to_pydatetime().replace(tzinfo=timezone.utc)
 tz=ZoneInfo(g.get('timezone','UTC'));tomorrow=(now.astimezone(tz)+timedelta(days=1)).date()
 start=datetime(tomorrow.year,tomorrow.month,tomorrow.day,tzinfo=tz).astimezone(timezone.utc);end=start+timedelta(hours=23)
 first_step=int((start-last).total_seconds()//3600);steps=int((end-last).total_seconds()//3600)
 if steps<1:raise ValueError('Archive already covers tomorrow; unexpected')
 meta=save_dataset(df,user,'weather-'+g['name'],{'source':'open-meteo archive','city':g['name'],'country':g.get('country'),'lat':g['latitude'],'lon':g['longitude']})
 return {'dataset_id':meta['dataset_id'],'city':g['name'],'country':g.get('country'),'latitude':g['latitude'],'longitude':g['longitude'],'source':'Open-Meteo archive API (ERA5 reanalysis), hourly temperature_2m, times in UTC','rows':len(df),'first_timestamp_utc':df['time'].iloc[0].isoformat(),'last_timestamp_utc':last.isoformat(),'local_timezone':g.get('timezone'),'tomorrow_local_date':tomorrow.isoformat(),
  'forecast_args':{'dataset':meta['dataset_id'],'targets':['temperature_2m'],'timestamp':'time','prediction_length':steps},
  'tomorrow_in_result':f'forecast steps {max(first_step,1)} to {steps} (1-based) are the 24 hours of {tomorrow} local time; earlier steps are the gap after the last measurement','note':'Timestral extrapolates the series; it is not a numerical weather model.'}
