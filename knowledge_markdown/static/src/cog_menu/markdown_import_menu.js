import { Component } from "@odoo/owl";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { exprToBoolean } from "@web/core/utils/strings";
import { STATIC_ACTIONS_GROUP_NUMBER } from "@web/search/action_menus/action_menus";

const cogMenuRegistry = registry.category("cogMenu");

export class ImportMarkdown extends Component {
    static template = "knowledge_markdown.ImportMarkdown";
    static components = { DropdownItem };
    static props = {};

    setup() {
        this.action = useService("action");
    }

    importMarkdown() {
        return this.action.doAction("knowledge_markdown.action_knowledge_markdown_import_new");
    }
}

export const importMarkdownItem = {
    Component: ImportMarkdown,
    groupNumber: STATIC_ACTIONS_GROUP_NUMBER,
    isDisplayed: ({ config, isSmall, searchModel }) =>
        !isSmall &&
        searchModel.resModel === "document.page" &&
        config.actionType === "ir.actions.act_window" &&
        ["kanban", "list"].includes(config.viewType) &&
        exprToBoolean(config.viewArch.getAttribute("create"), true),
};

cogMenuRegistry.add("knowledge-markdown-import-menu", importMarkdownItem, { sequence: 2 });
