import unittest

from item_test_base import ServerTestCase, run_main


class StartAuctionTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.make_user("owner")
        self.room_id = self.make_room(self.owner, "RoomA")

    def join(self, client, room_id, room_name):
        self.assertEqual(client.cmd("JOIN_ROOM %d" % room_id), "OK JOINED_ROOM %s" % room_name)

    def statuses(self, client, room_id):
        result = {}
        for line in self.item_lines(client, room_id):
            parts = line.split()
            result[int(parts[1])] = parts[-1]
        return result

    def test_01_start_auction_uses_first_item(self):
        self.add_item(self.owner, self.room_id, "Laptop", 1000000, 5000000)
        self.add_item(self.owner, self.room_id, "Phone", 200000, 900000)
        self.assertEqual(self.owner.cmd("START_AUCTION %d" % self.room_id),
                         "OK AUCTION_STARTED 1 Laptop START 1000000 BUYNOW 5000000")
        self.assertEqual(self.statuses(self.owner, self.room_id),
                         {1: "AUCTIONING", 2: "PENDING"})

    def test_02_start_auction_not_logged_in(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        guest = self.connect()
        self.assertEqual(guest.cmd("START_AUCTION %d" % self.room_id), "ERROR Not logged in")
        self.assertEqual(self.statuses(self.owner, self.room_id), {1: "PENDING"})

    def test_03_start_auction_invalid_room_id(self):
        for bad in ["abc", "0", "-1", "1.5"]:
            self.assertEqual(self.owner.cmd("START_AUCTION %s" % bad), "ERROR Invalid room ID", bad)

    def test_04_start_auction_room_not_found(self):
        self.assertEqual(self.owner.cmd("START_AUCTION 999"), "ERROR Room not found")

    def test_05_start_auction_not_room_owner(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        other = self.make_user("other")
        self.assertEqual(other.cmd("START_AUCTION %d" % self.room_id), "ERROR Not room owner")
        self.assertEqual(self.statuses(self.owner, self.room_id), {1: "PENDING"})

    def test_06_member_who_is_not_owner_cannot_start(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        other = self.make_user("other")
        self.join(other, self.room_id, "RoomA")
        self.assertEqual(other.cmd("START_AUCTION %d" % self.room_id), "ERROR Not room owner")

    def test_07_start_auction_wrong_number_of_arguments(self):
        self.assertEqual(self.owner.cmd("START_AUCTION"), "ERROR Invalid command or arguments")
        self.assertEqual(self.owner.cmd("START_AUCTION 1 2"), "ERROR Invalid command or arguments")

    def test_08_start_auction_without_pending_items(self):
        self.assertEqual(self.owner.cmd("START_AUCTION %d" % self.room_id), "ERROR No pending items")

    def test_09_start_auction_twice_is_rejected(self):
        self.add_item(self.owner, self.room_id, "A")
        self.add_item(self.owner, self.room_id, "B")
        self.assertTrue(self.owner.cmd("START_AUCTION %d" % self.room_id).startswith("OK AUCTION_STARTED 1"))
        self.assertEqual(self.owner.cmd("START_AUCTION %d" % self.room_id), "ERROR Auction already running")
        self.assertEqual(self.statuses(self.owner, self.room_id), {1: "AUCTIONING", 2: "PENDING"})

    def test_10_first_item_is_lowest_item_id_after_removal(self):
        for name in ["A", "B", "C"]:
            self.add_item(self.owner, self.room_id, name)
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 1"), "OK ITEM_REMOVED ID: 1")
        self.assertEqual(self.owner.cmd("START_AUCTION %d" % self.room_id),
                         "OK AUCTION_STARTED 2 B START 100000 BUYNOW 500000")

    def test_11_items_added_during_auction_stay_pending(self):
        self.add_item(self.owner, self.room_id, "A")
        self.owner.cmd("START_AUCTION %d" % self.room_id)
        self.add_item(self.owner, self.room_id, "B")
        self.assertEqual(self.statuses(self.owner, self.room_id), {1: "AUCTIONING", 2: "PENDING"})

    def test_12_each_room_has_its_own_auction(self):
        room_b = self.make_room(self.owner, "RoomB")
        self.add_item(self.owner, self.room_id, "A")
        self.add_item(self.owner, room_b, "B")
        self.assertTrue(self.owner.cmd("START_AUCTION %d" % self.room_id).startswith("OK AUCTION_STARTED 1 A"))
        self.assertTrue(self.owner.cmd("START_AUCTION %d" % room_b).startswith("OK AUCTION_STARTED 2 B"))
        self.assertEqual(self.statuses(self.owner, self.room_id), {1: "AUCTIONING"})
        self.assertEqual(self.statuses(self.owner, room_b), {2: "AUCTIONING"})

    def test_13_start_auction_only_uses_items_of_that_room(self):
        room_b = self.make_room(self.owner, "RoomB")
        self.add_item(self.owner, room_b, "OnlyInB")
        self.assertEqual(self.owner.cmd("START_AUCTION %d" % self.room_id), "ERROR No pending items")

    def test_14_members_receive_item_started_event(self):
        self.add_item(self.owner, self.room_id, "Laptop", 1000000, 5000000)
        member1 = self.make_user("member1")
        member2 = self.make_user("member2")
        self.join(member1, self.room_id, "RoomA")
        self.join(member2, self.room_id, "RoomA")
        self.assertTrue(self.owner.cmd("START_AUCTION %d" % self.room_id).startswith("OK AUCTION_STARTED"))
        expected = "EVENT ITEM_STARTED 1 Laptop START 1000000 BUYNOW 5000000"
        self.assertEqual(member1.read_line(), expected)
        self.assertEqual(member2.read_line(), expected)

    def test_15_non_members_do_not_receive_event(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        room_b = self.make_room(self.owner, "RoomB")
        outsider = self.make_user("outsider")
        guest = self.connect()
        other_room_member = self.make_user("other_member")
        self.join(other_room_member, room_b, "RoomB")
        self.owner.cmd("START_AUCTION %d" % self.room_id)
        self.assertFalse(outsider.has_data())
        self.assertFalse(guest.has_data())
        self.assertFalse(other_room_member.has_data())

    def test_16_member_who_left_room_does_not_receive_event(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        member = self.make_user("member")
        self.join(member, self.room_id, "RoomA")
        self.assertEqual(member.cmd("LEAVE_ROOM"), "OK LEFT_ROOM")
        self.owner.cmd("START_AUCTION %d" % self.room_id)
        self.assertFalse(member.has_data())

    def test_17_owner_inside_room_gets_reply_only_once(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        self.join(self.owner, self.room_id, "RoomA")
        self.assertTrue(self.owner.cmd("START_AUCTION %d" % self.room_id).startswith("OK AUCTION_STARTED"))
        self.assertFalse(self.owner.has_data())

    def test_18_server_survives_member_disconnect_before_start(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        member = self.make_user("member")
        self.join(member, self.room_id, "RoomA")
        member.close()
        self.assertTrue(self.owner.cmd("START_AUCTION %d" % self.room_id).startswith("OK AUCTION_STARTED"))
        self.assertEqual(self.owner.cmd("PING"), "OK PONG")

    def test_19_remove_item_being_auctioned_is_rejected(self):
        self.add_item(self.owner, self.room_id, "A")
        self.add_item(self.owner, self.room_id, "B")
        self.owner.cmd("START_AUCTION %d" % self.room_id)
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 1"), "ERROR Item already put up for auction")
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 2"), "OK ITEM_REMOVED ID: 2")
        self.assertEqual(self.statuses(self.owner, self.room_id), {1: "AUCTIONING"})

    def test_20_start_auction_is_written_to_log(self):
        self.add_item(self.owner, self.room_id, "Laptop")
        other = self.make_user("other")
        other.cmd("START_AUCTION %d" % self.room_id)
        self.owner.cmd("START_AUCTION %d" % self.room_id)
        log = self.read_log()
        self.assertIn("AUCTION_ITEM_STARTED room_id=%d item_id=1 name=Laptop" % self.room_id, log)
        self.assertEqual(log.count("AUCTION_ITEM_STARTED"), 1)

    def test_21_help_lists_start_auction(self):
        self.assertIn("START_AUCTION", self.owner.cmd("HELP"))

    def test_22_owner_reconnect_keeps_auction_running(self):
        self.add_item(self.owner, self.room_id, "A")
        self.owner.cmd("START_AUCTION %d" % self.room_id)
        self.assertEqual(self.owner.cmd("LOGOUT"), "OK Logout successful")
        self.assertEqual(self.owner.cmd("LOGIN owner %s" % self.password), "OK Login successful")
        self.assertEqual(self.owner.cmd("START_AUCTION %d" % self.room_id), "ERROR Auction already running")

    def test_23_start_auction_two_commands_in_one_send(self):
        self.add_item(self.owner, self.room_id, "A")
        self.owner.send_raw(("START_AUCTION %d\nSTART_AUCTION %d\n" % (self.room_id, self.room_id)).encode())
        self.assertTrue(self.owner.read_line().startswith("OK AUCTION_STARTED 1 A"))
        self.assertEqual(self.owner.read_line(), "ERROR Auction already running")


if __name__ == "__main__":
    run_main()
