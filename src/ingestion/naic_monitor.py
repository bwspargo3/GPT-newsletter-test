
import hashlib,requests
def page_hash(url):
    return hashlib.sha256(requests.get(url,timeout=30).text.encode()).hexdigest()
