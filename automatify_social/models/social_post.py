import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html2plaintext, is_html_empty

from odoo.addons.automatify_social.providers.base import AmbiguousPublishError

_logger = logging.getLogger(__name__)


class AutomatifySocialPost(models.Model):
    _name = "automatify.social.post"
    _description = "Social Post"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "scheduled_at desc, id desc"

    name = fields.Char(compute="_compute_name")
    message = fields.Html(
        string="Post Content",
        required=True,
        tracking=True,
        sanitize=True,
        help="Rich authoring content. Connectors publish a provider-safe text rendering.",
    )
    message_text = fields.Text(
        string="Outbound Text",
        compute="_compute_message_text",
        help="Plain-text representation sent to social-network APIs.",
    )
    image_ids = fields.Many2many(
        "ir.attachment",
        "automatify_social_post_image_rel",
        "post_id",
        "attachment_id",
        string="Image",
        copy=False,
        help="Optional image attached to this social post. Stage 1.1 supports one image per post.",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("scheduled", "Scheduled"),
            ("processing", "Processing"),
            ("published", "Published"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        index=True,
        tracking=True,
    )
    scheduled_at = fields.Datetime(index=True, tracking=True)
    published_at = fields.Datetime(readonly=True, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        ondelete="cascade",
    )
    target_ids = fields.One2many(
        "automatify.social.post.target",
        "post_id",
        string="Channels",
        copy=True,
    )
    failure_reason = fields.Text(readonly=True)

    @api.depends("message")
    def _compute_message_text(self):
        for post in self:
            post.message_text = html2plaintext(post.message or "", include_references=True)

    @api.depends("message")
    def _compute_name(self):
        for post in self:
            text = html2plaintext(post.message or "", include_references=False)
            text = " ".join(text.split())
            post.name = text[:80] or _("Social Post")

    @api.constrains("message")
    def _check_message_content(self):
        for post in self:
            if is_html_empty(post.message):
                raise ValidationError(_("Post content cannot be empty."))

    @api.constrains("image_ids")
    def _check_images(self):
        for post in self:
            if len(post.image_ids) > 1:
                raise ValidationError(_("Stage 1.1 currently supports one image per social post."))
            invalid = post.image_ids.filtered(
                lambda attachment: not (attachment.mimetype or "").startswith("image/")
            )
            if invalid:
                raise ValidationError(_("Only image attachments can be added to a social post."))

    @api.constrains("target_ids", "company_id")
    def _check_target_companies(self):
        for post in self:
            mismatched = post.target_ids.filtered(
                lambda target: target.account_id.company_id != post.company_id
            )
            if mismatched:
                raise ValidationError(_("All social accounts must belong to the post company."))

    def _require_targets(self):
        for post in self:
            if not post.target_ids:
                raise UserError(_("Add at least one social account before publishing."))

    def _lock_for_publish(self):
        """Serialize publication per post to avoid cron/manual duplicate writes."""
        self.ensure_one()
        self.env.cr.execute(
            "SELECT state FROM automatify_social_post WHERE id = %s FOR UPDATE",
            [self.id],
        )
        row = self.env.cr.fetchone()
        self.invalidate_recordset(["state"])
        return row[0] if row else self.state

    def _unknown_targets(self):
        self.ensure_one()
        return self.target_ids.filtered(lambda target: target.state == "unknown")

    def action_schedule(self):
        self.ensure_one()
        self._require_targets()
        if not self.scheduled_at:
            raise UserError(_("Choose a scheduled date and time first."))
        if self.scheduled_at <= fields.Datetime.now():
            raise UserError(_("Scheduled time must be in the future."))
        state = self._lock_for_publish()
        if state != "draft":
            raise UserError(_("Only draft posts can be scheduled."))
        self.target_ids.write({"state": "pending", "error_message": False})
        self.write({"state": "scheduled", "failure_reason": False})
        return True

    def action_publish_now(self):
        for post in self:
            post._require_targets()
            state = post._lock_for_publish()
            if state in ("processing", "published", "cancelled"):
                raise UserError(_("This post cannot be published in its current state."))
            if post._unknown_targets():
                raise UserError(
                    _(
                        "A channel has an unknown publication outcome. Verify the post on the "
                        "network before attempting any new publication."
                    )
                )
            if state == "failed" and post.target_ids.filtered(
                lambda target: target.state == "failed"
            ):
                raise UserError(_("Use Retry Failed to retry failed channels."))
            values = {"state": "processing", "failure_reason": False}
            if state == "draft":
                values["scheduled_at"] = False
            post.write(values)
            post._publish_pending_targets()
        return True

    def _publish_pending_targets(self):
        for post in self:
            targets = post.target_ids.filtered(lambda target: target.state == "pending")
            for target in targets:
                try:
                    account = target.account_id
                    provider = account._get_social_provider()
                    # Authorization is enforced on the post/target/account before this point.
                    # Elevate only the internal provider record so connector code can use
                    # manager-restricted OAuth token fields without exposing them to publishers.
                    result = provider.publish(account.sudo(), post)
                    target.write(
                        {
                            "state": "published",
                            "external_post_id": result.external_post_id or False,
                            "external_url": result.external_url or False,
                            "published_at": result.published_at or fields.Datetime.now(),
                            "error_message": False,
                        }
                    )
                except AmbiguousPublishError as exc:
                    _logger.warning(
                        "Social publish outcome unknown for post %s target %s: %s",
                        post.id,
                        target.id,
                        exc,
                    )
                    target.write({"state": "unknown", "error_message": str(exc)})
                except Exception as exc:
                    _logger.exception(
                        "Social publish failed for post %s target %s",
                        post.id,
                        target.id,
                    )
                    target.write({"state": "failed", "error_message": str(exc)})

            unknown = post._unknown_targets()
            failed = post.target_ids.filtered(lambda target: target.state == "failed")
            pending = post.target_ids.filtered(lambda target: target.state == "pending")
            if unknown:
                post.write(
                    {
                        "state": "failed",
                        "failure_reason": _(
                            "One or more channels have an unknown publication outcome. "
                            "Verify the remote network before attempting another publication."
                        ),
                    }
                )
            elif failed:
                post.write(
                    {
                        "state": "failed",
                        "failure_reason": _("One or more channels failed to publish."),
                    }
                )
            elif not pending:
                post.write(
                    {
                        "state": "published",
                        "published_at": fields.Datetime.now(),
                        "failure_reason": False,
                    }
                )

    def action_retry_failed(self):
        for post in self:
            if post._unknown_targets():
                raise UserError(
                    _(
                        "A channel has an unknown publication outcome and cannot be retried "
                        "automatically. Verify the post on the remote network first."
                    )
                )
            failed = post.target_ids.filtered(lambda target: target.state == "failed")
            if not failed:
                raise UserError(_("There are no failed channels to retry."))

            recovered = failed.filtered(
                lambda target: target.external_post_id or target.external_url
            )
            for target in recovered:
                target.write(
                    {
                        "state": "published",
                        "published_at": target.published_at or fields.Datetime.now(),
                        "error_message": False,
                    }
                )

            retryable = failed - recovered
            retryable.write({"state": "pending", "error_message": False})
            post.action_publish_now()
        return True

    def action_cancel(self):
        for post in self:
            if post.state in ("processing", "published"):
                raise UserError(_("Processing or published posts cannot be cancelled."))
            post.write({"state": "cancelled"})
        return True

    def action_reset_to_draft(self):
        for post in self:
            state = post._lock_for_publish()
            if state in ("processing", "published"):
                raise UserError(_("Processing or published posts cannot be reset to draft."))
            if post._unknown_targets():
                raise UserError(
                    _(
                        "A channel has an unknown publication outcome and cannot be reset to "
                        "draft until the remote post has been verified."
                    )
                )
            if post.target_ids.filtered(lambda target: target.state == "published"):
                raise UserError(
                    _(
                        "A post already published to one or more channels cannot be reset. "
                        "Use Retry Failed for the remaining channels."
                    )
                )
            post.target_ids.write({"state": "pending", "error_message": False})
            post.write(
                {
                    "state": "draft",
                    "scheduled_at": False,
                    "failure_reason": False,
                }
            )
        return True

    @api.model
    def _cron_publish_scheduled(self):
        due_posts = self.search(
            [
                ("state", "=", "scheduled"),
                ("scheduled_at", "<=", fields.Datetime.now()),
            ],
            order="scheduled_at asc",
            limit=50,
        )
        for post in due_posts:
            try:
                with self.env.cr.savepoint():
                    post.action_publish_now()
            except Exception:
                _logger.exception("Scheduled social post %s failed", post.id)
        return True


class AutomatifySocialPostTarget(models.Model):
    _name = "automatify.social.post.target"
    _description = "Social Post Target"
    _order = "id"

    post_id = fields.Many2one(
        "automatify.social.post",
        required=True,
        ondelete="cascade",
        index=True,
    )
    account_id = fields.Many2one(
        "automatify.social.account",
        required=True,
        ondelete="restrict",
        index=True,
    )
    company_id = fields.Many2one(
        related="post_id.company_id",
        store=True,
        index=True,
    )
    state = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("published", "Published"),
            ("failed", "Failed"),
            ("unknown", "Outcome Unknown"),
        ],
        default="pending",
        required=True,
        index=True,
    )
    external_post_id = fields.Char(readonly=True)
    external_url = fields.Char(readonly=True)
    published_at = fields.Datetime(readonly=True)
    error_message = fields.Text(readonly=True)

    _post_account_unique = models.Constraint(
        "unique(post_id, account_id)",
        "The same social account can only be added once to a post.",
    )

    @api.constrains("post_id", "account_id")
    def _check_company_match(self):
        for target in self:
            if (
                target.post_id
                and target.account_id
                and target.post_id.company_id != target.account_id.company_id
            ):
                raise ValidationError(
                    _("The social account must belong to the same company as the post."))
                )
