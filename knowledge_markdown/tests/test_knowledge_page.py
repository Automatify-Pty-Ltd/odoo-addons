from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestKnowledgeMarkdownPage(TransactionCase):
    def test_category_with_children_cannot_become_content(self):
        category = self.env["knowledge.markdown.page"].create(
            {"name": "Category", "page_type": "category"}
        )
        self.env["knowledge.markdown.page"].create(
            {
                "name": "Child",
                "page_type": "content",
                "parent_id": category.id,
            }
        )

        with self.assertRaises(ValidationError):
            category.write({"page_type": "content"})
