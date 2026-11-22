import unittest

from item_test_base import ServerTestCase, run_main


class RemoveItemTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.make_user("owner")
        self.room_id = self.make_room(self.owner, "RoomA")

    def ids_in_room(self, client, room_id):
        return [int(line.split()[1]) for line in self.item_lines(client, room_id)]

    def test_01_remove_pending_item(self):
        item_id = self.add_item(self.owner, self.room_id, "Laptop")
        self.assertEqual(self.owner.cmd("REMOVE_ITEM %d" % item_id), "OK ITEM_REMOVED ID: 1")
        self.assertEqual(self.owner.list_items(self.room_id),
                         ["OK ITEM_LIST", "NO_ITEMS", "END_ITEM_LIST"])

    def test_02_remove_one_of_several_items(self):
        for name in ["A", "B", "C"]:
            self.add_item(self.owner, self.room_id, name)
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 2"), "OK ITEM_REMOVED ID: 2")
        lines = self.item_lines(self.owner, self.room_id)
        self.assertEqual(len(lines), 2)
        self.assertIn(" A ", lines[0])
        self.assertIn(" C ", lines[1])

    def test_03_remove_not_logged_in(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        guest = self.connect()
        self.assertEqual(guest.cmd("REMOVE_ITEM 1"), "ERROR Not logged in")
        self.assertEqual(len(self.item_lines(self.owner, self.room_id)), 1)

    def test_04_remove_item_not_found(self):
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 999"), "ERROR Item not found")

    def test_05_remove_item_twice(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 1"), "OK ITEM_REMOVED ID: 1")
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 1"), "ERROR Item not found")

    def test_06_remove_invalid_item_id(self):
        for bad in ["abc", "0", "-1", "1.5", "99999999999"]:
            self.assertEqual(self.owner.cmd("REMOVE_ITEM %s" % bad), "ERROR Invalid item ID", bad)

    def test_07_remove_wrong_number_of_arguments(self):
        self.assertEqual(self.owner.cmd("REMOVE_ITEM"), "ERROR Invalid command or arguments")
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 1 2"), "ERROR Invalid command or arguments")

    def test_08_non_owner_cannot_remove(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        other = self.make_user("other")
        self.assertEqual(other.cmd("REMOVE_ITEM 1"), "ERROR Not room owner")
        self.assertEqual(len(self.item_lines(self.owner, self.room_id)), 1)

    def test_09_member_who_is_not_owner_cannot_remove(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        other = self.make_user("other")
        self.assertEqual(other.cmd("JOIN_ROOM %d" % self.room_id), "OK JOINED_ROOM RoomA")
        self.assertEqual(other.cmd("REMOVE_ITEM 1"), "ERROR Not room owner")

    def test_10_owner_of_another_room_cannot_remove(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        other = self.make_user("other")
        self.make_room(other, "RoomB")
        self.assertEqual(other.cmd("REMOVE_ITEM 1"), "ERROR Not room owner")

    def test_11_owner_can_remove_without_joining_room(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 1"), "OK ITEM_REMOVED ID: 1")

    def test_12_item_ids_are_not_reused(self):
        self.add_item(self.owner, self.room_id, "A")
        self.add_item(self.owner, self.room_id, "B")
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 1"), "OK ITEM_REMOVED ID: 1")
        self.assertEqual(self.owner.cmd("ADD_ITEM %d C 1000 2000" % self.room_id),
                         "OK ITEM_ADDED ID: 3")

    def test_13_list_stays_ordered_by_item_id_after_slot_reuse(self):
        for name in ["A", "B", "C"]:
            self.add_item(self.owner, self.room_id, name)
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 2"), "OK ITEM_REMOVED ID: 2")
        self.add_item(self.owner, self.room_id, "D")
        self.assertEqual(self.ids_in_room(self.owner, self.room_id), [1, 3, 4])

    def test_14_removing_frees_room_item_limit(self):
        for number in range(20):
            self.add_item(self.owner, self.room_id, "I%d" % number)
        self.assertEqual(self.owner.cmd("ADD_ITEM %d X 1000 2000" % self.room_id),
                         "ERROR Item limit reached (maximum 20 items per room)")
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 5"), "OK ITEM_REMOVED ID: 5")
        self.assertEqual(self.owner.cmd("ADD_ITEM %d X 1000 2000" % self.room_id),
                         "OK ITEM_ADDED ID: 21")

    def test_15_removed_item_disappears_for_other_users(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        other = self.make_user("other")
        self.assertEqual(len(self.item_lines(other, self.room_id)), 1)
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 1"), "OK ITEM_REMOVED ID: 1")
        self.assertEqual(self.item_lines(other, self.room_id), [])

    def test_16_remove_only_affects_selected_item_in_its_room(self):
        room_b = self.make_room(self.owner, "RoomB")
        self.add_item(self.owner, self.room_id, "A")
        self.add_item(self.owner, room_b, "B")
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 1"), "OK ITEM_REMOVED ID: 1")
        self.assertEqual(self.ids_in_room(self.owner, self.room_id), [])
        self.assertEqual(self.ids_in_room(self.owner, room_b), [2])

    def test_17_remove_after_logout(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        self.assertEqual(self.owner.cmd("LOGOUT"), "OK Logout successful")
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 1"), "ERROR Not logged in")

    def test_18_remove_is_written_to_log(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        other = self.make_user("other")
        other.cmd("REMOVE_ITEM 1")
        self.owner.cmd("REMOVE_ITEM 1")
        log = self.read_log()
        self.assertIn("ITEM_REMOVED id=1 room_id=%d name=Laptop owner=owner" % self.room_id, log)
        self.assertEqual(log.count("ITEM_REMOVED"), 1)

    def test_19_help_lists_remove_item(self):
        self.assertIn("REMOVE_ITEM", self.owner.cmd("HELP"))

    def test_20_remove_multiple_commands_in_one_send(self):
        for name in ["A", "B", "C"]:
            self.add_item(self.owner, self.room_id, name)
        self.owner.send_raw(b"REMOVE_ITEM 1\nREMOVE_ITEM 3\nREMOVE_ITEM 1\n")
        self.assertEqual(self.owner.read_line(), "OK ITEM_REMOVED ID: 1")
        self.assertEqual(self.owner.read_line(), "OK ITEM_REMOVED ID: 3")
        self.assertEqual(self.owner.read_line(), "ERROR Item not found")
        self.assertEqual(self.ids_in_room(self.owner, self.room_id), [2])


if __name__ == "__main__":
    run_main()
