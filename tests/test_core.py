import os
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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
        account = self.client().authenticate()
        self.assertEqual(account["status"], "Active")
        self.assertEqual(account["active_cons"], "0")
        self.assertEqual(account["max_connections"], "2")
        self.assertEqual(account["exp_date"], "1893456000")

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

    def test_playback_preference_survives_restart_and_account_change(self):
        self.assertFalse(self.library.auto_next_enabled)
        self.library.set_auto_next(True)
        self.library.close()
        self.library = Library(self.directory.name)
        self.assertTrue(self.library.auto_next_enabled)
        self.library.select_account(Credentials("http://example.com", "another-user", "pass"))
        self.assertTrue(self.library.auto_next_enabled)
        self.library.set_auto_next(False)
        self.assertFalse(self.library.auto_next_enabled)

    def test_episode_favorite_is_the_series_and_shared_between_episodes(self):
        episode = Content("episode", "91", "Um episódio", series_id="9", series_name="Série", artwork="cover", plot="Sinopse do episódio")
        other = Content("episode", "92", "Outro episódio", series_id="9")
        series = Content("series", "9", "Série")
        self.assertTrue(self.library.toggle_favorite(episode))
        self.assertEqual(list(self.library.favorites), [series.uid])
        self.assertEqual(self.library.favorites[series.uid].name, "Série")
        self.assertEqual(self.library.favorites[series.uid].artwork, "cover")
        self.assertEqual(self.library.favorites[series.uid].plot, "")
        self.assertTrue(self.library.is_favorite(other))
        self.assertTrue(self.library.is_favorite(series))
        self.assertFalse(self.library.toggle_favorite(other))
        self.assertFalse(self.library.is_favorite(episode))
        self.assertEqual(self.library.db.execute("SELECT COUNT(*) FROM favorites").fetchone()[0], 0)

    def test_legacy_episode_favorites_migrate_once_without_losing_series_or_progress(self):
        series = Content("series", "9", "Série completa", plot="Sinopse da série", added=100)
        episodes = [Content("episode", str(i), "Episódio", series_id="9", series_name="Série", episode=i) for i in (2, 6)]
        self.library.toggle_favorite(series)
        self.library.toggle_favorite(self.movie)
        other_account = "another-account"
        with self.library.db:
            for episode in episodes:
                for account in (self.library.account, other_account):
                    self.library.db.execute("INSERT INTO favorites VALUES (?,?,?,?)", (account, episode.uid, json.dumps(episode.to_dict()), 200))
        self.library.record_progress(episodes[-1], 15000, 90000)
        self.library.select_account(self.credentials)
        self.assertEqual(set(self.library.favorites), {series.uid, self.movie.uid})
        self.assertEqual(self.library.favorites[series.uid], series)
        self.assertEqual(self.library.checkpoint(series)["position"], 15000)
        self.assertEqual(self.library.db.execute("SELECT COUNT(*) FROM favorites WHERE account=? AND uid LIKE 'episode:%'", (self.library.account,)).fetchone()[0], 0)
        self.assertEqual(self.library.db.execute("SELECT COUNT(*) FROM favorites WHERE account=?", (other_account,)).fetchone()[0], 2)
        self.library.select_account(self.credentials)
        self.assertEqual(set(self.library.favorites), {series.uid, self.movie.uid})

    def test_legacy_episode_only_favorites_become_one_durable_series(self):
        for i in (2, 6):
            episode = Content("episode", str(i), "Episódio", series_id="9", series_name="Série", artwork="cover", episode=i)
            with self.library.db:
                self.library.db.execute("INSERT INTO favorites VALUES (?,?,?,?)", (self.library.account, episode.uid, json.dumps(episode.to_dict()), i))
        self.library.select_account(self.credentials)
        self.assertEqual(list(self.library.favorites), ["series:9"])
        self.assertEqual(self.library.favorites["series:9"].name, "Série")
        self.library.close()
        self.library = Library(self.directory.name)
        self.library.select_account(self.credentials)
        self.assertEqual(list(self.library.favorites), ["series:9"])

    def test_episode_without_parent_id_cannot_be_favorited_by_title(self):
        episode = Content("episode", "91", "Episódio", series_name="Série")
        self.assertFalse(self.library.toggle_favorite(episode))
        self.assertFalse(self.library.is_favorite(episode))
        self.assertFalse(self.library.favorites)

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

    def test_continue_has_one_latest_episode_per_series_and_preserves_checkpoints(self):
        second = Content("episode", "2", "Segundo", series_id="9", series_name="Série", episode=2)
        sixth = Content("episode", "6", "Sexto", series_id="9", series_name="Série", episode=6)
        other = Content("episode", "20", "Outra", series_id="10", series_name="Série")
        with patch("smartiptv.storage.time.time", side_effect=[10, 20, 30, 40]):
            for item in (second, sixth, other, self.movie):
                self.library.record_progress(item, 10000, 90000)
        self.assertEqual(self.library.continuing(), [self.movie, other, sixth])
        self.assertEqual(self.library.checkpoint(second)["position"], 10000)
        self.assertEqual(self.library.checkpoint(Content("series", "9", "Série"))["item"], sixth)
        self.library.close()
        self.library = Library(self.directory.name)
        self.library.select_account(self.credentials)
        self.assertEqual(self.library.continuing(), [self.movie, other, sixth])

    def test_continue_uses_most_recently_watched_not_highest_episode_number(self):
        sixth = Content("episode", "6", "Sexto", series_id="9", episode=6)
        second = Content("episode", "2", "Segundo", series_id="9", episode=2)
        with patch("smartiptv.storage.time.time", side_effect=[10, 20]):
            self.library.record_progress(sixth, 10000, 90000)
            self.library.record_progress(second, 20000, 90000)
        self.assertEqual(self.library.continuing(), [second])
        self.assertEqual(self.library.checkpoint(Content("series", "9", "Série"))["item"], second)

    def test_completed_latest_episode_does_not_resurrect_older_unfinished_one(self):
        second = Content("episode", "2", "Segundo", series_id="9")
        sixth = Content("episode", "6", "Sexto", series_id="9")
        with patch("smartiptv.storage.time.time", side_effect=[10, 20]):
            self.library.record_progress(second, 10000, 90000)
            self.library.record_progress(sixth, 90000, 90000, True)
        self.assertEqual(self.library.continuing(), [])
        self.assertIsNone(self.library.checkpoint(Content("series", "9", "Série")))
        self.assertIsNotNone(self.library.checkpoint(second))

    def test_removing_series_from_continue_does_not_reveal_old_duplicates(self):
        episodes = [Content("episode", str(i), "Episódio", series_id="9") for i in (2, 6)]
        for episode in episodes:
            self.library.record_progress(episode, 10000, 90000)
        self.library.toggle_favorite(episodes[0])
        self.library.record_progress(self.movie, 10000, 90000)
        self.library.remove_progress(episodes[-1])
        self.assertEqual(self.library.continuing(), [self.movie])
        self.assertTrue(self.library.is_favorite(episodes[0]))
        self.library.select_account(self.credentials)
        self.assertEqual(self.library.continuing(), [self.movie])

    def test_episodes_without_series_ids_are_not_merged_by_name(self):
        episodes = [Content("episode", str(i), "Episódio", series_name="Sem identificação") for i in (1, 2)]
        for episode in episodes:
            self.library.record_progress(episode, 10000, 90000)
        self.assertEqual(len(self.library.continuing()), 2)

    def test_equal_windows_clock_ticks_and_clock_rollback_keep_last_access_first(self):
        second = Content("episode", "2", "Segundo", series_id="9")
        sixth = Content("episode", "6", "Sexto", series_id="9")
        with patch("smartiptv.storage.time.time", side_effect=[42, 42, 10]):
            self.library.record_progress(second, 10000, 90000)
            self.library.record_progress(sixth, 10000, 90000)
            self.assertEqual(self.library.continuing(), [sixth])
            self.library.record_progress(second, 20000, 90000)
        self.assertEqual(self.library.continuing(), [second])
        self.library.select_account(self.credentials)
        self.assertEqual(self.library.continuing(), [second])

    def test_legacy_equal_timestamps_use_last_persisted_episode(self):
        second = Content("episode", "2", "Segundo", series_id="9")
        sixth = Content("episode", "6", "Sexto", series_id="9")
        self.library.record_progress(second, 10000, 90000)
        self.library.record_progress(sixth, 10000, 90000)
        with self.library.db:
            self.library.db.execute("UPDATE progress SET updated=42 WHERE account=?", (self.library.account,))
        self.library.select_account(self.credentials)
        self.assertEqual(self.library.continuing(), [sixth])
        self.assertEqual(self.library.checkpoint(Content("series", "9", "Série"))["item"], sixth)

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
