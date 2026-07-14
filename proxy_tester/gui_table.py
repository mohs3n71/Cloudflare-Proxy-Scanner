from .gui_utils import table_sort_value
from .gui_qr import open_config_qr
from .proxy_config import make_proxy_url


class TableMixin:
    def open_table_context_menu(self, event):
        item = self.table.identify_row(event.y)
        if item and item not in self.table.selection():
            self.table.selection_set(item)
        if not self.table.selection():
            return
        single = len(self.table.selection()) == 1
        config_state = "normal" if self.profile is not None else "disabled"
        for index in (
            self.table_menu_speed_download_index,
            self.table_menu_speed_upload_index,
            self.table_menu_speed_both_index,
        ):
            self.table_menu.entryconfigure(index, state=config_state)
        self.table_menu.entryconfigure(
            self.table_menu_run_xray_index,
            state="normal" if single and self.profile is not None else "disabled",
        )
        self.table_menu.entryconfigure(self.table_menu_copy_ip_index, state="normal" if single else "disabled")
        self.table_menu.entryconfigure(
            self.table_menu_copy_config_index,
            state="normal" if single and self.profile is not None else "disabled",
        )
        self.table_menu.entryconfigure(
            self.table_menu_qr_config_index,
            state="normal" if single and self.profile is not None else "disabled",
        )
        try:
            self.table_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.table_menu.grab_release()

    def _selected_table_ips(self):
        ips = []
        seen = set()
        for item in self.table.selection():
            values = self.table.item(item, "values")
            if len(values) < 2:
                continue
            ip = str(values[1]).strip()
            if ip and ip not in seen:
                ips.append(ip)
                seen.add(ip)
        return ips

    def _selected_single_ip(self):
        ips = self._selected_table_ips()
        return ips[0] if len(ips) == 1 else None

    def _restore_table_selection_by_ips(self, ips):
        items = []
        for ip in ips:
            item = self.table_items_by_ip.get(ip)
            if item:
                items.append(item)
        if not items:
            return
        self.table.selection_set(items)
        if len(items) == 1:
            self.table.focus(items[0])
            self.table.see(items[0])

    def copy_selected_ip(self):
        ip = self._selected_single_ip()
        if not ip:
            return
        self.clipboard_clear()
        self.clipboard_append(ip)

    def copy_selected_config(self):
        ip = self._selected_single_ip()
        if not ip:
            return
        profile = self._selected_profile()
        if profile is None:
            return
        self.clipboard_clear()
        self.clipboard_append(make_proxy_url(ip, f"cf-{ip}", profile))

    def show_selected_config_qr(self):
        ip = self._selected_single_ip()
        if not ip:
            return
        profile = self._selected_profile()
        if profile is None:
            return
        config_url = make_proxy_url(ip, f"cf-{ip}", profile)
        open_config_qr(self, config_url, profile.protocol, ip)

    def _upsert_table_result(self, result):
        ip = result.get("ip", "")
        merged = dict(result)
        previous = None
        remaining = []
        for row in self.passed_results:
            if row.get("ip") == ip:
                previous = row
                merged = {**row, **result}
            else:
                remaining.append(row)
        remaining.append(merged)
        self.passed_results = remaining
        self._upsert_table_row(merged, previous)

    def _set_ip_active(self, ip, active):
        if active:
            self.active_test_ips.add(ip)
        else:
            self.active_test_ips.discard(ip)
        changed = False
        for result in self.passed_results:
            if result.get("ip") == ip:
                result["active"] = active
                self._update_table_row_tags(ip, result)
                changed = True
                break
        if not changed:
            return

    def _refresh_passed_table(self):
        for item in self.table.get_children():
            self.table.delete(item)
        self.table_items_by_ip = {}
        for result in self._sorted_results():
            item = self.table.insert(
                "",
                "end",
                values=self._table_values(result),
                tags=self._table_tags(result),
            )
            self.table_items_by_ip[result["ip"]] = item

    def _table_values(self, result):
        return (
            result["ms"],
            result["ip"],
            result.get("download_mbps", ""),
            result.get("upload_mbps", ""),
        )

    def _table_tags(self, result):
        return ("active",) if result.get("active") else ()

    def _upsert_table_row(self, result, previous=None):
        ip = result.get("ip", "")
        item = self.table_items_by_ip.get(ip)
        if not item:
            item = self.table.insert("", "end", values=self._table_values(result), tags=self._table_tags(result))
            self.table_items_by_ip[ip] = item
        else:
            self.table.item(item, values=self._table_values(result), tags=self._table_tags(result))

        if previous is None or self._sort_value(previous) != self._sort_value(result):
            self._move_table_item_to_sorted_position(item, result)

    def _update_table_row_tags(self, ip, result):
        item = self.table_items_by_ip.get(ip)
        if item:
            self.table.item(item, tags=self._table_tags(result))

    def _move_table_item_to_sorted_position(self, item, result):
        sorted_results = self._sorted_results()
        target_index = next(
            (index for index, row in enumerate(sorted_results) if row.get("ip") == result.get("ip")),
            len(sorted_results) - 1,
        )
        self.table.move(item, "", target_index)

    def _sort_by_column(self, column):
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
        self._refresh_passed_table()

    def _sorted_results(self):
        return sorted(self.passed_results, key=self._sort_value, reverse=self.sort_reverse)

    def _sort_value(self, result):
        return table_sort_value(result, self.sort_column)


