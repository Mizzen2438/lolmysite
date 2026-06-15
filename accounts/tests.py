from datetime import UTC, datetime

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from .utils import discord_id_to_created_at, is_discord_account_old_enough

User = get_user_model()


class SnowflakeUtilTests(TestCase):
    def test_known_snowflake_decodes_to_creation_time(self):
        # Discord documentation's reference snowflake.
        created = discord_id_to_created_at(175928847299117063)
        self.assertEqual(created.year, 2016)
        self.assertEqual(created.month, 4)

    def test_account_age_gate(self):
        now = datetime(2026, 6, 15, tzinfo=UTC)
        # An account created in 2016 is clearly older than 90 days.
        self.assertTrue(
            is_discord_account_old_enough("175928847299117063", 90, now=now)
        )


class UserModelTests(TestCase):
    def test_create_user_has_no_usable_password(self):
        user = User.objects.create_user(discord_id="123", discord_name="tester")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(str(user), "tester")
        self.assertFalse(user.is_riot_linked)

    def test_create_superuser_can_access_admin(self):
        admin = User.objects.create_superuser(discord_id="999", password="pw-secret-123")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.has_usable_password())

    def test_discord_id_is_unique(self):
        User.objects.create_user(discord_id="555")
        with self.assertRaises(IntegrityError):
            User.objects.create_user(discord_id="555")

    def test_riot_id_property(self):
        user = User.objects.create_user(
            discord_id="222", riot_game_name="Hikari", riot_tagline="JP1"
        )
        self.assertEqual(user.riot_id, "Hikari#JP1")
