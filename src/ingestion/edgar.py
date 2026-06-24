
import requests
def company_submissions(cik):
    url=f'https://data.sec.gov/submissions/CIK{cik}.json'
    return requests.get(url,headers={'User-Agent':'LA Intelligence'}).json()
