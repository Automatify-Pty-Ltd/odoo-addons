from odoo import fields, models


class AutomatifySocialLinkedInOAuthState(models.Model):
    _name = "automatify.social.linkedin.oauth.state"
    _description = "LinkedIn OAuth State"
    _order = "create_date desc"

    token = fields.Char(required=True, index=True, copy=False)
    account_id = fields.Many2one(
        "automatify.social.account", required=True, ondelete="cascade", index=True
    )
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    expires_at = fields.Datetime(required=True, index=True)

    _token_unique = models.Constraint(
        "unique(token)",
        "OAuth state must be unique.",
    )
