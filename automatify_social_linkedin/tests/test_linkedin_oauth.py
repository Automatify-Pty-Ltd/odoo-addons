from datetime import timedelta
from unittest.mock import Mock, patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.automatify_social_linkedin.controllers.oauth import (
    AutomatifySocialLinkedInOAuthController,
)


class TestLinkedInOAuth(TransactionCase):
    def setUp(self):
        super().setUp()
        self.account = self.env["automatify.social.account"].create(
            {
                "name": "LinkedIn Test Account",
                "platform": "linkedin",
                "linkedin_author_type": "organization",
            }
        )
        self.regular_user = new_test_user(
            self.env,
            login="linkedin-settings-user",
            email="linkedin-settings-user@example.com",
            groups="base.group_user",
        )

    def test_organization_scopes(self):
        self.assertEqual(
            self.account._linkedin_oauth_scopes(),
            ["rw_organization_admin", "w_organization_social"],
        )

    def test_member_scopes_use_oidc_and_share_permission(self):
        self.account.linkedin_author_type = "member"
        self.assertEqual(
            self.account._linkedin_oauth_scopes(),
            ["openid", "profile", "w_member_social"],
        )

    def test_member_identity_uses_oidc_userinfo_sub(self):
        controller = AutomatifySocialLinkedInOAuthController()
        response = Mock(status_code=200, text="")
        response.json.return_value = {
            "sub": "member-123",
            "name": "LinkedIn Test Member",
        }
        with patch(
            "odoo.addons.automatify_social_linkedin.controllers.oauth.requests.get",
            return_value=response,
        ) as get_request:
            author_urn, display_name = controller._resolve_member("test-token")

        self.assertEqual(author_urn, "urn:li:person:member-123")
        self.assertEqual(display_name, "LinkedIn Test Member")
        self.assertEqual(
            get_request.call_args.args[0], "https://api.linkedin.com/v2/userinfo"
        )

    def test_organization_identity_traverses_acl_pages(self):
        controller = AutomatifySocialLinkedInOAuthController()
        configured_urn = "urn:li:organization:222"
        self.account.linkedin_author_urn = configured_urn

        first_response = Mock(status_code=200, text="")
        first_response.json.return_value = {
            "elements": [
                {
                    "state": "APPROVED",
                    "role": "ADMINISTRATOR",
                    "organization": "urn:li:organization:111",
                }
            ],
            "paging": {
                "start": 0,
                "count": 1,
                "links": [{"rel": "next", "href": "/rest/organizationAcls?start=1"}],
            },
        }
        second_response = Mock(status_code=200, text="")
        second_response.json.return_value = {
            "elements": [
                {
                    "state": "APPROVED",
                    "role": "CONTENT_ADMIN",
                    "organizationTarget": configured_urn,
                }
            ],
            "paging": {"start": 1, "count": 1, "links": []},
        }

        with patch(
            "odoo.addons.automatify_social_linkedin.controllers.oauth.requests.get",
            side_effect=[first_response, second_response],
        ) as get_request:
            author_urn, display_name = controller._resolve_organization(
                self.account, "test-token"
            )

        self.assertEqual(author_urn, configured_urn)
        self.assertIsNone(display_name)
        self.assertEqual(get_request.call_count, 2)
        self.assertEqual(
            get_request.call_args_list[1].kwargs["params"],
            {
                "q": "roleAssignee",
                "state": "APPROVED",
                "start": 1,
                "count": 1,
            },
        )

    def test_redirect_uri_uses_odoo_base_url(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "web.base.url", "https://odoo.example.com/"
        )
        self.assertEqual(
            self.account._linkedin_redirect_uri(),
            "https://odoo.example.com/automatify-social/linkedin/oauth/callback",
        )

    def test_settings_secrets_and_writes_are_manager_only(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("automatify_social_linkedin.client_id", "original-id")
        params.set_param(
            "automatify_social_linkedin.client_secret", "original-secret"
        )
        settings_model = self.env[
            "automatify.social.linkedin.settings"
        ].with_user(self.regular_user)

        with self.assertRaises(AccessError):
            settings_model.default_get(["client_id", "client_secret", "callback_url"])

        manager_user = new_test_user(
            self.env,
            login="linkedin-settings-manager",
            email="linkedin-settings-manager@example.com",
            groups="automatify_social.group_automatify_social_manager",
        )
        settings = (
            self.env["automatify.social.linkedin.settings"]
            .with_user(manager_user)
            .create({"client_id": "attacker-id", "client_secret": "attacker-secret"})
            .with_user(self.regular_user)
        )
        with self.assertRaises(AccessError):
            settings.action_save()

        self.assertEqual(
            params.get_param("automatify_social_linkedin.client_id"), "original-id"
        )
        self.assertEqual(
            params.get_param("automatify_social_linkedin.client_secret"),
            "original-secret",
        )

    def test_oauth_state_is_locked_before_one_time_consumption(self):
        state_model = self.env["automatify.social.linkedin.oauth.state"].sudo()
        state_record = state_model.create(
            {
                "token": "linkedin-one-time-state",
                "account_id": self.account.id,
                "user_id": self.env.user.id,
                "expires_at": fields.Datetime.now() + timedelta(minutes=10),
            }
        )

        locked = state_model._lock_for_consume("linkedin-one-time-state")
        self.assertEqual(locked, state_record)
        locked.unlink()
        self.assertFalse(state_model._lock_for_consume("linkedin-one-time-state"))
