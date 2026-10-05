import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import html2plaintext, is_html_empty

from odoo.addons.automatify_social.providers.base import AmbiguousPublishError

_logger = logging.getLogger(__name__)


class AutomatifySocialPost(models.Model):
    _name = "automatify.social.post"
    _description = "Social Post"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "scheduled_at desc, id desc"

    _WORKFLOW_MANAGED_FIELDS = frozenset({"state", "published_at", "failure_reason"})
    _AUTHORING_FIELDS = frozenset({"message", "image_ids"})

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
        copy=False,
    )
    scheduled_at = fields.Datetime(index=True, tracking=True, copy=False)
    published_at = fields.Datetime(readonly=True, tracking=True, copy=False)
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
    failure_reason = fields.Text(readonly=True, copy=False)

    def _ensure_workflow_fields_allowed(self, vals):
        if self.env.su or self.env.user.has_group(
            "automatify_social.group_automatify_social_manager"
        ):
            return
        if self._WORKFLOW_MANAGED_FIELDS.intersection(vals):
            raise AccessError(
                _("Publication status and result fields are managed by Social Publisher actions.")
            )

    def _ensure_edit_fields_allowed(self, vals):
        edits_authoring = bool(self._AUTHORING_FIELDS.intersection(vals))
        edits_schedule = "scheduled_at" in vals
        if not edits_authoring and not edits_schedule:
            return
        for post in self.sorted(key=lambda record: record.id):
            state = post._lock_for_publish()
            if edits_schedule:
                if state not in ("draft", "scheduled"):
                    raise UserError(
                        _("Scheduled time can only be changed while a post is Draft or Scheduled.")
                    )
                if state == "scheduled":
                    scheduled_value = vals.get("scheduled_at")
                    if not scheduled_value:
                        raise UserError(
                            _("A scheduled post must keep a scheduled date and time.")
                        )
                    scheduled_at = fields.Datetime.to_datetime(scheduled_value)
                    if scheduled_at <= fields.Datetime.now():
                        raise UserError(_("Scheduled time must be in the future."))
            if not edits_authoring:
                continue
            post.target_ids.invalidate_recordset(
                ["state", "external_post_id", "external_url"]
            )
            remote_outcome = post.target_ids.filtered(
                lambda target: target.state in ("published", "unknown")
                or target.external_post_id
                or target.external_url
            )
            if state in ("processing", "published") or remote_outcome:
                raise UserError(
                    _("Post content cannot be edited after publication has started.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._ensure_workflow_fields_allowed(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._ensure_workflow_fields_allowed(vals)
        self._ensure_edit_fields_allowed(vals)
        return super().write(vals)

    def _write_workflow_values(self, vals):
        """Apply action-managed values without re-entering public edit guards."""
        return super(AutomatifySocialPost, self.sudo()).write(vals)

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
        self.check_access("write")
        self.flush_recordset(["state"])
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
        state = self._lock_for_publish()
        self.invalidate_recordset(["scheduled_at", "target_ids"])
        self._require_targets()
        if state != "draft":
            raise UserError(_("Only draft posts can be scheduled."))
        if not self.scheduled_at:
            raise UserError(_("Choose a scheduled date and time first."))
        if self.scheduled_at <= fields.Datetime.now():
            raise UserError(_("Scheduled time must be in the future."))
        self.target_ids.sudo().write({"state": "pending", "error_message": False})
        self._write_workflow_values({"state": "scheduled", "failure_reason": False})
        return True

    def action_publish_now(self):
        if len(self) != 1:
            raise UserError(_("Post Now can only publish one post at a time."))
        post = self
        state = post._lock_for_publish()
        post.invalidate_recordset(["target_ids"])
        post._require_targets()
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
        post._write_workflow_values(values)
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
                except AmbiguousPublishError as exc:
                    _logger.warning(
                        "Social publish outcome unknown for post %s target %s: %s",
                        post.id,
                        target.id,
                        exc,
                    )
                    target.sudo().write(
                        {"state": "unknown", "error_message": str(exc)}
                    )
                except Exception as exc:
                    _logger.exception(
                        "Social publish failed for post %s target %s",
                        post.id,
                        target.id,
                    )
                    target.sudo().write(
                        {"state": "failed", "error_message": str(exc)}
                    )
                else:
                    try:
                        with self.env.cr.savepoint():
                            target.sudo().write(
                                {
                                    "state": "published",
                                    "external_post_id": result.external_post_id or False,
                                    "external_url": result.external_url or False,
                                    "published_at": result.published_at or fields.Datetime.now(),
                                    "error_message": False,
                                }
                            )
                    except Exception as exc:
                        remote_details = []
                        if result.external_post_id:
                            remote_details.append(
                                f"remote id: {result.external_post_id}"
                            )
                        if result.external_url:
                            remote_details.append(
                                f"remote url: {result.external_url}"
                            )
                        detail = _(
                            "Remote publication succeeded, but Odoo could not record the "
                            "result. Verify the remote post before retrying."
                        )
                        if remote_details:
                            detail = f"{detail} {'; '.join(remote_details)}"
                        _logger.exception(
                            "Social publish bookkeeping failed after remote success for post %s "
                            "target %s",
                            post.id,
                            target.id,
                        )
                        target.sudo().write(
                            {"state": "unknown", "error_message": detail}
                        )

            unknown = post._unknown_targets()
            failed = post.target_ids.filtered(lambda target: target.state == "failed")
            pending = post.target_ids.filtered(lambda target: target.state == "pending")
            if unknown:
                post._write_workflow_values(
                    {
                        "state": "failed",
                        "failure_reason": _(
                            "One or more channels have an unknown publication outcome. "
                            "Verify the remote network before attempting another publication."
                        ),
                    }
                )
            elif failed:
                post._write_workflow_values(
                    {
                        "state": "failed",
                        "failure_reason": _("One or more channels failed to publish."),
                    }
                )
            elif not pending:
                post._write_workflow_values(
                    {
                        "state": "published",
                        "published_at": fields.Datetime.now(),
                        "failure_reason": False,
                    }
                )

    def action_retry_failed(self):
        if len(self) != 1:
            raise UserError(_("Retry Failed can only retry one post at a time."))
        post = self
        state = post._lock_for_publish()
        post.target_ids.invalidate_recordset(
            [
                "state",
                "external_post_id",
                "external_url",
                "published_at",
                "error_message",
            ]
        )
        if state != "failed":
            raise UserError(_("Only failed posts can be retried."))
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
            target.sudo().write(
                {
                    "state": "published",
                    "published_at": target.published_at or fields.Datetime.now(),
                    "error_message": False,
                }
            )

        retryable = failed - recovered
        retryable.sudo().write({"state": "pending", "error_message": False})
        post._write_workflow_values({"state": "processing", "failure_reason": False})
        post._publish_pending_targets()
        return True

    def action_cancel(self):
        for post in self.sorted(key=lambda record: record.id):
            state = post._lock_for_publish()
            if state in ("processing", "published"):
                raise UserError(_("Processing or published posts cannot be cancelled."))
            post._write_workflow_values({"state": "cancelled"})
        return True

    def action_reset_to_draft(self):
        for post in self.sorted(key=lambda record: record.id):
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
            post.target_ids.sudo().write({"state": "pending", "error_message": False})
            post._write_workflow_values(
                {
                    "state": "draft",
                    "scheduled_at": False,
                    "failure_reason": False,
                }
            )
        return True

    def _publish_scheduled_if_due(self):
        self.ensure_one()
        state = self._lock_for_publish()
        self.invalidate_recordset(["scheduled_at"])
        if (
            state != "scheduled"
            or not self.scheduled_at
            or self.scheduled_at > fields.Datetime.now()
        ):
            return False
        self.action_publish_now()
        return True

    @api.model
    def _cron_publish_scheduled(self):
        due_posts = self.search(
            [
                ("state", "=", "scheduled"),
                ("scheduled_at", "<=", fields.Datetime.now()),
            ],
            order="scheduled_at asc, id asc",
            limit=50,
        )
        for post in due_posts:
            try:
                with self.env.cr.savepoint():
                    post._publish_scheduled_if_due()
            except Exception:
                _logger.exception("Scheduled social post %s failed", post.id)
        return True


class AutomatifySocialPostTarget(models.Model):
    _name = "automatify.social.post.target"
    _description = "Social Post Target"
    _order = "id"

    _WORKFLOW_MANAGED_FIELDS = frozenset(
        {"state", "external_post_id", "external_url", "published_at", "error_message"}
    )

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
        copy=False,
    )
    external_post_id = fields.Char(readonly=True, copy=False)
    external_url = fields.Char(readonly=True, copy=False)
    published_at = fields.Datetime(readonly=True, copy=False)
    error_message = fields.Text(readonly=True, copy=False)

    _post_account_unique = models.Constraint(
        "unique(post_id, account_id)",
        "The same social account can only be added once to a post.",
    )

    def _ensure_workflow_fields_allowed(self, vals, creating=False):
        if self.env.su or self.env.user.has_group(
            "automatify_social.group_automatify_social_manager"
        ):
            return
        protected = self._WORKFLOW_MANAGED_FIELDS
        if not creating:
            protected = protected | {"post_id"}
        if protected.intersection(vals):
            raise AccessError(
                _("Publication status and remote-result fields are managed by Social Publisher.")
            )

    def _ensure_parent_allows_target_creation(self, vals_list):
        if self.env.su:
            return
        post_ids = sorted(
            {vals.get("post_id") for vals in vals_list if vals.get("post_id")}
        )
        if not post_ids:
            return
        locked_states = {}
        posts = self.env["automatify.social.post"].browse(post_ids)
        for post in posts.sorted(key=lambda record: record.id):
            locked_states[post.id] = post._lock_for_publish()
        if any(locked_states[post_id] != "draft" for post_id in post_ids):
            raise AccessError(_("Channels can only be added while the post is still in Draft."))

    def _ensure_account_change_allowed(self, vals):
        if "account_id" not in vals or self.env.su:
            return
        locked_states = {}
        for post in self.mapped("post_id").sorted(key=lambda record: record.id):
            locked_states[post.id] = post._lock_for_publish()
        self.invalidate_recordset(["state", "post_id"])
        for target in self:
            if target.state != "pending" or locked_states.get(target.post_id.id) != "draft":
                raise AccessError(
                    _(
                        "A social account can only be changed while its post is still in Draft "
                        "and the channel has not started publication."
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._ensure_workflow_fields_allowed(vals, creating=True)
        self._ensure_parent_allows_target_creation(vals_list)
        return super().create(vals_list)

    def write(self, vals):
        self._ensure_workflow_fields_allowed(vals)
        self._ensure_account_change_allowed(vals)
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            locked_states = {}
            for post in self.mapped("post_id").sorted(key=lambda record: record.id):
                locked_states[post.id] = post._lock_for_publish()
            self.invalidate_recordset(["state", "post_id"])
            for target in self:
                if (
                    target.state != "pending"
                    or locked_states.get(target.post_id.id) != "draft"
                ):
                    raise AccessError(
                        _(
                            "Channels can only be removed while the post is still in Draft and "
                            "the channel has not started publication."
                        )
                    )
        return super().unlink()

    @api.constrains("post_id", "account_id")
    def _check_company_match(self):
        for target in self:
            if (
                target.post_id
                and target.account_id
                and target.post_id.company_id != target.account_id.company_id
            ):
                raise ValidationError(
                    _("The social account must belong to the same company as the post.")
                )
