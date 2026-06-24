
import os,requests
URL='https://api.groq.com/openai/v1/chat/completions'
def chat(prompt):
    r=requests.post(URL,
        headers={'Authorization':f'Bearer {os.getenv("GROQ_API_KEY")}'},
        json={'model':'llama-3.3-70b-versatile',
              'messages':[{'role':'user','content':prompt}]},
        timeout=60)
    return r.json()
