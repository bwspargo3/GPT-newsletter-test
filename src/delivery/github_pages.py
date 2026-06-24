
from pathlib import Path
def publish(html,path):
    p=Path('archive')/path
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(html,encoding='utf-8')
