import os
import subprocess
import unittest

from item_test_base import ServerTestCase, TEST_PORT, run_main


class InteractiveAddItemTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.make_user("owner")
        self.room_id = self.make_room(self.owner, "RoomA")

    def start_flow(self, client=None):
        client = client or self.owner
        self.assertEqual(client.cmd("ADD_ITEM"), "Room ID:")

    def test_01_full_interactive_flow(self):
        self.start_flow()
        self.assertEqual(self.owner.cmd(str(self.room_id)), "Item name:")
        self.assertEqual(self.owner.cmd("Laptop"), "Start price:")
        self.assertEqual(self.owner.cmd("1000000"), "Buy now price:")
        self.assertEqual(self.owner.cmd("5000000"), "OK ITEM_ADDED ID: 1")
        self.assertEqual(self.owner.list_items(self.room_id)[1],
                         "ITEM 1 Laptop START 1000000 BUYNOW 5000000 STATUS PENDING")

    def test_02_not_logged_in(self):
        guest = self.connect()
        self.assertEqual(guest.cmd("ADD_ITEM"), "ERROR Not logged in")
        self.assertEqual(guest.cmd("PING"), "OK PONG")

    def test_03_invalid_room_id_asks_again(self):
        self.start_flow()
        for bad in ["abc", "0", "-1", "1.5"]:
            self.assertEqual(self.owner.cmd(bad), "ERROR Invalid room ID", bad)
            self.assertEqual(self.owner.read_line(), "Room ID:")
        self.assertEqual(self.owner.cmd(str(self.room_id)), "Item name:")

    def test_04_room_not_found_asks_again(self):
        self.start_flow()
        self.assertEqual(self.owner.cmd("999"), "ERROR Room not found")
        self.assertEqual(self.owner.read_line(), "Room ID:")
        self.assertEqual(self.owner.cmd(str(self.room_id)), "Item name:")

    def test_05_not_room_owner_leaves_prompt_mode(self):
        other = self.make_user("other")
        self.assertEqual(other.cmd("ADD_ITEM"), "Room ID:")
        self.assertEqual(other.cmd(str(self.room_id)), "ERROR Not room owner")
        self.assertEqual(other.cmd("PING"), "OK PONG")
        self.assertEqual(self.item_lines(self.owner, self.room_id), [])

    def test_06_room_with_full_item_list_is_rejected_early(self):
        for number in range(20):
            self.add_item(self.owner, self.room_id, "I%d" % number)
        self.start_flow()
        self.assertEqual(self.owner.cmd(str(self.room_id)),
                         "ERROR Item limit reached (maximum 20 items per room)")
        self.assertEqual(self.owner.cmd("PING"), "OK PONG")

    def test_07_invalid_item_name_asks_again(self):
        self.start_flow()
        self.owner.cmd(str(self.room_id))
        self.assertEqual(self.owner.cmd("a" * 50),
                         "ERROR Item name must be 1-49 characters without whitespace")
        self.assertEqual(self.owner.read_line(), "Item name:")
        self.assertEqual(self.owner.cmd("two words"),
                         "ERROR Item name must be 1-49 characters without whitespace")
        self.assertEqual(self.owner.read_line(), "Item name:")
        self.assertEqual(self.owner.cmd(""),
                         "ERROR Item name must be 1-49 characters without whitespace")
        self.assertEqual(self.owner.read_line(), "Item name:")
        self.assertEqual(self.owner.cmd("a" * 49), "Start price:")

    def test_08_invalid_start_price_asks_again(self):
        self.start_flow()
        self.owner.cmd(str(self.room_id))
        self.owner.cmd("Laptop")
        for bad in ["abc", "0", "-1", "1.5", "1000000000001"]:
            self.assertEqual(self.owner.cmd(bad), "ERROR Invalid price", bad)
            self.assertEqual(self.owner.read_line(), "Start price:")
        self.assertEqual(self.owner.cmd("1000"), "Buy now price:")

    def test_09_invalid_buy_now_price_asks_again(self):
        self.start_flow()
        self.owner.cmd(str(self.room_id))
        self.owner.cmd("Laptop")
        self.owner.cmd("1000")
        for bad in ["abc", "0", "-1", "1.5"]:
            self.assertEqual(self.owner.cmd(bad), "ERROR Invalid price", bad)
            self.assertEqual(self.owner.read_line(), "Buy now price:")
        self.assertEqual(self.owner.cmd("2000"), "OK ITEM_ADDED ID: 1")

    def test_10_buy_now_not_greater_than_start_asks_again(self):
        self.start_flow()
        self.owner.cmd(str(self.room_id))
        self.owner.cmd("Laptop")
        self.owner.cmd("5000")
        for bad in ["5000", "4999"]:
            self.assertEqual(self.owner.cmd(bad),
                             "ERROR Buy-now price must be greater than start price")
            self.assertEqual(self.owner.read_line(), "Buy now price:")
        self.assertEqual(self.owner.cmd("5001"), "OK ITEM_ADDED ID: 1")
        self.assertEqual(self.owner.list_items(self.room_id)[1],
                         "ITEM 1 Laptop START 5000 BUYNOW 5001 STATUS PENDING")

    def test_11_lines_in_prompt_are_data_not_commands(self):
        self.start_flow()
        self.assertEqual(self.owner.cmd("PING"), "ERROR Invalid room ID")
        self.assertEqual(self.owner.read_line(), "Room ID:")
        self.assertEqual(self.owner.cmd(str(self.room_id)), "Item name:")
        self.assertEqual(self.owner.cmd("QUIT"), "Start price:")
        self.assertEqual(self.owner.cmd("LOGOUT"), "ERROR Invalid price")
        self.assertEqual(self.owner.read_line(), "Start price:")
        self.assertEqual(self.owner.cmd("1000"), "Buy now price:")
        self.assertEqual(self.owner.cmd("2000"), "OK ITEM_ADDED ID: 1")
        self.assertEqual(self.owner.list_items(self.room_id)[1],
                         "ITEM 1 QUIT START 1000 BUYNOW 2000 STATUS PENDING")
        self.assertEqual(self.owner.cmd("PING"), "OK PONG")

    def test_12_prompt_of_one_client_does_not_block_others(self):
        other = self.make_user("other")
        other_room = self.make_room(other, "RoomB")
        self.start_flow()
        self.owner.cmd(str(self.room_id))
        self.assertEqual(other.cmd("PING"), "OK PONG")
        self.assertEqual(other.cmd("ADD_ITEM %d Phone 1000 2000" % other_room), "OK ITEM_ADDED ID: 1")
        self.assertEqual(self.owner.cmd("Laptop"), "Start price:")
        self.assertEqual(self.owner.cmd("1000"), "Buy now price:")
        self.assertEqual(self.owner.cmd("2000"), "OK ITEM_ADDED ID: 2")

    def test_13_two_clients_in_prompt_at_the_same_time(self):
        other = self.make_user("other")
        other_room = self.make_room(other, "RoomB")
        self.start_flow()
        self.assertEqual(other.cmd("ADD_ITEM"), "Room ID:")
        self.assertEqual(self.owner.cmd(str(self.room_id)), "Item name:")
        self.assertEqual(other.cmd(str(other_room)), "Item name:")
        self.assertEqual(other.cmd("Phone"), "Start price:")
        self.assertEqual(self.owner.cmd("Laptop"), "Start price:")
        self.assertEqual(self.owner.cmd("1000"), "Buy now price:")
        self.assertEqual(other.cmd("3000"), "Buy now price:")
        self.assertEqual(other.cmd("4000"), "OK ITEM_ADDED ID: 1")
        self.assertEqual(self.owner.cmd("2000"), "OK ITEM_ADDED ID: 2")
        self.assertIn(" Laptop START 1000 BUYNOW 2000 ", self.item_lines(self.owner, self.room_id)[0])
        self.assertIn(" Phone START 3000 BUYNOW 4000 ", self.item_lines(other, other_room)[0])

    def test_14_whole_flow_in_one_send(self):
        self.owner.send_raw(("ADD_ITEM\n%d\nLaptop\n1000\n2000\nPING\n" % self.room_id).encode())
        self.assertEqual([self.owner.read_line() for _ in range(6)],
                         ["Room ID:", "Item name:", "Start price:", "Buy now price:",
                          "OK ITEM_ADDED ID: 1", "OK PONG"])

    def test_15_flow_split_across_several_sends(self):
        self.owner.send_raw(b"ADD_")
        self.owner.send_raw(b"ITEM\n")
        self.assertEqual(self.owner.read_line(), "Room ID:")
        self.owner.send_raw(("%d\nLap" % self.room_id).encode())
        self.assertEqual(self.owner.read_line(), "Item name:")
        self.owner.send_raw(b"top\n")
        self.assertEqual(self.owner.read_line(), "Start price:")

    def test_16_one_line_form_still_works_after_interactive_flow(self):
        self.start_flow()
        self.owner.cmd(str(self.room_id))
        self.owner.cmd("Laptop")
        self.owner.cmd("1000")
        self.assertEqual(self.owner.cmd("2000"), "OK ITEM_ADDED ID: 1")
        self.assertEqual(self.owner.cmd("ADD_ITEM %d Phone 1000 2000" % self.room_id), "OK ITEM_ADDED ID: 2")

    def test_17_add_item_with_two_to_four_arguments_is_still_invalid(self):
        for command in ["ADD_ITEM 1", "ADD_ITEM 1 Laptop", "ADD_ITEM 1 Laptop 1000"]:
            self.assertEqual(self.owner.cmd(command), "ERROR Invalid command or arguments", command)

    def test_18_disconnect_in_the_middle_of_flow(self):
        self.start_flow()
        self.owner.cmd(str(self.room_id))
        self.owner.cmd("Laptop")
        self.owner.close()
        again = self.connect()
        self.assertEqual(again.cmd("LOGIN owner %s" % self.password), "OK Login successful")
        self.assertEqual(again.cmd("PING"), "OK PONG")
        self.assertEqual(self.item_lines(again, self.room_id), [])
        self.assertEqual(again.cmd("ADD_ITEM"), "Room ID:")

    def test_19_flow_data_is_not_logged_as_commands(self):
        self.start_flow()
        self.owner.cmd(str(self.room_id))
        self.owner.cmd("Laptop")
        self.owner.cmd("1000")
        self.owner.cmd("2000")
        log = self.read_log()
        self.assertEqual(log.count("command=ADD_ITEM"), 1)
        self.assertNotIn("command=Laptop", log)
        self.assertNotIn("command=1000", log)
        self.assertEqual(log.count("ITEM_ADDED id=1"), 1)

    def test_20_interactive_item_can_be_auctioned(self):
        self.start_flow()
        self.owner.cmd(str(self.room_id))
        self.owner.cmd("Laptop")
        self.owner.cmd("1000")
        self.owner.cmd("2000")
        self.assertEqual(self.owner.cmd("START_AUCTION %d" % self.room_id),
                         "OK AUCTION_STARTED 1 Laptop START 1000 BUYNOW 2000")

    def test_21_other_input_flows_still_work(self):
        guest = self.connect()
        self.assertEqual(guest.cmd("REGISTER"), "New username:")
        self.assertEqual(guest.cmd("newuser"), "New password:")
        self.assertEqual(guest.cmd("secret1"), "OK Account registered")
        self.assertEqual(guest.cmd("LOGIN"), "Username:")
        self.assertEqual(guest.cmd("newuser"), "Password:")
        self.assertEqual(guest.cmd("secret1"), "OK Login successful")
        self.assertEqual(guest.cmd("CREATE_ROOM"), "Room name:")
        self.assertEqual(guest.cmd("RoomZ"), "OK ROOM_CREATED ID: 2")
        self.assertEqual(guest.cmd("JOIN_ROOM"), "Room ID:")
        self.assertEqual(guest.cmd("2"), "OK JOINED_ROOM RoomZ")

    def test_22_real_client_program_shows_prompts(self):
        client_path = os.path.join(self.build_dir, "client")
        script = ("REGISTER player1 secret1\nLOGIN player1 secret1\nCREATE_ROOM Shop\n"
                  "ADD_ITEM\n2\nBook\n1000\n3000\nLIST_ITEMS 2\n")
        result = subprocess.run([client_path, "127.0.0.1", str(TEST_PORT)], input=script,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ["Room ID: ", "Item name: ", "Start price: ", "Buy now price: ",
                         "OK ITEM_ADDED ID: 1",
                         "ITEM 1 Book START 1000 BUYNOW 3000 STATUS PENDING",
                         "END_ITEM_LIST"]:
            self.assertIn(expected, result.stdout)


if __name__ == "__main__":
    run_main()
