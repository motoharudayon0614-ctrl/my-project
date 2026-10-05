"""Offline tests for collect.py: Apify calls are replaced with fixture items."""
import unittest
from unittest import mock

import collect

IG = [{"username": "shop_a", "followersCount": 1320, "latestPosts": [
    {"type": "Video", "videoPlayCount": 18000, "likesCount": 600, "commentsCount": 20, "timestamp": "2026-09-03T10:00:00.000Z", "url": "https://www.instagram.com/reel/x1/", "caption": "Before/After\nmore"},
    {"type": "Image", "likesCount": 90, "commentsCount": 1, "timestamp": "2026-09-05T10:00:00.000Z"},
    {"type": "Video", "videoViewCount": 900, "likesCount": 30, "commentsCount": 2, "timestamp": "2026-08-28T10:00:00.000Z"}]}]
TT = [{"authorMeta": {"name": "shop_a", "fans": 950}, "webVideoUrl": "https://www.tiktok.com/@shop_a/video/1", "createTimeISO": "2026-09-30T16:00:00.000Z",
       "playCount": 5000, "diggCount": 200, "commentCount": 5, "shareCount": 3, "collectCount": 9, "text": "tour"},
      {"authorMeta": {"name": "shop_a", "fans": 950}, "webVideoUrl": "https://www.tiktok.com/@shop_a/video/2", "createTimeISO": "2026-09-10T03:00:00.000Z",
       "playCount": 1000, "diggCount": 50, "commentCount": 1, "shareCount": 0, "collectCount": 1}]
YT = [{"numberOfSubscribers": 4210, "url": "https://www.youtube.com/watch?v=a", "title": "Room tour", "date": "2026-09-12T00:00:00.000Z", "viewCount": 3000, "likes": 80, "commentsCount": 4}]


class T(unittest.TestCase):
    def test_parse_accounts(self):
        self.assertEqual(collect.ig_user("https://www.instagram.com/shop_a/?hl=ja"), "shop_a")
        self.assertEqual(collect.ig_user("@shop_a"), "shop_a")
        self.assertIsNone(collect.ig_user("https://www.instagram.com/p/abc/"))
        self.assertEqual(collect.tt_user("https://www.tiktok.com/@shop_a?lang=ja"), "shop_a")
        self.assertEqual(collect.yt_url("@shop_a"), "https://www.youtube.com/@shop_a")

    def test_collect(self):
        fx = {"apify~instagram-profile-scraper": IG, "clockworks~tiktok-scraper": TT, "streamers~youtube-scraper": YT}
        with mock.patch.object(collect, "run_actor", side_effect=lambda a, i, t: fx[a]):
            docs, errors = collect.collect([{"id": "c1", "name": "A", "ig": "https://www.instagram.com/shop_a/",
                                             "tt": "https://www.tiktok.com/@shop_a", "yt": "https://www.youtube.com/@shop_a"},
                                            {"id": "c2", "name": "stopped", "ig": "@x", "active": False}], "2026-09", "tok", log=lambda s: None)
        self.assertEqual(errors, [])
        self.assertEqual(len(docs), 1)
        d = docs[0]["data"]
        self.assertEqual(docs[0]["docId"], "c1_2026-09")
        self.assertEqual(d["ig"], {"followers": 1320, "posts": 1, "views": 18000, "likes": 600, "comments": 20})
        # 2026-09-30T16:00Z is 10/1 in JST, so only one TikTok video falls in September
        self.assertEqual(d["tt"], {"followers": 950, "posts": 1, "views": 1000, "likes": 50, "comments": 1, "shares": 0, "saves": 1})
        self.assertEqual(d["yt"]["followers"], 4210)
        self.assertEqual(d["yt"]["posts"], 1)
        self.assertEqual(len(d["videos"]), 3)
        self.assertEqual(d["videos"][0]["title"], "Before/After")

    def test_failed_platform_is_reported(self):
        def boom(a, i, t):
            if a.startswith("apify~"):
                raise RuntimeError("blocked")
            return []
        with mock.patch.object(collect, "run_actor", side_effect=boom):
            docs, errors = collect.collect([{"id": "c1", "ig": "@shop_a"}], "2026-09", "tok", log=lambda s: None)
        self.assertEqual(docs, [])
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
