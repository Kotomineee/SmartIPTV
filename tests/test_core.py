import os
from pathlib import Path
import tempfile
import unittest

from smartiptv.client import Credentials, ProviderError, XtreamClient
from smartiptv.models import Content, content_from_api, episodes_from_api
from smartiptv.storage import Library, SessionStore
from smartiptv.validation import server_error
from tests.provider import Provider


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = Provider().start()

    @classmethod
    def tearDownClass(cls):
        cls.provider.close()

    def client(self, username="demo", password="demopass"):
        return XtreamClient(Credentials(self.provider.url, username, password))

    def test_valid_login(self):
        self.assertEqual(self.client().authenticate()["status"], "Active")

    def test_rejected_login_does_not_echo_credentials(self):
        with self.assertRaises(ProviderError) as error:
            self.client(password="never-log-this").authenticate()
        self.assertNotIn("never-log-this", str(error.exception))

    def test_inactive_account_rejected(self):
        with self.assertRaisesRegex(ProviderError, "inativa ou expirada"):
            self.client(username="expired").authenticate()

    def test_catalog_separates_sections_and_deduplicates_ids(self):
        catalog = self.client().catalog()
        self.assertEqual(set(catalog), {"live", "movie", "series"})
        self.assertEqual(len(catalog["movie"]["items"]), 80)
        self.assertEqual(catalog["movie"]["items"][0].categories, ("1",))
        self.assertEqual(len(catalog["movie"]["categories"]), 2)

    def test_unexpected_catalog_schema(self):
        self.provider.bad_catalog = True
        try:
            with self.assertRaises(ProviderError):
                self.client().catalog()
        finally:
            self.provider.bad_catalog = False

    def test_empty_season_list_uses_episode_groups(self):
        series = Content("series", "1", "Uma série")
        result = self.client().series_details(series)
        self.assertEqual([(ep.season, ep.episode) for ep in result["episodes"]], [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)])
        self.assertTrue(all(ep.series_id == "1" for ep in result["episodes"]))

    def test_playback_escapes_each_path_component(self):
        client = XtreamClient(Credentials("http://example.com", "user/@", "secret #/"))
        self.assertEqual(client.playback_url(Content("episode", "12", "Episode", extension="mp4")), "http://example.com/series/user%2F%40/secret%20%23%2F/12.mp4")
        self.assertTrue(client.playback_url(Content("live", "9", "TV")).endswith("/9.ts"))

    def test_credentials_repr_hides_password(self):
        self.assertNotIn("not-for-logs", repr(Credentials("http://example.com", "user", "not-for-logs")))


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.library = Library(self.directory.name)
        self.credentials = Credentials("http://example.com", "demo", "demopass")
        self.library.select_account(self.credentials)
        self.movie = Content("movie", "1", "Filme")

    def tearDown(self):
        self.library.close()
        self.directory.cleanup()

    def test_favorites_survive_reopening(self):
        self.library.toggle_favorite(self.movie)
        self.library.close()
        self.library = Library(self.directory.name)
        self.library.select_account(self.credentials)
        self.assertTrue(self.library.is_favorite(self.movie))
        self.assertFalse(self.library.toggle_favorite(self.movie))

    def test_accounts_are_isolated(self):
        self.library.toggle_favorite(self.movie)
        self.library.record_progress(self.movie, 10000, 60000)
        self.library.select_account(Credentials("http://example.com", "another-user", "pass"))
        self.assertFalse(self.library.favorites)
        self.assertFalse(self.library.continuing())
        self.library.select_account(self.credentials)
        self.assertEqual(self.library.checkpoint(self.movie)["position"], 10000)

    def test_episode_checkpoint_and_completion(self):
        series = Content("series", "9", "Série")
        episode = Content("episode", "91", "Episódio", series_id="9", series_name="Série", season=2, episode=1)
        self.library.record_progress(episode, 10000, 60000)
        self.assertEqual(self.library.checkpoint(series)["item"].uid, "episode:91")
        self.library.record_progress(episode, 60000, 60000, finished=True)
        self.assertIsNone(self.library.checkpoint(series))
        self.assertFalse(self.library.continuing())

    def test_restart_replaces_old_checkpoint(self):
        self.library.record_progress(self.movie, 30000, 60000)
        self.library.record_progress(self.movie, 2000, 60000)
        self.assertEqual(self.library.checkpoint(self.movie)["position"], 2000)

    def test_checkpoint_survives_reopening(self):
        self.library.record_progress(self.movie, 15000, 90000)
        self.library.close()
        self.library = Library(self.directory.name)
        self.library.select_account(self.credentials)
        self.assertEqual(self.library.checkpoint(self.movie)["position"], 15000)

    def test_live_and_not_started_items_do_not_enter_continue(self):
        self.library.record_progress(Content("live", "1", "Canal"), 10000, 0)
        self.library.record_progress(self.movie, 0, 90000)
        self.assertFalse(self.library.continuing())

    def test_progress_metadata_does_not_store_playback_credentials(self):
        self.library.record_progress(self.movie, 10000, 90000)
        raw = self.library.db.execute("SELECT item FROM progress").fetchone()[0]
        self.assertNotIn("demopass", raw)
        self.assertNotIn("direct_source", raw)

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_remembered_session_is_encrypted_and_can_be_cleared(self):
        sessions = SessionStore(self.directory.name)
        sessions.save(self.credentials)
        self.assertNotIn(b"demopass", sessions.path.read_bytes())
        self.assertEqual(sessions.load(), self.credentials)
        sessions.clear()
        self.assertIsNone(sessions.load())

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_corrupt_session_requires_login_without_plaintext_fallback(self):
        sessions = SessionStore(self.directory.name)
        sessions.path.write_bytes(b"not-a-valid-windows-secret")
        with self.assertRaises(OSError):
            sessions.load()


class NormalizationTests(unittest.TestCase):
    def test_invalid_server_and_embedded_credentials_are_rejected(self):
        for value in ("example.com", "ftp://example.com", "http://example.com:99999", "http://example.com/get.php?username=demo", "http://demo:pass@example.com", "http://exa mple.com"):
            self.assertIsNotNone(server_error(value))

    def test_missing_metadata_has_safe_defaults(self):
        item = content_from_api("movie", {"stream_id": 1, "category_id": 3})
        self.assertEqual(item.name, "Sem título")
        self.assertEqual(item.categories, ("3",))
        self.assertEqual(item.added, 0)
        self.assertEqual(Content.from_dict(item.to_dict()), item)

    def test_episode_duplicates_are_removed(self):
        series = Content("series", "1", "Série")
        episode = {"id": 7, "episode_num": 1}
        self.assertEqual(len(episodes_from_api(series, {"episodes": {"1": [episode, episode]}})), 1)


if __name__ == "__main__":
    unittest.main()
