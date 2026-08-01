import unittest
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "reply_pagination",
    Path(__file__).parent / "modules" / "posting" / "reply_pagination.py",
)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
fetch_changed_thread_posts = _MODULE.fetch_changed_thread_posts


class FakeClient:
    def __init__(self, total_posts):
        self.posts = [
            {"pid": str(1000 + i), "uid": "2", "dateline": i, "message": "reply"}
            for i in range(total_posts)
        ]
        self.pages = []

    async def read(self, request):
        spec = request["posts"]
        page = spec["_page"]
        perpage = spec["_perpage"]
        self.pages.append(page)
        start = (page - 1) * perpage
        return {"posts": self.posts[start:start + perpage]}


class ReplyPaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_verified_reply_count_for_final_pages(self):
        client = FakeClient(75)
        posts, replies = await fetch_changed_thread_posts(client, "123", 74)
        self.assertEqual(replies, 74)
        self.assertEqual(len(posts), 45)
        self.assertEqual(client.pages, [2, 3])

    async def test_finds_final_page_when_count_is_missing(self):
        client = FakeClient(75)
        posts, replies = await fetch_changed_thread_posts(client, "123", None)
        self.assertEqual(replies, 74)
        self.assertEqual(len({row["pid"] for row in posts}), 45)
        self.assertIn(3, client.pages)
        self.assertIn(4, client.pages)

    async def test_single_page_thread(self):
        client = FakeClient(8)
        posts, replies = await fetch_changed_thread_posts(client, "123", None)
        self.assertEqual(replies, 7)
        self.assertEqual(len(posts), 8)
        self.assertEqual(client.pages, [1])


if __name__ == "__main__":
    unittest.main()
