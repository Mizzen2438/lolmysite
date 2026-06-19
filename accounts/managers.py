from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Manager for the Discord-OAuth-based custom user.

    Regular users authenticate via Discord and have no usable password.
    Staff/superusers are created with ``createsuperuser`` and use a password
    so they can sign in to the Django admin (F-SAFE-07).
    """

    use_in_migrations = True

    def create_user(self, discord_id, password=None, **extra_fields):
        if not discord_id:
            raise ValueError("discord_id は必須です。")
        user = self.model(discord_id=str(discord_id), **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, discord_id, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("status", self.model.Status.ACTIVE)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("スーパーユーザーは is_staff=True である必要があります。")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("スーパーユーザーは is_superuser=True である必要があります。")

        return self.create_user(discord_id, password, **extra_fields)
