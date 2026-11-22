#include <stdio.h>
#include <string.h>
#include "common.h"
#include "item.h"
#include "room.h"
#include "logger.h"

int find_item_by_id(int item_id) {
    for (int i = 0; i < MAX_ITEMS; i++) {
        if (items[i].is_active && items[i].item_id == item_id) {
            return i;
        }
    }

    return -1;
}

const char *item_status_name(ItemStatus status) {
    if (status == ITEM_AUCTIONING) {
        return "AUCTIONING";
    }
    if (status == ITEM_ENDED) {
        return "ENDED";
    }
    return "PENDING";
}

int count_room_items(int room_id) {
    int count = 0;

    for (int i = 0; i < MAX_ITEMS; i++) {
        if (items[i].is_active && items[i].room_id == room_id) {
            count++;
        }
    }

    return count;
}

static int find_next_item(int room_id, int after_id) {
    int best = -1;

    for (int i = 0; i < MAX_ITEMS; i++) {
        if (!items[i].is_active || items[i].room_id != room_id ||
            items[i].item_id <= after_id) {
            continue;
        }
        if (best < 0 || items[i].item_id < items[best].item_id) {
            best = i;
        }
    }

    return best;
}

void add_item(int client_index,
              int room_id,
              const char *name,
              long long start_price,
              long long buy_now_price) {
    Client *client = &clients[client_index];

    if (client->user_index < 0) {
        send_message(client->socket_fd, "ERROR Not logged in\n");
        return;
    }

    int room_index = find_room_by_id(room_id);
    if (room_index < 0) {
        send_message(client->socket_fd, "ERROR Room not found\n");
        return;
    }

    if (!is_room_owner(client->user_index, room_index)) {
        send_message(client->socket_fd, "ERROR Not room owner\n");
        return;
    }

    if (start_price <= 0 || start_price > MAX_PRICE ||
        buy_now_price <= 0 || buy_now_price > MAX_PRICE) {
        send_message(client->socket_fd, "ERROR Invalid price\n");
        return;
    }

    if (buy_now_price <= start_price) {
        send_message(client->socket_fd,
                     "ERROR Buy-now price must be greater than start price\n");
        return;
    }

    if (count_room_items(room_id) >= MAX_ITEMS_PER_ROOM) {
        send_message(client->socket_fd,
                     "ERROR Item limit reached (maximum 20 items per room)\n");
        return;
    }

    int slot = -1;
    for (int i = 0; i < MAX_ITEMS; i++) {
        if (!items[i].is_active) {
            slot = i;
            break;
        }
    }

    if (slot < 0) {
        send_message(client->socket_fd, "ERROR Item database is full\n");
        return;
    }

    AuctionItem *item = &items[slot];
    item->item_id = next_item_id++;
    item->room_id = room_id;
    snprintf(item->name, sizeof(item->name), "%s", name);
    item->start_price = start_price;
    item->buy_now_price = buy_now_price;
    item->status = ITEM_PENDING;
    item->is_active = 1;

    log_event("ITEM_ADDED id=%d room_id=%d name=%s owner=%s start=%lld buy_now=%lld",
              item->item_id, room_id, item->name,
              users[client->user_index].username,
              item->start_price, item->buy_now_price);

    char response[128];
    snprintf(response, sizeof(response), "OK ITEM_ADDED ID: %d\n",
             item->item_id);
    send_message(client->socket_fd, response);
}

void list_items(int client_index, int room_id) {
    Client *client = &clients[client_index];

    if (client->user_index < 0) {
        send_message(client->socket_fd, "ERROR Not logged in\n");
        return;
    }

    if (find_room_by_id(room_id) < 0) {
        send_message(client->socket_fd, "ERROR Room not found\n");
        return;
    }

    int item_count = 0;
    int last_id = 0;
    int index;

    send_message(client->socket_fd, "OK ITEM_LIST\n");

    while ((index = find_next_item(room_id, last_id)) >= 0) {
        char response[256];
        snprintf(response, sizeof(response),
                 "ITEM %d %s START %lld BUYNOW %lld STATUS %s\n",
                 items[index].item_id,
                 items[index].name,
                 items[index].start_price,
                 items[index].buy_now_price,
                 item_status_name(items[index].status));
        if (send_message(client->socket_fd, response) < 0) {
            return;
        }
        last_id = items[index].item_id;
        item_count++;
    }

    if (item_count == 0) {
        send_message(client->socket_fd, "NO_ITEMS\n");
    }

    send_message(client->socket_fd, "END_ITEM_LIST\n");
}
