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
YT = [{"channelUrl": "https://www.youtube.com/@shop_a", "numberOfSubscribers": 4210, "url": "https://www.youtube.com/watch?v=a", "title": "Room tour", "date": "2026-09-12T00:00:00.000Z", "viewCount": 3000, "likes": 80, "commentsCount": 4, "duration": "10:21"}]


class T(unittest.TestCase):
    def test_parse_accounts(self):
        self.assertEqual(collect.ig_user("https://www.instagram.com/shop_a/?hl=ja"), "shop_a")
        self.assertEqual(collect.ig_user("@shop_a"), "shop_a")
        self.assertIsNone(collect.ig_user("https://www.instagram.com/p/abc/"))
        self.assertEqual(collect.tt_user("https://www.tiktok.com/@shop_a?lang=ja"), "shop_a")
        self.assertEqual(collect.yt_url("@shop_a"), "https://www.youtube.com/@shop_a")
        self.assertEqual(collect.yt_url("https://www.youtube.com/@GMcorporationGIMMIC/featured"), "https://www.youtube.com/@gmcorporationgimmic")
        self.assertEqual(collect.yt_url("https://youtube.com/@kamakuraprote?si=abc"), "https://www.youtube.com/@kamakuraprote")

    def test_youtube_channels_are_not_mixed(self):
        """Two clients whose URLs both end in /featured must each get only their own channel."""
        yt = [{"channelUrl": "https://www.youtube.com/@aaa", "url": "https://www.youtube.com/shorts/1", "date": "2026-09-02T00:00:00Z", "viewCount": 10, "duration": "0:30"},
              {"channelUrl": "https://www.youtube.com/@bbb", "url": "https://www.youtube.com/shorts/2", "date": "2026-09-03T00:00:00Z", "viewCount": 20, "duration": "0:30"},
              {"channelUrl": "https://www.youtube.com/@bbb", "url": "https://www.youtube.com/shorts/3", "date": "2026-09-04T00:00:00Z", "viewCount": 30, "duration": "0:30"}]
        with mock.patch.object(collect, "run_actor", side_effect=lambda a, i, t: yt if a.startswith("streamers") else []):
            docs, _ = collect.collect([{"id": "a", "yt": "https://www.youtube.com/@aaa/featured"}, {"id": "b", "yt": "https://www.youtube.com/@bbb/shorts"},
                                       {"id": "c", "yt": "https://www.youtube.com/@ccc"}], "2026-09", "", log=lambda s: None)
        by = {d["docId"]: d["data"] for d in docs}
        self.assertEqual([v["url"] for v in by["a_2026-09"]["videos"]], ["https://www.youtube.com/shorts/1"])
        self.assertEqual(len(by["b_2026-09"]["videos"]), 2)
        self.assertEqual(by["c_2026-09"]["videos"], [])

    def test_collect(self):
        fx = {"apify~instagram-profile-scraper": IG, "apify~instagram-reel-scraper": [], "clockworks~tiktok-scraper": TT, "streamers~youtube-scraper": YT}
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
        self.assertEqual(d["videos"][2]["kind"], "long")

    def test_is_short(self):
        self.assertTrue(collect.is_short({"url": "https://www.youtube.com/shorts/abc"}))
        self.assertTrue(collect.is_short({"url": "https://www.youtube.com/watch?v=a", "duration": "0:58"}))
        self.assertFalse(collect.is_short({"url": "https://www.youtube.com/watch?v=a", "duration": "12:04"}))

    def test_reel_play_counts_win(self):
        reels = [{"ownerUsername": "shop_a", "type": "Video", "videoPlayCount": 20141, "videoViewCount": 12193, "likesCount": 130,
                  "commentsCount": 1, "timestamp": "2026-09-15T01:00:00.000Z", "url": "https://www.instagram.com/p/x/", "isPinned": False},
                 {"ownerUsername": "shop_a", "type": "Video", "videoPlayCount": 907427, "timestamp": "2025-02-19T01:00:00.000Z", "isPinned": True}]
        prof, vids = collect.norm_ig(IG, "shop_a", reels)
        self.assertEqual(prof["followers"], 1320)
        block, inm = collect.monthly(prof, vids, "2026-09")
        self.assertEqual(block["views"], 20141)
        self.assertEqual(block["posts"], 1)

    def test_collect_months_runs_actors_once(self):
        calls = []
        fx = {"apify~instagram-profile-scraper": IG, "apify~instagram-reel-scraper": [], "clockworks~tiktok-scraper": TT, "streamers~youtube-scraper": YT}
        def fake(a, i, t, **kw):
            calls.append(a)
            return fx[a]
        with mock.patch.object(collect, "run_actor", side_effect=fake):
            docs, errors = collect.collect_months([{"id": "c1", "ig": "@shop_a", "tt": "@shop_a", "yt": "@shop_a"}], ["2026-09", "2026-10"], "", log=lambda s: None)
        self.assertEqual(sorted(d["docId"] for d in docs), ["c1_2026-09", "c1_2026-10"])
        self.assertEqual(len(calls), 4)

    def test_failed_platform_is_reported(self):
        def boom(a, i, t):
            if a.startswith("apify~"):
                raise RuntimeError("blocked")
            return []
        with mock.patch.object(collect, "run_actor", side_effect=boom):
            docs, errors = collect.collect([{"id": "c1", "ig": "@shop_a"}], "2026-09", "tok", log=lambda s: None)
        self.assertEqual(docs, [])
        self.assertEqual(len(errors), 2)


if __name__ == "__main__":
    unittest.main()
