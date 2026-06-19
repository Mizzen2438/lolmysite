from django.test import TestCase

from .models import Game


class GameModelTests(TestCase):
    def test_create_game_with_master_data(self):
        game = Game.objects.create(
            name="League of Legends",
            slug="league-of-legends",
            modes=["ARAM"],
            lanes=["TOP", "MID"],
            rank_tiers=["アイアン", "ブロンズ"],
        )
        self.assertEqual(str(game), "League of Legends")
        self.assertEqual(game.lanes, ["TOP", "MID"])
        self.assertTrue(game.is_active)

    def test_load_league_fixture(self):
        from django.core.management import call_command

        call_command("loaddata", "league_of_legends", verbosity=0)
        game = Game.objects.get(slug="league-of-legends")
        self.assertIn("TOP", game.lanes)
        self.assertEqual(len(game.rank_tiers), 10)
