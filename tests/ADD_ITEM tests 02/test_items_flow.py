import unittest

from item_test_base import ServerTestCase, run_main


class ItemFlowTests(ServerTestCase):
    def join(self, client, room_id, room_name):
        self.assertEqual(client.cmd("JOIN_ROOM %d" % room_id), "OK JOINED_ROOM %s" % room_name)

    def test_01_full_auction_scenario(self):
        owner = self.make_user("seller")
        buyer1 = self.make_user("buyer1")
        buyer2 = self.make_user("buyer2")
        room_id = self.make_room(owner, "Shop")
        self.join(buyer1, room_id, "Shop")
        self.join(buyer2, room_id, "Shop")

        self.assertEqual(owner.cmd("ADD_ITEM"), "Room ID:")
        owner.cmd(str(room_id))
        owner.cmd("Laptop")
        owner.cmd("1000000")
        self.assertEqual(owner.cmd("5000000"), "OK ITEM_ADDED ID: 1")
        self.assertEqual(owner.cmd("ADD_ITEM %d Phone 200000 900000" % room_id), "OK ITEM_ADDED ID: 2")
        self.assertEqual(owner.cmd("ADD_ITEM %d Watch 300000 700000" % room_id), "OK ITEM_ADDED ID: 3")
        self.assertEqual(owner.cmd("REMOVE_ITEM 2"), "OK ITEM_REMOVED ID: 2")

        self.assertEqual(buyer1.list_items(room_id), [
            "OK ITEM_LIST",
            "ITEM 1 Laptop START 1000000 BUYNOW 5000000 STATUS PENDING",
            "ITEM 3 Watch START 300000 BUYNOW 700000 STATUS PENDING",
            "END_ITEM_LIST",
        ])
        self.assertEqual(buyer1.cmd("REMOVE_ITEM 1"), "ERROR Not room owner")
        self.assertEqual(buyer1.cmd("START_AUCTION %d" % room_id), "ERROR Not room owner")
        self.assertEqual(buyer1.cmd("NEXT_ITEM %d" % room_id), "ERROR Not room owner")

        self.assertEqual(owner.cmd("START_AUCTION %d" % room_id),
                         "OK AUCTION_STARTED 1 Laptop START 1000000 BUYNOW 5000000")
        for buyer in (buyer1, buyer2):
            self.assertEqual(buyer.read_line(), "EVENT ITEM_STARTED 1 Laptop START 1000000 BUYNOW 5000000")
        self.assertEqual(owner.cmd("REMOVE_ITEM 1"), "ERROR Item already put up for auction")

        owner.send("NEXT_ITEM %d" % room_id)
        self.assertEqual(owner.read_line(), "OK ITEM_ENDED 1 Laptop")
        self.assertEqual(owner.read_line(), "OK ITEM_STARTED 3 Watch START 300000 BUYNOW 700000")
        for buyer in (buyer1, buyer2):
            self.assertEqual(buyer.read_line(), "EVENT ITEM_ENDED 1 Laptop NO_SALE")
            self.assertEqual(buyer.read_line(), "EVENT ITEM_STARTED 3 Watch START 300000 BUYNOW 700000")

        owner.send("NEXT_ITEM %d" % room_id)
        self.assertEqual(owner.read_line(), "OK ITEM_ENDED 3 Watch")
        self.assertEqual(owner.read_line(), "OK AUCTION_FINISHED")
        for buyer in (buyer1, buyer2):
            self.assertEqual(buyer.read_line(), "EVENT ITEM_ENDED 3 Watch NO_SALE")
            self.assertEqual(buyer.read_line(), "EVENT AUCTION_FINISHED")

        self.assertEqual(buyer2.list_items(room_id), [
            "OK ITEM_LIST",
            "ITEM 1 Laptop START 1000000 BUYNOW 5000000 STATUS ENDED",
            "ITEM 3 Watch START 300000 BUYNOW 700000 STATUS ENDED",
            "END_ITEM_LIST",
        ])

    def test_02_many_members_all_receive_events(self):
        owner = self.make_user("seller")
        room_id = self.make_room(owner, "Big")
        owner.cmd("ADD_ITEM %d A 1000 2000" % room_id)
        owner.cmd("ADD_ITEM %d B 1000 2000" % room_id)
        members = []
        for number in range(30):
            member = self.make_user("member%d" % number)
            self.join(member, room_id, "Big")
            members.append(member)
        self.assertTrue(owner.cmd("START_AUCTION %d" % room_id).startswith("OK AUCTION_STARTED 1 A"))
        owner.send("NEXT_ITEM %d" % room_id)
        owner.read_line()
        owner.read_line()
        for member in members:
            self.assertEqual(member.read_line(), "EVENT ITEM_STARTED 1 A START 1000 BUYNOW 2000")
            self.assertEqual(member.read_line(), "EVENT ITEM_ENDED 1 A NO_SALE")
            self.assertEqual(member.read_line(), "EVENT ITEM_STARTED 2 B START 1000 BUYNOW 2000")

    def test_03_members_leaving_mid_auction_stop_receiving_events(self):
        owner = self.make_user("seller")
        stay = self.make_user("stay")
        leave = self.make_user("leave")
        room_id = self.make_room(owner, "Shop")
        owner.cmd("ADD_ITEM %d A 1000 2000" % room_id)
        owner.cmd("ADD_ITEM %d B 1000 2000" % room_id)
        self.join(stay, room_id, "Shop")
        self.join(leave, room_id, "Shop")
        owner.cmd("START_AUCTION %d" % room_id)
        self.assertTrue(stay.read_line().startswith("EVENT ITEM_STARTED 1"))
        self.assertTrue(leave.read_line().startswith("EVENT ITEM_STARTED 1"))
        self.assertEqual(leave.cmd("LEAVE_ROOM"), "OK LEFT_ROOM")
        owner.send("NEXT_ITEM %d" % room_id)
        owner.read_line()
        owner.read_line()
        self.assertEqual(stay.read_line(), "EVENT ITEM_ENDED 1 A NO_SALE")
        self.assertFalse(leave.has_data())

    def test_04_owner_disconnect_keeps_items_and_room_state(self):
        owner = self.make_user("seller")
        room_id = self.make_room(owner, "Shop")
        owner.cmd("ADD_ITEM %d A 1000 2000" % room_id)
        owner.cmd("ADD_ITEM %d B 1000 2000" % room_id)
        owner.cmd("START_AUCTION %d" % room_id)
        owner.close()
        again = self.connect()
        self.assertEqual(again.cmd("LOGIN seller %s" % self.password), "OK Login successful")
        self.assertEqual(again.cmd("START_AUCTION %d" % room_id), "ERROR Auction already running")
        again.send("NEXT_ITEM %d" % room_id)
        self.assertEqual(again.read_line(), "OK ITEM_ENDED 1 A")
        self.assertTrue(again.read_line().startswith("OK ITEM_STARTED 2 B"))

    def test_05_item_commands_rejected_for_guest_after_logout(self):
        owner = self.make_user("seller")
        room_id = self.make_room(owner, "Shop")
        owner.cmd("ADD_ITEM %d A 1000 2000" % room_id)
        self.assertEqual(owner.cmd("LOGOUT"), "OK Logout successful")
        for command in ["ADD_ITEM %d B 1000 2000" % room_id, "LIST_ITEMS %d" % room_id,
                        "REMOVE_ITEM 1", "START_AUCTION %d" % room_id, "NEXT_ITEM %d" % room_id,
                        "ADD_ITEM"]:
            self.assertEqual(owner.cmd(command), "ERROR Not logged in", command)

    def test_06_log_contains_whole_item_lifecycle(self):
        owner = self.make_user("seller")
        room_id = self.make_room(owner, "Shop")
        owner.cmd("ADD_ITEM %d A 1000 2000" % room_id)
        owner.cmd("ADD_ITEM %d B 1000 2000" % room_id)
        owner.cmd("REMOVE_ITEM 2")
        owner.cmd("ADD_ITEM %d C 1000 2000" % room_id)
        owner.cmd("START_AUCTION %d" % room_id)
        owner.send("NEXT_ITEM %d" % room_id)
        owner.read_line()
        owner.read_line()
        owner.send("NEXT_ITEM %d" % room_id)
        owner.read_line()
        owner.read_line()
        events = [line.split("] ", 1)[1].split()[0] for line in self.read_log().splitlines()
                  if any(key in line for key in ("ITEM_ADDED", "ITEM_REMOVED", "AUCTION_"))]
        self.assertEqual(events, ["ITEM_ADDED", "ITEM_ADDED", "ITEM_REMOVED", "ITEM_ADDED",
                                  "AUCTION_ITEM_STARTED", "AUCTION_ITEM_ENDED", "AUCTION_ITEM_STARTED",
                                  "AUCTION_ITEM_ENDED", "AUCTION_FINISHED"])

    def test_07_existing_flows_regression(self):
        owner = self.make_user("seller")
        room_id = self.make_room(owner, "Shop")
        other = self.make_user("other")
        self.join(other, room_id, "Shop")
        self.assertEqual(other.cmd("JOIN_ROOM %d" % room_id), "ERROR Already in a room")
        self.assertEqual(other.cmd("LOGOUT"), "OK Logout successful")
        self.assertEqual(owner.cmd("CREATE_ROOM Shop"), "ERROR Room already exists")
        self.assertEqual(owner.cmd("LEAVE_ROOM"), "ERROR Not in a room")
        self.assertEqual(owner.cmd("BOGUS"), "ERROR Unknown command: BOGUS")
        owner.send("QUIT")
        self.assertEqual(owner.read_line(), "OK Goodbye")


if __name__ == "__main__":
    run_main()
