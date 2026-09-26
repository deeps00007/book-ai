import sys, os, time, re
sys.path.insert(0, "backend")
os.environ["USE_SQLITE"] = "true"
import fitz

path = "12th class biology.pdf"
doc = fitz.open(path)

t0 = time.time()
texts = [doc[i].get_text() for i in range(doc.page_count)]
print(f"get_text only: {time.time()-t0:.1f}s")

t0 = time.time()
for i in range(doc.page_count):
    _ = doc[i].get_text("dict")
print(f"get_text('dict'): {time.time()-t0:.1f}s")

t0 = time.time()
def clean(t):
    t = t.replace("\ufffd", " ").replace("\u00a0", " ")
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()
for t in texts:
    clean(t)
print(f"clean_text: {time.time()-t0:.1f}s")
doc.close()
