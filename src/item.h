#ifndef ITEM_H
#define ITEM_H

#include "common.h"

int find_item_by_id(int item_id);
const char *item_status_name(ItemStatus status);
int count_room_items(int room_id);
void add_item(int client_index,
              int room_id,
              const char *name,
              long long start_price,
              long long buy_now_price);
void list_items(int client_index, int room_id);
void remove_item(int client_index, int item_id);
void start_auction(int client_index, int room_id);

#endif
