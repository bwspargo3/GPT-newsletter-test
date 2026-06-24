
from rapidfuzz import fuzz
def similar(a,b): return fuzz.ratio(a,b)>90
