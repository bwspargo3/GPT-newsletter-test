
import feedparser
def fetch(url):
    return feedparser.parse(url).entries
