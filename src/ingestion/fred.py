
import requests,os
def series(series_id):
    key=os.getenv('FRED_API_KEY')
    return requests.get(
      f'https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={key}&file_type=json'
    ).json()
