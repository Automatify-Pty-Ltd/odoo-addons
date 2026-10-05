from odoo import _, models
from odoo.exceptions import UserError


class AutomatifySocialPostUnlink(models.Model):
    _inherit = "automatify.social.post"

    def unlink(self):
        """Only drafts may be deleted; serialize with publication before deciding."""
        for post in self.sorted(key=lambda record: record.id):
            state = post._lock_for_publish()
            if state != "draft":
                raise UserError(
                    _(
                        "Only draft social posts can be deleted. Cancel or safely reset the post "
                        "to Draft first so a concurrent or completed remote publication cannot be "
                        "orphaned from Odoo."
                    )
                )
        return super().unlink()
