from odoo import _, models
from odoo.exceptions import UserError


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    _SOCIAL_MEDIA_CONTENT_FIELDS = frozenset(
        {"datas", "raw", "db_datas", "store_fname", "mimetype"}
    )

    def _lock_referencing_social_posts(self):
        if not self.ids:
            return []
        self.env["automatify.social.post"].flush_model(["state"])
        self.env.cr.execute(
            """
            SELECT post.id, post.state
              FROM automatify_social_post AS post
             WHERE EXISTS (
                       SELECT 1
                         FROM automatify_social_post_image_rel AS rel
                        WHERE rel.post_id = post.id
                          AND rel.attachment_id = ANY(%s)
                   )
             ORDER BY post.id
             FOR UPDATE
            """,
            [list(self.ids)],
        )
        return self.env.cr.fetchall()

    def _ensure_social_media_mutation_allowed(self):
        referenced_posts = self._lock_referencing_social_posts()
        if any(state != "draft" for _post_id, state in referenced_posts):
            raise UserError(
                _(
                    "An image used by a non-draft social post cannot be changed or deleted. "
                    "Reset the post to Draft first, or create a new attachment."
                )
            )

    def write(self, vals):
        if self._SOCIAL_MEDIA_CONTENT_FIELDS.intersection(vals):
            self._ensure_social_media_mutation_allowed()
        return super().write(vals)

    def unlink(self):
        self._ensure_social_media_mutation_allowed()
        return super().unlink()
