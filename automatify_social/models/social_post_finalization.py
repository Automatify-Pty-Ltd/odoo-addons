import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class AutomatifySocialPostFinalization(models.Model):
    _inherit = "automatify.social.post"

    def _write_workflow_values(self, vals):
        """Keep recorded remote successes durable if final parent publication fails."""
        if vals.get("state") != "published":
            return super()._write_workflow_values(vals)

        try:
            with self.env.cr.savepoint():
                return super()._write_workflow_values(vals)
        except Exception:
            _logger.exception(
                "Social post parent finalization failed after remote success for posts %s",
                self.ids,
            )
            reason = _(
                "Remote publication results were recorded, but Odoo could not finalize the "
                "parent post. Automatic retry is disabled; verify the remote posts before "
                "intervening."
            )
            for post in self:
                self.env.cr.execute(
                    """
                    UPDATE automatify_social_post
                       SET state = %s,
                           published_at = NULL,
                           failure_reason = %s
                     WHERE id = %s
                    """,
                    ["failed", reason, post.id],
                )
            self.invalidate_recordset(["state", "published_at", "failure_reason"])
            return True
