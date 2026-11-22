import unittest

from item_test_base import ServerTestCase, run_main


class NextItemTests(ServerTestCase):
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

    def start(self):
        response = self.owner.cmd("START_AUCTION %d" % self.room_id)
        self.assertTrue(response.startswith("OK AUCTION_STARTED"), response)

    def next(self, client=None, room_id=None):
        client = client or self.owner
        room_id = room_id or self.room_id
        client.send("NEXT_ITEM %d" % room_id)

    def test_01_next_item_ends_current_and_starts_next(self):
        self.add_item(self.owner, self.room_id, "A", 1000, 9000)
        self.add_item(self.owner, self.room_id, "B", 2000, 8000)
        self.start()
        self.next()
        self.assertEqual(self.owner.read_line(), "OK ITEM_ENDED 1 A")
        self.assertEqual(self.owner.read_line(), "OK ITEM_STARTED 2 B START 2000 BUYNOW 8000")
        self.assertEqual(self.statuses(self.owner, self.room_id), {1: "ENDED", 2: "AUCTIONING"})

    def test_02_last_item_finishes_auction(self):
        self.add_item(self.owner, self.room_id, "A")
        self.start()
        self.next()
        self.assertEqual(self.owner.read_line(), "OK ITEM_ENDED 1 A")
        self.assertEqual(self.owner.read_line(), "OK AUCTION_FINISHED")
        self.assertEqual(self.statuses(self.owner, self.room_id), {1: "ENDED"})

    def test_03_items_are_auctioned_in_order(self):
        for name in ["A", "B", "C"]:
            self.add_item(self.owner, self.room_id, name)
        self.start()
        started = []
        for _ in range(2):
            self.next()
            self.owner.read_line()
            started.append(self.owner.read_line().split()[2])
        self.assertEqual(started, ["2", "3"])
        self.next()
        self.assertEqual(self.owner.read_line(), "OK ITEM_ENDED 3 C")
        self.assertEqual(self.owner.read_line(), "OK AUCTION_FINISHED")
        self.assertEqual(self.statuses(self.owner, self.room_id), {1: "ENDED", 2: "ENDED", 3: "ENDED"})

    def test_04_next_item_before_start(self):
        self.add_item(self.owner, self.room_id, "A")
        self.assertEqual(self.owner.cmd("NEXT_ITEM %d" % self.room_id), "ERROR No item is being auctioned")
        self.assertEqual(self.statuses(self.owner, self.room_id), {1: "PENDING"})

    def test_05_next_item_after_auction_finished(self):
        self.add_item(self.owner, self.room_id, "A")
        self.start()
        self.next()
        self.owner.read_until("OK AUCTION_FINISHED")
        self.assertEqual(self.owner.cmd("NEXT_ITEM %d" % self.room_id), "ERROR No item is being auctioned")

    def test_06_next_item_not_logged_in(self):
        guest = self.connect()
        self.assertEqual(guest.cmd("NEXT_ITEM %d" % self.room_id), "ERROR Not logged in")

    def test_07_next_item_invalid_room_id(self):
        for bad in ["abc", "0", "-1", "1.5"]:
            self.assertEqual(self.owner.cmd("NEXT_ITEM %s" % bad), "ERROR Invalid room ID", bad)

    def test_08_next_item_room_not_found(self):
        self.assertEqual(self.owner.cmd("NEXT_ITEM 999"), "ERROR Room not found")

    def test_09_next_item_not_room_owner(self):
        self.add_item(self.owner, self.room_id, "A")
        self.start()
        other = self.make_user("other")
        self.assertEqual(other.cmd("NEXT_ITEM %d" % self.room_id), "ERROR Not room owner")
        self.assertEqual(self.statuses(self.owner, self.room_id), {1: "AUCTIONING"})

    def test_10_next_item_wrong_number_of_arguments(self):
        self.assertEqual(self.owner.cmd("NEXT_ITEM"), "ERROR Invalid command or arguments")
        self.assertEqual(self.owner.cmd("NEXT_ITEM 1 2"), "ERROR Invalid command or arguments")

    def test_11_start_again_after_finish_with_new_item(self):
        self.add_item(self.owner, self.room_id, "A")
        self.start()
        self.next()
        self.owner.read_until("OK AUCTION_FINISHED")
        self.assertEqual(self.owner.cmd("START_AUCTION %d" % self.room_id), "ERROR No pending items")
        self.add_item(self.owner, self.room_id, "B")
        self.assertTrue(self.owner.cmd("START_AUCTION %d" % self.room_id).startswith("OK AUCTION_STARTED 2 B"))
        self.assertEqual(self.statuses(self.owner, self.room_id), {1: "ENDED", 2: "AUCTIONING"})

    def test_12_item_added_during_auction_is_auctioned_later(self):
        self.add_item(self.owner, self.room_id, "A")
        self.start()
        self.add_item(self.owner, self.room_id, "B")
        self.next()
        self.assertEqual(self.owner.read_line(), "OK ITEM_ENDED 1 A")
        self.assertTrue(self.owner.read_line().startswith("OK ITEM_STARTED 2 B"))

    def test_13_removed_pending_item_is_skipped(self):
        for name in ["A", "B", "C"]:
            self.add_item(self.owner, self.room_id, name)
        self.start()
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 2"), "OK ITEM_REMOVED ID: 2")
        self.next()
        self.assertEqual(self.owner.read_line(), "OK ITEM_ENDED 1 A")
        self.assertTrue(self.owner.read_line().startswith("OK ITEM_STARTED 3 C"))

    def test_14_removing_last_pending_item_makes_next_finish_auction(self):
        self.add_item(self.owner, self.room_id, "A")
        self.add_item(self.owner, self.room_id, "B")
        self.start()
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 2"), "OK ITEM_REMOVED ID: 2")
        self.next()
        self.assertEqual(self.owner.read_line(), "OK ITEM_ENDED 1 A")
        self.assertEqual(self.owner.read_line(), "OK AUCTION_FINISHED")

    def test_15_cannot_remove_item_being_auctioned_or_ended(self):
        for name in ["A", "B", "C"]:
            self.add_item(self.owner, self.room_id, name)
        self.start()
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 1"), "ERROR Item already put up for auction")
        self.next()
        self.owner.read_line()
        self.owner.read_line()
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 1"), "ERROR Item already put up for auction")
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 2"), "ERROR Item already put up for auction")
        self.assertEqual(self.owner.cmd("REMOVE_ITEM 3"), "OK ITEM_REMOVED ID: 3")
        self.assertEqual(self.statuses(self.owner, self.room_id), {1: "ENDED", 2: "AUCTIONING"})

    def test_16_members_receive_all_events_in_order(self):
        self.add_item(self.owner, self.room_id, "A", 1000, 9000)
        self.add_item(self.owner, self.room_id, "B", 2000, 8000)
        member = self.make_user("member")
        self.join(member, self.room_id, "RoomA")
        self.start()
        self.assertEqual(member.read_line(), "EVENT ITEM_STARTED 1 A START 1000 BUYNOW 9000")
        self.next()
        self.owner.read_line()
        self.owner.read_line()
        self.assertEqual(member.read_line(), "EVENT ITEM_ENDED 1 A NO_SALE")
        self.assertEqual(member.read_line(), "EVENT ITEM_STARTED 2 B START 2000 BUYNOW 8000")
        self.next()
        self.owner.read_line()
        self.owner.read_line()
        self.assertEqual(member.read_line(), "EVENT ITEM_ENDED 2 B NO_SALE")
        self.assertEqual(member.read_line(), "EVENT AUCTION_FINISHED")

    def test_17_non_members_do_not_receive_events(self):
        self.add_item(self.owner, self.room_id, "A")
        self.add_item(self.owner, self.room_id, "B")
        room_b = self.make_room(self.owner, "RoomB")
        outsider = self.make_user("outsider")
        other_member = self.make_user("other_member")
        self.join(other_member, room_b, "RoomB")
        self.start()
        self.next()
        self.owner.read_line()
        self.owner.read_line()
        self.assertFalse(outsider.has_data())
        self.assertFalse(other_member.has_data())

    def test_18_owner_inside_room_does_not_get_duplicate_events(self):
        self.add_item(self.owner, self.room_id, "A")
        self.add_item(self.owner, self.room_id, "B")
        self.join(self.owner, self.room_id, "RoomA")
        self.start()
        self.next()
        self.assertEqual(self.owner.read_line(), "OK ITEM_ENDED 1 A")
        self.assertTrue(self.owner.read_line().startswith("OK ITEM_STARTED 2 B"))
        self.assertFalse(self.owner.has_data())

    def test_19_member_joining_midway_only_gets_later_events(self):
        self.add_item(self.owner, self.room_id, "A")
        self.add_item(self.owner, self.room_id, "B")
        self.start()
        late = self.make_user("late")
        self.join(late, self.room_id, "RoomA")
        self.assertFalse(late.has_data())
        self.next()
        self.owner.read_line()
        self.owner.read_line()
        self.assertEqual(late.read_line(), "EVENT ITEM_ENDED 1 A NO_SALE")

    def test_20_two_rooms_run_independently(self):
        room_b = self.make_room(self.owner, "RoomB")
        self.add_item(self.owner, self.room_id, "A1")
        self.add_item(self.owner, self.room_id, "A2")
        self.add_item(self.owner, room_b, "B1")
        self.add_item(self.owner, room_b, "B2")
        self.start()
        self.assertTrue(self.owner.cmd("START_AUCTION %d" % room_b).startswith("OK AUCTION_STARTED 3 B1"))
        self.next(room_id=room_b)
        self.assertEqual(self.owner.read_line(), "OK ITEM_ENDED 3 B1")
        self.assertTrue(self.owner.read_line().startswith("OK ITEM_STARTED 4 B2"))
        self.assertEqual(self.statuses(self.owner, self.room_id), {1: "AUCTIONING", 2: "PENDING"})
        self.assertEqual(self.statuses(self.owner, room_b), {3: "ENDED", 4: "AUCTIONING"})

    def test_21_member_disconnect_during_events_does_not_break_server(self):
        self.add_item(self.owner, self.room_id, "A")
        self.add_item(self.owner, self.room_id, "B")
        member = self.make_user("member")
        self.join(member, self.room_id, "RoomA")
        self.start()
        member.close()
        self.next()
        self.assertEqual(self.owner.read_line(), "OK ITEM_ENDED 1 A")
        self.assertTrue(self.owner.read_line().startswith("OK ITEM_STARTED 2 B"))
        self.assertEqual(self.owner.cmd("PING"), "OK PONG")

    def test_22_events_are_written_to_log(self):
        self.add_item(self.owner, self.room_id, "A")
        self.add_item(self.owner, self.room_id, "B")
        self.start()
        self.next()
        self.owner.read_line()
        self.owner.read_line()
        self.next()
        self.owner.read_line()
        self.owner.read_line()
        log = self.read_log()
        self.assertEqual(log.count("AUCTION_ITEM_STARTED"), 2)
        self.assertIn("AUCTION_ITEM_ENDED room_id=%d item_id=1 name=A result=NO_SALE" % self.room_id, log)
        self.assertIn("AUCTION_ITEM_ENDED room_id=%d item_id=2 name=B result=NO_SALE" % self.room_id, log)
        self.assertIn("AUCTION_FINISHED room_id=%d" % self.room_id, log)

    def test_23_help_lists_next_item(self):
        self.assertIn("NEXT_ITEM", self.owner.cmd("HELP"))

    def test_24_next_item_two_commands_in_one_send(self):
        self.add_item(self.owner, self.room_id, "A")
        self.add_item(self.owner, self.room_id, "B")
        self.start()
        self.owner.send_raw(("NEXT_ITEM %d\nNEXT_ITEM %d\nNEXT_ITEM %d\n"
                             % (self.room_id, self.room_id, self.room_id)).encode())
        lines = [self.owner.read_line() for _ in range(5)]
        self.assertEqual(lines[0], "OK ITEM_ENDED 1 A")
        self.assertTrue(lines[1].startswith("OK ITEM_STARTED 2 B"))
        self.assertEqual(lines[2], "OK ITEM_ENDED 2 B")
        self.assertEqual(lines[3], "OK AUCTION_FINISHED")
        self.assertEqual(lines[4], "ERROR No item is being auctioned")


if __name__ == "__main__":
    run_main()
