import httpx, asyncio, time, os

SUPABASE_URL = "https://ynltzrdihjycufniyvlk.supabase.co"
ANON = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlubHR6cmRpaGp5Y3Vmbml5dmxrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODYwMDQ5NjcsImV4cCI6MjEwMTU4MDk2N30.uTYgwfvdjLnA_Ed0JIW6YnGm8q4TcUJdpwaNNTefZe0"
BACKEND = "https://bookai-api-three.vercel.app/api/v1"

async def main():
    async with httpx.AsyncClient(timeout=600) as c:
        r = await c.post(f"{BACKEND}/auth/login", json={"email": "fix@test.com", "password": "test1234"})
        token = r.json()["access_token"]
        print("logged in")

        filepath = "12th class biology.pdf"
        filesize = os.path.getsize(filepath)
        chunk_size = 40 * 1024 * 1024  # 40MB
        total_chunks = (filesize + chunk_size - 1) // chunk_size
        print(f"File: {filesize/1024/1024:.1f}MB -> {total_chunks} chunks of ~40MB each")

        chunk_urls = []
        base = int(time.time())
        with open(filepath, "rb") as f:
            for i in range(total_chunks):
                data = f.read(chunk_size)
                name = f"chunks/{base}_part{i}.pdf"
                up = await c.post(
                    f"{SUPABASE_URL}/storage/v1/object/books/{name}",
                    content=data,
                    headers={"Authorization": f"Bearer {ANON}", "Content-Type": "application/pdf"},
                )
                if up.status_code not in (200,):
                    print(f"  chunk {i} FAILED: {up.status_code} {up.text[:100]}")
                    return
                url = f"{SUPABASE_URL}/storage/v1/object/public/books/{name}"
                chunk_urls.append(url)
                print(f"  chunk {i}/{total_chunks-1}: {len(data)/1024/1024:.1f}MB DONE")

        print(f"\nReassembling via backend...")
        r2 = await c.post(
            f"{BACKEND}/books/upload",
            json={
                "title": "12th Class Biology",
                "author": "NCERT",
                "storage_urls": chunk_urls,
                "file_size": filesize,
            },
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=600,
        )
        print(f"Result: {r2.status_code}")
        print(f"Body: {r2.text[:300]}")

asyncio.run(main())
