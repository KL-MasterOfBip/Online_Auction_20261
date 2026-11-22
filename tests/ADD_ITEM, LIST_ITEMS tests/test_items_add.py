import unittest

from item_test_base import ServerTestCase, run_main


class AddItemTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.make_user("owner")
        self.room_id = self.make_room(self.owner, "RoomA")

    def test_01_add_item_valid(self):
        self.assertEqual(self.owner.cmd("ADD_ITEM %d Laptop 1000000 5000000" % self.room_id),
                         "OK ITEM_ADDED ID: 1")
        self.assertEqual(self.owner.cmd("ADD_ITEM %d Phone 200000 900000" % self.room_id),
                         "OK ITEM_ADDED ID: 2")

    def test_02_list_items_shows_added_items_with_pending_status(self):
        self.add_item(self.owner, self.room_id, "Laptop", 1000000, 5000000)
        self.add_item(self.owner, self.room_id, "Phone", 200000, 900000)
        lines = self.owner.list_items(self.room_id)
        self.assertEqual(lines, [
            "OK ITEM_LIST",
            "ITEM 1 Laptop START 1000000 BUYNOW 5000000 STATUS PENDING",
            "ITEM 2 Phone START 200000 BUYNOW 900000 STATUS PENDING",
            "END_ITEM_LIST",
        ])

    def test_03_list_items_empty_room(self):
        self.assertEqual(self.owner.list_items(self.room_id),
                         ["OK ITEM_LIST", "NO_ITEMS", "END_ITEM_LIST"])

    def test_04_add_item_not_logged_in(self):
        guest = self.connect()
        self.assertEqual(guest.cmd("ADD_ITEM %d Laptop 1000 2000" % self.room_id),
                         "ERROR Not logged in")

    def test_05_add_item_after_logout(self):
        self.assertEqual(self.owner.cmd("LOGOUT"), "OK Logout successful")
        self.assertEqual(self.owner.cmd("ADD_ITEM %d Laptop 1000 2000" % self.room_id),
                         "ERROR Not logged in")

    def test_06_add_item_room_not_found(self):
        self.assertEqual(self.owner.cmd("ADD_ITEM 999 Laptop 1000 2000"),
                         "ERROR Room not found")

    def test_07_add_item_not_room_owner(self):
        other = self.make_user("other")
        self.assertEqual(other.cmd("ADD_ITEM %d Laptop 1000 2000" % self.room_id),
                         "ERROR Not room owner")
        self.assertEqual(self.item_lines(self.owner, self.room_id), [])

    def test_08_member_who_is_not_owner_cannot_add(self):
        other = self.make_user("other")
        self.assertEqual(other.cmd("JOIN_ROOM %d" % self.room_id), "OK JOINED_ROOM RoomA")
        self.assertEqual(other.cmd("ADD_ITEM %d Laptop 1000 2000" % self.room_id),
                         "ERROR Not room owner")

    def test_09_owner_does_not_need_to_join_room(self):
        self.assertEqual(self.owner.cmd("ADD_ITEM %d Laptop 1000 2000" % self.room_id),
                         "OK ITEM_ADDED ID: 1")

    def test_10_owner_of_another_room_cannot_add(self):
        other = self.make_user("other")
        other_room = self.make_room(other, "RoomB")
        self.assertEqual(other.cmd("ADD_ITEM %d Laptop 1000 2000" % self.room_id),
                         "ERROR Not room owner")
        self.assertEqual(other.cmd("ADD_ITEM %d Laptop 1000 2000" % other_room),
                         "OK ITEM_ADDED ID: 1")

    def test_11_invalid_room_id(self):
        for bad in ["abc", "0", "-1", "1.5", "99999999999"]:
            self.assertEqual(self.owner.cmd("ADD_ITEM %s Laptop 1000 2000" % bad),
                             "ERROR Invalid room ID", bad)

    def test_12_invalid_price(self):
        bad_prices = ["abc", "0", "-5", "1.5", "+5", "1e5", "0x10", "1000000000001",
                      "99999999999999999999"]
        for bad in bad_prices:
            self.assertEqual(self.owner.cmd("ADD_ITEM %d Laptop %s 2000000000000" % (self.room_id, bad)),
                             "ERROR Invalid price", "start=" + bad)
            self.assertEqual(self.owner.cmd("ADD_ITEM %d Laptop 1000 %s" % (self.room_id, bad)),
                             "ERROR Invalid price", "buy_now=" + bad)
        self.assertEqual(self.item_lines(self.owner, self.room_id), [])

    def test_13_buy_now_must_be_greater_than_start_price(self):
        message = "ERROR Buy-now price must be greater than start price"
        self.assertEqual(self.owner.cmd("ADD_ITEM %d Laptop 5000 5000" % self.room_id), message)
        self.assertEqual(self.owner.cmd("ADD_ITEM %d Laptop 5000 4000" % self.room_id), message)
        self.assertEqual(self.owner.cmd("ADD_ITEM %d Laptop 5000 5001" % self.room_id),
                         "OK ITEM_ADDED ID: 1")

    def test_14_price_boundaries(self):
        self.assertEqual(self.owner.cmd("ADD_ITEM %d Min 1 2" % self.room_id),
                         "OK ITEM_ADDED ID: 1")
        self.assertEqual(self.owner.cmd("ADD_ITEM %d Max 999999999999 1000000000000" % self.room_id),
                         "OK ITEM_ADDED ID: 2")

    def test_15_item_name_length(self):
        self.assertEqual(self.owner.cmd("ADD_ITEM %d %s 1000 2000" % (self.room_id, "a" * 49)),
                         "OK ITEM_ADDED ID: 1")
        self.assertEqual(self.owner.cmd("ADD_ITEM %d %s 1000 2000" % (self.room_id, "a" * 50)),
                         "ERROR Item name is too long")
        lines = self.item_lines(self.owner, self.room_id)
        self.assertEqual(lines, ["ITEM 1 %s START 1000 BUYNOW 2000 STATUS PENDING" % ("a" * 49)])

    def test_16_wrong_number_of_arguments(self):
        for command in ["ADD_ITEM", "ADD_ITEM 1", "ADD_ITEM 1 Laptop", "ADD_ITEM 1 Laptop 1000",
                        "ADD_ITEM 1 Laptop 1000 2000 extra", "ADD_ITEM 1 a b c d e f"]:
            self.assertEqual(self.owner.cmd(command), "ERROR Invalid command or arguments", command)
        self.assertEqual(self.owner.cmd("LIST_ITEMS"), "ERROR Invalid command or arguments")
        self.assertEqual(self.owner.cmd("LIST_ITEMS 1 2"), "ERROR Invalid command or arguments")

    def test_17_items_are_separated_by_room(self):
        room_b = self.make_room(self.owner, "RoomB")
        self.add_item(self.owner, self.room_id, "Laptop")
        self.add_item(self.owner, room_b, "Phone")
        self.assertEqual(len(self.item_lines(self.owner, self.room_id)), 1)
        self.assertIn(" Laptop ", self.item_lines(self.owner, self.room_id)[0])
        self.assertEqual(len(self.item_lines(self.owner, room_b)), 1)
        self.assertIn(" Phone ", self.item_lines(self.owner, room_b)[0])

    def test_18_item_limit_per_room(self):
        for number in range(20):
            self.add_item(self.owner, self.room_id, "Item%d" % number)
        self.assertEqual(self.owner.cmd("ADD_ITEM %d Extra 1000 2000" % self.room_id),
                         "ERROR Item limit reached (maximum 20 items per room)")
        room_b = self.make_room(self.owner, "RoomB")
        self.assertEqual(self.owner.cmd("ADD_ITEM %d Extra 1000 2000" % room_b),
                         "OK ITEM_ADDED ID: 21")

    def test_19_item_database_full(self):
        users = [self.owner, self.make_user("user2"), self.make_user("user3")]
        rooms = [(users[0], self.room_id)]
        for index in range(9):
            rooms.append((users[0], self.make_room(users[0], "A%d" % index)))
        for index in range(10):
            rooms.append((users[1], self.make_room(users[1], "B%d" % index)))
        for index in range(5):
            rooms.append((users[2], self.make_room(users[2], "C%d" % index)))
        for client, room_id in rooms:
            for number in range(20):
                self.assertTrue(client.cmd("ADD_ITEM %d I%d 1000 2000" % (room_id, number))
                                .startswith("OK ITEM_ADDED"))
        spare_room = self.make_room(users[2], "SpareRoom")
        self.assertEqual(users[2].cmd("ADD_ITEM %d Extra 1000 2000" % spare_room),
                         "ERROR Item database is full")

    def test_20_list_items_requires_login(self):
        guest = self.connect()
        self.assertEqual(guest.cmd("LIST_ITEMS %d" % self.room_id), "ERROR Not logged in")

    def test_21_list_items_invalid_or_missing_room(self):
        self.assertEqual(self.owner.cmd("LIST_ITEMS abc"), "ERROR Invalid room ID")
        self.assertEqual(self.owner.cmd("LIST_ITEMS -3"), "ERROR Invalid room ID")
        self.assertEqual(self.owner.cmd("LIST_ITEMS 999"), "ERROR Room not found")

    def test_22_other_logged_in_user_can_list_items(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        other = self.make_user("other")
        self.assertEqual(len(self.item_lines(other, self.room_id)), 1)

    def test_23_items_persist_after_owner_logout_and_login(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        self.assertEqual(self.owner.cmd("LOGOUT"), "OK Logout successful")
        self.assertEqual(self.owner.cmd("LOGIN owner %s" % self.password), "OK Login successful")
        self.assertEqual(len(self.item_lines(self.owner, self.room_id)), 1)

    def test_24_multiple_commands_in_one_send(self):
        self.owner.send_raw(("ADD_ITEM %d A 1000 2000\nADD_ITEM %d B 1000 2000\nLIST_ITEMS %d\n"
                             % (self.room_id, self.room_id, self.room_id)).encode())
        self.assertEqual(self.owner.read_line(), "OK ITEM_ADDED ID: 1")
        self.assertEqual(self.owner.read_line(), "OK ITEM_ADDED ID: 2")
        lines = self.owner.read_until("END_ITEM_LIST")
        self.assertEqual(len(lines), 4)

    def test_25_command_split_across_several_sends(self):
        self.owner.send_raw(("ADD_ITEM %d Lap" % self.room_id).encode())
        self.assertFalse(self.owner.has_data(0.2))
        self.owner.send_raw(b"top 1000 ")
        self.owner.send_raw(b"2000\n")
        self.assertEqual(self.owner.read_line(), "OK ITEM_ADDED ID: 1")

    def test_26_item_added_is_written_to_log(self):
        self.add_item(self.owner, self.room_id, "Laptop", 1000, 2000)
        self.owner.cmd("ADD_ITEM %d Bad 5000 4000" % self.room_id)
        log = self.read_log()
        self.assertIn("ITEM_ADDED id=1 room_id=%d name=Laptop owner=owner start=1000 buy_now=2000"
                      % self.room_id, log)
        self.assertEqual(log.count("ITEM_ADDED"), 1)

    def test_27_help_lists_item_commands(self):
        response = self.owner.cmd("HELP")
        self.assertTrue(response.startswith("OK Commands:"))
        for command in ["ADD_ITEM", "LIST_ITEMS"]:
            self.assertIn(command, response)

    def test_28_existing_features_still_work(self):
        self.assertEqual(self.owner.cmd("PING"), "OK PONG")
        self.assertEqual(self.owner.cmd("FOO"), "ERROR Unknown command: FOO")
        self.assertEqual(self.owner.cmd(""), "ERROR Empty command")
        other = self.make_user("other")
        self.assertEqual(other.cmd("JOIN_ROOM %d" % self.room_id), "OK JOINED_ROOM RoomA")
        self.assertEqual(other.cmd("LEAVE_ROOM"), "OK LEFT_ROOM")
        self.assertEqual(other.cmd("LOGIN other %s" % self.password), "ERROR Already logged in")
        lines = self.owner.cmd("LIST_ROOMS")
        self.assertEqual(lines, "OK ROOM_LIST")


if __name__ == "__main__":
    run_main()
