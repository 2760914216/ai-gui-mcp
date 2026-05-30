from src.providers.gdino.label_mapper import GdinoLabelMapper
from src.providers.qwen_vl.descriptor import ALL_TYPES, constrain_by_category


class TestGdinoLabelMapper:
    def test_button_label_maps_to_interactive(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("button") == "interactive"
        assert mapper.map("Button") == "interactive"

    def test_text_label_maps_to_interactive(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("text label") == "interactive"
        assert mapper.map("text field") == "interactive"
        assert mapper.map("text input") == "interactive"

    def test_input_label_maps_to_interactive(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("input field") == "interactive"

    def test_checkbox_label_maps_to_interactive(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("checkbox") == "interactive"
        assert mapper.map("check box") == "interactive"

    def test_radio_label_maps_to_interactive(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("radio button") == "interactive"

    def test_link_label_maps_to_interactive(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("link") == "interactive"

    def test_tab_label_maps_to_interactive(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("tab") == "interactive"

    def test_menu_item_label_maps_to_interactive(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("menu item") == "interactive"

    def test_window_label_maps_to_structural(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("window") == "structural"

    def test_dialog_label_maps_to_structural(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("dialog") == "structural"

    def test_sidebar_label_maps_to_structural(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("sidebar") == "structural"

    def test_toolbar_label_maps_to_structural(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("toolbar") == "structural"

    def test_panel_label_maps_to_structural(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("panel") == "structural"

    def test_list_label_maps_to_structural(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("list") == "structural"

    def test_table_label_maps_to_structural(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("table") == "structural"

    def test_form_label_maps_to_structural(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("form") == "structural"

    def test_menu_label_maps_to_structural(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("menu") == "structural"

    def test_unknown_label_degrades_to_unknown(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("thumbnail") == "unknown"
        assert mapper.map("icon") == "unknown"
        assert mapper.map("image") == "unknown"
        assert mapper.map("scrollbar") == "unknown"
        assert mapper.map("") == "unknown"

    def test_none_label_degrades_to_unknown(self):
        mapper = GdinoLabelMapper()
        assert mapper.map(None) == "unknown"

    def test_case_insensitive(self):
        mapper = GdinoLabelMapper()
        assert mapper.map("BUTTON") == "interactive"
        assert mapper.map("WiNdOw") == "structural"

    def test_known_labels_coverage(self):
        mapper = GdinoLabelMapper()
        expected = {
            "button",
            "text",
            "input",
            "check",
            "radio",
            "link",
            "menu item",
            "tab",
            "window",
            "menu",
            "sidebar",
            "toolbar",
            "panel",
            "list",
            "table",
            "dialog",
            "form",
        }
        assert mapper.KNOWN_LABELS == expected


class TestQwenTypeMapper:
    def test_interactive_types(self):
        types = constrain_by_category("interactive")
        assert len(types) == 7
        assert types == [
            "button",
            "input",
            "checkbox",
            "radio",
            "tab",
            "menuitem",
            "link",
        ]

    def test_structural_types(self):
        types = constrain_by_category("structural")
        assert len(types) == 8
        assert types == [
            "window",
            "dialog",
            "sidebar",
            "toolbar",
            "panel",
            "list",
            "table",
            "form",
        ]

    def test_unknown_types(self):
        types = constrain_by_category("unknown")
        assert len(types) == 17
        assert types == ALL_TYPES

    def test_arbitrary_string_falls_back_to_all(self):
        types = constrain_by_category("garbage")
        assert len(types) == 17
        assert types == ALL_TYPES

    def test_all_types_count(self):
        assert len(ALL_TYPES) == 17
