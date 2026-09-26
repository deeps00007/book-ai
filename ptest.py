import sys, os, asyncio
sys.path.insert(0, "backend")
os.environ["USE_SQLITE"] = "true"

from app.services.upload_service import extract_pages, detect_chapters, chunk_pages

path = "12th class biology.pdf"
pages = extract_pages(path)
print(f"pages: {len(pages)}, total chars: {sum(len(p['text']) for p in pages)}")

chapters = detect_chapters(pages, path)
print(f"\nchapters detected: {len(chapters)}")
for ch in chapters[:20]:
    print(f"  page {ch['page_number']:3} | {ch['title'][:60]}")

chunks = chunk_pages(pages)
print(f"\nchunks: {len(chunks)}")
print("first chunk:", chunks[0]['page_start'], "-", chunks[0]['page_end'], "|", chunks[0]['text'][:100])
print("last chunk: ", chunks[-1]['page_start'], "-", chunks[-1]['page_end'], "|", chunks[-1]['text'][:100])
